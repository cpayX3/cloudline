import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from room_core import RoomStore
from room_admission import RoomAdmission
from agent_sessions import AgentSessions
from negotiation import Negotiation
from mandate_store import MandateStore
from autonomous_consent import AutonomousConsent
from autonomous_scope import AutonomousScope


class FakeHandler(server.Handler):
    def __init__(self, path, body, authorization=None):
        self.path = path
        self.headers = {
            "Host": server.HOST,
            "Origin": "http://" + server.HOST,
            "Content-Type": "application/json",
            "Content-Length": str(len(json.dumps(body).encode()))
        }
        if authorization:
            self.headers["Authorization"] = authorization
        self.rfile = io.BytesIO(json.dumps(body).encode())
        self.status = None
        self.result = None

    def reply(self, status, value):
        self.status = status
        self.result = value

    def send_response(self, status):
        self.status = status

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass


class AutonomousHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.temp.name) / "rooms.sqlite")
        self.admission = RoomAdmission(self.store)
        self.sessions = AgentSessions(self.store)
        self.negotiation = Negotiation(self.store)
        self.mandates = MandateStore(self.store)
        self.consent = AutonomousConsent(self.store)
        self.scope = AutonomousScope(self.store)

        self.buyer = "buyer-agent"
        self.seller = "seller-agent"

        self.room = self.store.request_room(
            self.buyer, self.seller, "HTTP security test"
        )

        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (self.room,)
            )

        self.patches = [
            patch.object(server, "STORE", self.store),
            patch.object(server, "SESSIONS", self.sessions),
            patch.object(server, "NEGOTIATION", self.negotiation),
            patch.object(server, "MANDATES", self.mandates),
            patch.object(server, "AUTONOMOUS_CONSENT", self.consent),
            patch.object(server, "AUTONOMOUS_SCOPE", self.scope),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.store.close()
        self.temp.cleanup()

    def request(self, path, body, token=None):
        handler = FakeHandler(
            path, body,
            "Bearer " + token if token else None
        )
        handler.do_POST()
        return handler.status, handler.result

    # BILATERAL_HTTP_TESTS_V1
    def authenticated_token(self, address):
        # Exercise HTTP authorization with a locally issued test session.
        # The admission signature flow is tested separately.
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expiry = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).isoformat()

        with self.store.db:
            self.store.db.execute(
                """
                INSERT INTO agent_sessions
                (token_hash, room_id, address, expires_at, revoked)
                VALUES (?, ?, ?, ?, 0)
                """,
                (digest, self.room, address, expiry)
            )

        return token

    def register_mandates(self):
        self.mandates.register(self.room, self.buyer, {
            "target_units": 15,
            "limit_units": 35
        })
        self.mandates.register(self.room, self.seller, {
            "target_units": 40,
            "limit_units": 30
        })

    def run_body(self):
        return {
            "room_id": self.room,
            "service": "wallet-report",
            "resource": "/agent/v3/wallet-vibe-check",
            "network": "xrpl:0",
            "asset": "RLUSD",
            "recipient": "seller-wallet"
        }

    def test_one_sided_consent_blocks_run(self):
        buyer_token = self.authenticated_token(self.buyer)
        seller_token = self.authenticated_token(self.seller)
        self.register_mandates()
        self.authorize_scope(buyer_token, seller_token)

        status, _ = self.request(
            "/api/autonomous/consent",
            {"room_id": self.room, "enabled": True},
            buyer_token
        )
        self.assertEqual(status, 200)

        status, result = self.request(
            "/api/autonomous/run",
            self.run_body(),
            buyer_token
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            result["error"],
            "BILATERAL_AUTONOMOUS_CONSENT_REQUIRED"
        )

    def test_bilateral_consent_completes_negotiation(self):
        buyer_token = self.authenticated_token(self.buyer)
        seller_token = self.authenticated_token(self.seller)
        self.register_mandates()
        self.authorize_scope(buyer_token, seller_token)

        for token in (buyer_token, seller_token):
            status, _ = self.request(
                "/api/autonomous/consent",
                {"room_id": self.room, "enabled": True},
                token
            )
            self.assertEqual(status, 200)

        status, result = self.request(
            "/api/autonomous/run",
            self.run_body(),
            buyer_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "NEGOTIATION_COMPLETED")
        self.assertEqual(result["payment_authority"], "NOT_GRANTED")

        status, replay = self.request(
            "/api/autonomous/run",
            self.run_body(),
            buyer_token
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            replay["error"], "NEGOTIATION_ALREADY_STARTED"
        )

    def test_revoked_consent_blocks_run(self):
        buyer_token = self.authenticated_token(self.buyer)
        seller_token = self.authenticated_token(self.seller)
        self.register_mandates()
        self.authorize_scope(buyer_token, seller_token)

        for token in (buyer_token, seller_token):
            self.request(
                "/api/autonomous/consent",
                {"room_id": self.room, "enabled": True},
                token
            )

        status, _ = self.request(
            "/api/autonomous/consent",
            {"room_id": self.room, "enabled": False},
            seller_token
        )
        self.assertEqual(status, 200)

        status, result = self.request(
            "/api/autonomous/run",
            self.run_body(),
            buyer_token
        )
        self.assertEqual(status, 403)
        self.assertEqual(
            result["error"],
            "BILATERAL_AUTONOMOUS_CONSENT_REQUIRED"
        )

    # HTTP_SCOPE_TESTS_V1
    def authorize_scope(self, buyer_token, seller_token):
        scope = {
            key: value
            for key, value in self.run_body().items()
            if key != "room_id"
        }

        for token in (buyer_token, seller_token):
            status, result = self.request(
                "/api/autonomous/scope",
                {"room_id": self.room, "scope": scope},
                token
            )
            self.assertEqual(status, 200, result)

    def test_changed_recipient_blocked_over_http(self):
        buyer_token = self.authenticated_token(self.buyer)
        seller_token = self.authenticated_token(self.seller)
        self.register_mandates()

        for token in (buyer_token, seller_token):
            self.request(
                "/api/autonomous/consent",
                {"room_id": self.room, "enabled": True},
                token
            )

        self.authorize_scope(buyer_token, seller_token)

        changed = self.run_body()
        changed["recipient"] = "unauthorized-wallet"

        status, result = self.request(
            "/api/autonomous/run",
            changed,
            buyer_token
        )

        self.assertEqual(status, 403)
        self.assertEqual(
            result["error"],
            "BILATERAL_SCOPE_AUTHORIZATION_REQUIRED"
        )

    def test_missing_scope_blocks_run(self):
        buyer_token = self.authenticated_token(self.buyer)
        seller_token = self.authenticated_token(self.seller)
        self.register_mandates()

        for token in (buyer_token, seller_token):
            self.request(
                "/api/autonomous/consent",
                {"room_id": self.room, "enabled": True},
                token
            )

        status, result = self.request(
            "/api/autonomous/run",
            self.run_body(),
            buyer_token
        )

        self.assertEqual(status, 403)
        self.assertEqual(
            result["error"],
            "BILATERAL_SCOPE_AUTHORIZATION_REQUIRED"
        )

    def test_consent_requires_session(self):
        status, result = self.request(
            "/api/autonomous/consent",
            {"room_id": self.room, "enabled": True}
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "SESSION_REQUIRED")

    def test_run_requires_session(self):
        status, result = self.request(
            "/api/autonomous/run",
            {"room_id": self.room}
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "SESSION_REQUIRED")

    def test_invalid_token_rejected(self):
        status, result = self.request(
            "/api/autonomous/consent",
            {"room_id": self.room, "enabled": True},
            "x" * 48
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "INVALID_SESSION")

    def test_origin_rejected(self):
        handler = FakeHandler(
            "/api/autonomous/run",
            {"room_id": self.room}
        )
        handler.headers["Origin"] = "https://untrusted.example"
        handler.do_POST()
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.result["error"], "Origin rejected")


if __name__ == "__main__":
    unittest.main()
