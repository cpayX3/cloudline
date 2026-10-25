import cloudline_platform_poc
import cloudline_web_bridge
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import cpx_registry
from room_core import RoomStore
from room_admission import RoomAdmission
from agent_sessions import AgentSessions
from mandate_store import MandateStore
from autonomous_consent import AutonomousConsent
from autonomous_scope import AutonomousScope
from negotiation_runner import run_negotiation
from negotiation import Negotiation
from conversation_bridge import ConversationBridge

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "runtime"
DATA.mkdir(exist_ok=True)
STORE = RoomStore(DATA / "rooms.sqlite")
ADMISSION = RoomAdmission(STORE)
SESSIONS = AgentSessions(STORE)
NEGOTIATION = Negotiation(STORE)
MANDATES = MandateStore(STORE)
AUTONOMOUS_CONSENT = AutonomousConsent(STORE)
AUTONOMOUS_SCOPE = AutonomousScope(STORE)
CONVERSATION = ConversationBridge(STORE)
HOST = "127.0.0.1:8787"

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") == HOST

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Local access only"})
        if cloudline_web_bridge.handle(self, 'GET'):
            return
        path = urlparse(self.path).path

        # XRPay hackathon evidence view: local, read-only, fixed participants.
        if path == "/api/demo/xrpay":
            import sqlite3
            import json as _json

            buyer = "agent_32b12ad0565cab3fa6d35ae50375cb4a"
            seller = "agent_f982fdf4d88d2a3399ff972fd4b4d53f"
            database = DATA / "partner_api.sqlite"

            if not database.exists():
                return self.reply(404, {"error": "Partner database missing"})

            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row

            try:
                rooms = connection.execute("""
                    SELECT id, buyer, seller, purpose, status, created_at
                    FROM rooms
                    WHERE (buyer=? AND seller=?)
                       OR (buyer=? AND seller=?)
                    ORDER BY created_at DESC
                """, (buyer, seller, seller, buyer)).fetchall()

                output = []

                for room in rooms:
                    events = connection.execute("""
                        SELECT id, sender, kind, payload, created_at
                        FROM events
                        WHERE room_id=?
                        ORDER BY created_at, rowid
                    """, (room["id"],)).fetchall()

                    agreements = connection.execute("""
                        SELECT id, terms, buyer_accepted,
                               seller_accepted, created_at
                        FROM agreements
                        WHERE room_id=?
                    """, (room["id"],)).fetchall()

                    def decode(value):
                        if value is None:
                            return None
                        try:
                            return _json.loads(value)
                        except (TypeError, ValueError):
                            return value

                    output.append({
                        "room": dict(room),
                        "events": [
                            {
                                **dict(event),
                                "payload": decode(event["payload"])
                            }
                            for event in events
                        ],
                        "agreements": [
                            {
                                **dict(agreement),
                                "terms": decode(agreement["terms"])
                            }
                            for agreement in agreements
                        ]
                    })

                return self.reply(200, {
                    "source": "partner_api.sqlite",
                    "mode": "LOCAL_READ_ONLY_DEMO",
                    "buyer_name": "XRPay Testnet Riverside Buyer Agent",
                    "seller_name": "XRPay Testnet Cedar Supplier Agent",
                    "rooms": output
                })
            finally:
                connection.close()

        if cloudline_platform_poc.handle(self, path):
            return

        if cpx_registry.handle_get(self, path):
            return
        if path.startswith("/api/rooms/") and path.endswith("/negotiation"):
            return self.reply(403, {
                "error": "AUTHENTICATED_HISTORY_REQUIRED"
            })

        if False and path.startswith("/api/rooms/") and path.endswith("/negotiation"):
            room_id = path[len("/api/rooms/"):-len("/negotiation")].rstrip("/")
            try:
                room = STORE.get_room(room_id)
                from negotiation import Negotiation
                Negotiation(STORE)
                rows = STORE.db.execute(
                    """SELECT id, proposer, parent_id, terms_json,
                              terms_hash, state
                       FROM negotiation_offers
                       WHERE room_id=? ORDER BY rowid""",
                    (room_id,)
                ).fetchall()
                return self.reply(200, {
                    "room_id": room_id,
                    "room_state": room["state"],
                    "offers": [
                        {
                            "id": row[0],
                            "proposer": row[1],
                            "parent_id": row[2],
                            "terms": json.loads(row[3]),
                            "terms_hash": row[4],
                            "state": row[5]
                        }
                        for row in rows
                    ]
                })
            except KeyError:
                return self.reply(404, {"error": "Room not found"})

        if path.startswith("/api/rooms/"):
            return self.reply(403, {
                "error": "AUTHENTICATED_HISTORY_REQUIRED"
            })

        if False and path.startswith("/api/rooms/"):
            room_id = path.removeprefix("/api/rooms/")
            try:
                return self.reply(200, {
                    "room": STORE.get_room(room_id),
                    "events": STORE.events(room_id)
                })
            except KeyError:
                return self.reply(404, {"error": "Room not found"})

        # CLOUDLINE_AUTONOMOUS_STATIC_V1
        if path == "/cloudline-autonomous.js":
            script = ROOT / "public" / "cloudline-autonomous.js"
            if not script.is_file():
                return self.reply(404, {"error": "Script not found"})

            body = script.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/javascript; charset=utf-8"
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/cloudline-logo.png":
            body = (ROOT / "public" / "cloudline-logo.png").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/cloudline-partner.js":
            script = ROOT / "public" / "cloudline-partner.js"
            body = script.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        pages = {
            "/": "index.html",
            "/cloudline": "cloudline.html"
        }
        if path not in pages:
            return self.reply(404, {"error": "Not found"})
        body = (ROOT / "public" / pages[path]).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Local access only"})
        if cloudline_web_bridge.handle(self, 'POST'):
            return
        # CLOUDLINE_AGENT_ORIGIN_V1
        # Browsers must use our own origin.
        # Authenticated non-browser clients may omit Origin.
        origin = self.headers.get("Origin")
        agent_routes = {
            "/api/conversation/message",
            "/api/conversation/resolve",
            "/api/conversation/history"
        }
        if origin != "http://" + HOST:
            if not (self.path in agent_routes and origin is None):
                return self.reply(403, {"error": "Origin rejected"})
        if cpx_registry.handle_post(self):
            return
        if self.path not in (
            "/api/rooms",
            "/api/admission/challenge",
            "/api/admission/verify",
            "/api/mandates",
            "/api/negotiation/offer",
            "/api/negotiation/accept",
            "/api/autonomous/consent",
            "/api/autonomous/scope",
            "/api/autonomous/run",
            "/api/conversation/message",
            "/api/conversation/resolve",
            "/api/conversation/history"
        ):
            return self.reply(404, {"error": "Not found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 16384:
                return self.reply(413, {"error": "Invalid request size"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON required"})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object")
            # CLOUDLINE_CONVERSATION_HTTP_V1
            if self.path in (
                "/api/conversation/message",
                "/api/conversation/resolve",
                "/api/conversation/history"
            ):
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id,
                    self.headers.get("Authorization")
                )

                if self.path == "/api/conversation/message":
                    message_id = CONVERSATION.receive(
                        room_id,
                        actor,
                        body.get("payload"),
                        action=body.get("action", "message"),
                        question_id=body.get("question_id")
                    )
                    return self.reply(201, {
                        "status": "MESSAGE_RECORDED",
                        "room_id": room_id,
                        "message_id": message_id,
                        "payment_authority": "NOT_GRANTED"
                    })

                if self.path == "/api/conversation/resolve":
                    CONVERSATION.resolve(
                        room_id,
                        actor,
                        body.get("question_id"),
                        body.get("answer_id")
                    )
                    return self.reply(200, {
                        "status": "QUESTION_RESOLVED",
                        "room_id": room_id,
                        "payment_authority": "NOT_GRANTED"
                    })

                events = STORE.events(room_id)
                allowed = {
                    "MESSAGE",
                    "QUESTION",
                    "ANSWER",
                    "QUESTION_RESOLVED"
                }

                return self.reply(200, {
                    "room_id": room_id,
                    "messages": [
                        event for event in events
                        if event["kind"] in allowed
                    ],
                    "payment_authority": "NOT_GRANTED"
                })

            if self.path == "/api/admission/challenge":
                result = ADMISSION.challenge(
                    body.get("room_id"),
                    body.get("address")
                )
                return self.reply(200, result)

            if self.path == "/api/admission/verify":
                result = ADMISSION.verify(
                    body.get("room_id"),
                    body.get("address"),
                    body.get("challenge_id"),
                    body.get("signature")
                )
                session = SESSIONS.issue(
                    body.get("room_id"), result["address"]
                )
                result["session_token"] = session["token"]
                result["session_expires_at"] = session["expires_at"]
                return self.reply(200, result)

            # CLOUDLINE_AUTONOMOUS_HTTP_V1
            if self.path == "/api/autonomous/consent":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )
                result = AUTONOMOUS_CONSENT.set(
                    room_id, actor, body.get("enabled")
                )
                return self.reply(200, result)

            # CLOUDLINE_SCOPE_HTTP_V1
            if self.path == "/api/autonomous/scope":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )
                result = AUTONOMOUS_SCOPE.authorize(
                    room_id, actor, body.get("scope")
                )
                return self.reply(200, result)

            if self.path == "/api/autonomous/run":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )

                room = STORE.get_room(room_id)
                if actor not in (room["buyer"], room["seller"]):
                    raise PermissionError("NOT_ROOM_PARTICIPANT")

                scope = {
                    key: body.get(key)
                    for key in (
                        "service", "resource", "network",
                        "asset", "recipient"
                    )
                }
                AUTONOMOUS_SCOPE.require_bilateral(
                    room_id, scope
                )

                result = run_negotiation(
                    STORE,
                    NEGOTIATION,
                    MANDATES,
                    room_id,
                    body.get("service"),
                    body.get("resource"),
                    body.get("network"),
                    body.get("asset"),
                    body.get("recipient")
                )
                return self.reply(200, result)

            if self.path == "/api/mandates":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )
                mandate = MANDATES.register(
                    room_id, actor, body.get("mandate")
                )
                return self.reply(201, {
                    "status": "MANDATE_REGISTERED",
                    "role": mandate["role"],
                    "payment_authority": "NOT_GRANTED"
                })

            if self.path == "/api/negotiation/offer":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )
                terms = body.get("terms")
                if not isinstance(terms, dict):
                    raise ValueError("INVALID_TERMS")
                MANDATES.check_amount(
                    room_id, actor, terms.get("amount_units")
                )
                offer_id = NEGOTIATION.offer(
                    room_id,
                    actor,
                    body.get("terms"),
                    body.get("parent_id")
                )
                return self.reply(201, {
                    "offer": NEGOTIATION.get(offer_id),
                    "payment_authority": "NOT_GRANTED"
                })

            if self.path == "/api/negotiation/accept":
                room_id = body.get("room_id")
                actor = SESSIONS.authenticate(
                    room_id, self.headers.get("Authorization")
                )
                offer = NEGOTIATION.get(body.get("offer_id"))
                if offer["room_id"] != room_id:
                    raise PermissionError("OFFER_ROOM_MISMATCH")
                MANDATES.check_amount(
                    room_id, actor, offer["terms"]["amount_units"]
                )
                result = NEGOTIATION.accept(
                    room_id,
                    actor,
                    body.get("offer_id"),
                    body.get("expected_hash")
                )
                result["payment_authority"] = "NOT_GRANTED"
                return self.reply(200, result)

            room_id = STORE.request_room(
                body.get("buyer"), body.get("seller"), body.get("purpose")
            )
            print("ROOM_REQUESTED", room_id, flush=True)
            return self.reply(201, {"room_id": room_id})
        except PermissionError as exc:
            return self.reply(403, {"error": str(exc)})
        except KeyError:
            return self.reply(404, {"error": "Room not found"})
        except (ValueError, TypeError):
            return self.reply(400, {"error": "Invalid request fields"})

import cloudline_workspace_feed
cloudline_workspace_feed.install(Handler)


if __name__ == "__main__":
    print("cloudline: http://" + HOST + "/cloudline", flush=True)
    print("Dashboard: http://" + HOST, flush=True)
    try:
        HTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        STORE.close()
