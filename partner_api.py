
"""cloudline Partner API v1.

Platform and agent credentials are distinct.
No endpoint grants payment execution authority.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "runtime" / "partner_api.sqlite"
DB_PATH.parent.mkdir(exist_ok=True)

HOST = "127.0.0.1"
PORT = 8788

def now():
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix):
    return prefix + "_" + secrets.token_hex(16)

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def db():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection

def initialize():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS platforms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            platform_id TEXT NOT NULL,
            merchant_ref TEXT NOT NULL,
            name TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            key_hash TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(platform_id, merchant_ref),
            FOREIGN KEY(platform_id) REFERENCES platforms(id)
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id TEXT PRIMARY KEY,
            buyer TEXT NOT NULL,
            seller TEXT NOT NULL,
            purpose TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(buyer) REFERENCES agents(id),
            FOREIGN KEY(seller) REFERENCES agents(id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        );
        CREATE TABLE IF NOT EXISTS agreements (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL UNIQUE,
            terms TEXT NOT NULL,
            buyer_accepted INTEGER NOT NULL DEFAULT 0,
            seller_accepted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(room_id) REFERENCES rooms(id)
        );
        """)

class APIError(Exception):
    def __init__(self, status, code):
        self.status = status
        self.code = code

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise APIError(415, "JSON_REQUIRED")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "INVALID_LENGTH")
        if not 0 < size <= 16384:
            raise APIError(413, "INVALID_BODY_SIZE")
        try:
            value = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            raise APIError(400, "INVALID_JSON")
        if not isinstance(value, dict):
            raise APIError(400, "OBJECT_REQUIRED")
        return value

    def token(self):
        value = self.headers.get("Authorization", "")
        if not value.startswith("Bearer "):
            raise APIError(401, "AUTH_REQUIRED")
        token = value[7:]
        if len(token) < 32 or len(token) > 256:
            raise APIError(401, "INVALID_TOKEN")
        return digest(token)

    def identity(self, c, kind):
        table = "platforms" if kind == "platform" else "agents"
        row = c.execute(
            f"SELECT * FROM {table} WHERE key_hash=?",
            (self.token(),)
        ).fetchone()
        if row is None:
            raise APIError(401, "INVALID_CREDENTIAL")
        return row

    def agent(self, c):
        return self.identity(c, "agent")

    def room(self, c, room_id, agent_id):
        room = c.execute(
            "SELECT * FROM rooms WHERE id=?",
            (room_id,)
        ).fetchone()
        if room is None:
            raise APIError(404, "ROOM_NOT_FOUND")
        if agent_id not in (room["buyer"], room["seller"]):
            raise APIError(403, "NOT_ROOM_PARTICIPANT")
        return room

    def required(self, body, *fields):
        for field in fields:
            value = body.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise APIError(400, "INVALID_" + field.upper())

    def handle_api(self, method):
        path = urlsplit(self.path).path

        if path == "/health" and method == "GET":
            return 200, {
                "status": "ok",
                "service": "cloudline-partner-api",
                "version": "1"
            }

        body = self.body() if method == "POST" else {}

        with db() as c:
            # Bootstrap requires a server-side secret.
            if path == "/api/v1/platforms/register" and method == "POST":
                configured = os.environ.get("CLOUDLINE_BOOTSTRAP_SECRET", "")
                supplied = self.headers.get("X-Cloudline-Bootstrap", "")
                if not configured or not hmac.compare_digest(configured, supplied):
                    raise APIError(403, "BOOTSTRAP_DENIED")

                self.required(body, "name")
                key = secrets.token_urlsafe(48)
                pid = new_id("platform")
                c.execute(
                    "INSERT INTO platforms VALUES (?,?,?,?)",
                    (pid, body["name"].strip(), digest(key), now())
                )
                return 201, {
                    "platform_id": pid,
                    "api_key": key,
                    "warning": "Store this key securely; it is shown only once"
                }

            if path == "/api/v1/agents/register" and method == "POST":
                platform = self.identity(c, "platform")
                self.required(body, "merchant_ref", "name")
                caps = body.get("capabilities", [])
                if not isinstance(caps, list) or len(caps) > 30 or any(
                    not isinstance(x, str) or len(x) > 100 for x in caps
                ):
                    raise APIError(400, "INVALID_CAPABILITIES")

                key = secrets.token_urlsafe(48)
                aid = new_id("agent")
                try:
                    c.execute(
                        "INSERT INTO agents VALUES (?,?,?,?,?,?,?)",
                        (
                            aid, platform["id"], body["merchant_ref"].strip(),
                            body["name"].strip(), json.dumps(caps),
                            digest(key), now()
                        )
                    )
                except sqlite3.IntegrityError:
                    raise APIError(409, "MERCHANT_ALREADY_REGISTERED")

                return 201, {
                    "agent_id": aid,
                    "agent_api_key": key,
                    "payment_authority": "NOT_GRANTED"
                }

            if path == "/api/v1/agents" and method == "GET":
                self.token()
                identity = c.execute(
                    "SELECT id FROM platforms WHERE key_hash=?",
                    (self.token(),)
                ).fetchone()
                if identity is None:
                    identity = c.execute(
                        "SELECT id FROM agents WHERE key_hash=?",
                        (self.token(),)
                    ).fetchone()
                if identity is None:
                    raise APIError(401, "INVALID_CREDENTIAL")

                rows = c.execute(
                    "SELECT id, platform_id, name, capabilities FROM agents ORDER BY created_at LIMIT 200"
                ).fetchall()
                return 200, {
                    "agents": [
                        {
                            "agent_id": r["id"],
                            "platform_id": r["platform_id"],
                            "name": r["name"],
                            "capabilities": json.loads(r["capabilities"])
                        }
                        for r in rows
                    ]
                }

            if path == "/api/v1/inbox" and method == "GET":
                agent = self.agent(c)
                query = parse_qs(urlsplit(self.path).query)
                try:
                    after = int(query.get("after", ["0"])[0])
                except ValueError:
                    raise APIError(400, "INVALID_CURSOR")
                if after < 0:
                    raise APIError(400, "INVALID_CURSOR")

                rows = c.execute(
                    """SELECT e.rowid, e.id, e.room_id, e.sender,
                              e.kind, e.payload, e.created_at
                       FROM events e
                       JOIN rooms r ON r.id=e.room_id
                       WHERE (r.buyer=? OR r.seller=?)
                         AND e.rowid>?
                       ORDER BY e.rowid LIMIT 100""",
                    (agent["id"], agent["id"], after)
                ).fetchall()

                return 200, {
                    "agent_id": agent["id"],
                    "events": [
                        {
                            "cursor": r["rowid"],
                            "event_id": r["id"],
                            "room_id": r["room_id"],
                            "sender": r["sender"],
                            "kind": r["kind"],
                            "payload": json.loads(r["payload"]),
                            "created_at": r["created_at"]
                        }
                        for r in rows
                    ],
                    "next_cursor": rows[-1]["rowid"] if rows else after
                }

            if path == "/api/v1/agents/rotate-key" and method == "POST":
                agent = self.agent(c)
                key = secrets.token_urlsafe(48)
                c.execute(
                    "UPDATE agents SET key_hash=? WHERE id=?",
                    (digest(key), agent["id"])
                )
                return 200, {
                    "agent_id": agent["id"],
                    "agent_api_key": key,
                    "previous_key": "REVOKED"
                }

            if path == "/api/v1/agents/revoke" and method == "POST":
                agent = self.agent(c)
                c.execute(
                    "UPDATE agents SET key_hash=? WHERE id=?",
                    ("REVOKED:" + secrets.token_hex(32), agent["id"])
                )
                return 200, {
                    "agent_id": agent["id"],
                    "status": "REVOKED"
                }

            if path == "/api/v1/rooms" and method == "POST":
                agent = self.agent(c)
                self.required(body, "seller_agent_id", "purpose")
                seller = body["seller_agent_id"]
                if seller == agent["id"]:
                    raise APIError(400, "SELF_ROOM_DENIED")
                if not c.execute("SELECT 1 FROM agents WHERE id=?", (seller,)).fetchone():
                    raise APIError(404, "SELLER_NOT_FOUND")
                rid = new_id("room")
                c.execute(
                    "INSERT INTO rooms VALUES (?,?,?,?,?,?)",
                    (rid, agent["id"], seller, body["purpose"], "REQUESTED", now())
                )
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        new_id("evt"),
                        rid,
                        agent["id"],
                        "ROOM_INVITED",
                        json.dumps({"buyer_agent_id": agent["id"], "seller_agent_id": seller, "purpose": body["purpose"]}, sort_keys=True),
                        now()
                    )
                )
                return 201, {"room_id": rid, "status": "REQUESTED"}

            if path == "/api/v1/rooms/respond" and method == "POST":
                agent = self.agent(c)
                self.required(body, "room_id", "decision")
                room = self.room(c, body["room_id"], agent["id"])
                if room["seller"] != agent["id"]:
                    raise APIError(403, "ONLY_INVITED_AGENT_CAN_RESPOND")
                if room["status"] != "REQUESTED":
                    raise APIError(409, "ROOM_ALREADY_DECIDED")
                if body["decision"] not in ("accept", "reject"):
                    raise APIError(400, "INVALID_DECISION")
                status = "OPEN" if body["decision"] == "accept" else "REJECTED"
                c.execute("UPDATE rooms SET status=? WHERE id=?", (status, room["id"]))
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        new_id("evt"),
                        room["id"],
                        agent["id"],
                        "ROOM_STATUS_CHANGED",
                        json.dumps({"status": status, "decision": body["decision"]}, sort_keys=True),
                        now()
                    )
                )
                return 200, {"room_id": room["id"], "status": status}

            if path == "/api/v1/messages" and method == "POST":
                agent = self.agent(c)
                self.required(body, "room_id", "kind")
                room = self.room(c, body["room_id"], agent["id"])
                if room["status"] != "OPEN":
                    raise APIError(403, "ROOM_NOT_OPEN")
                if body["kind"] not in ("message", "question", "answer", "proposal", "counteroffer", "reject"):
                    raise APIError(400, "INVALID_MESSAGE_KIND")
                payload = body.get("payload")
                if not isinstance(payload, dict):
                    raise APIError(400, "INVALID_PAYLOAD")
                event_id = new_id("evt")
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        event_id, room["id"], agent["id"],
                        body["kind"], json.dumps(payload), now()
                    )
                )
                return 201, {
                    "event_id": event_id,
                    "status": "RECORDED",
                    "payment_authority": "NOT_GRANTED"
                }

            if path.startswith("/api/v1/rooms/") and path.endswith("/events") and method == "GET":
                agent = self.agent(c)
                room_id = path[len("/api/v1/rooms/"):-len("/events")].strip("/")
                self.room(c, room_id, agent["id"])
                query = parse_qs(urlsplit(self.path).query)
                try:
                    after = int(query.get("after", ["0"])[0])
                except ValueError:
                    raise APIError(400, "INVALID_CURSOR")
                if after < 0:
                    raise APIError(400, "INVALID_CURSOR")
                rows = c.execute(
                    """SELECT rowid, * FROM events
                       WHERE room_id=? AND rowid>?
                       ORDER BY rowid LIMIT 100""",
                    (room_id, after)
                ).fetchall()
                return 200, {
                    "room_id": room_id,
                    "events": [
                        {
                            "cursor": r["rowid"],
                            "id": r["id"],
                            "sender": r["sender"],
                            "kind": r["kind"],
                            "payload": json.loads(r["payload"]),
                            "created_at": r["created_at"]
                        }
                        for r in rows
                    ],
                    "next_cursor": rows[-1]["rowid"] if rows else after
                }

            if path == "/api/v1/agreements" and method == "POST":
                agent = self.agent(c)
                self.required(body, "room_id")
                room = self.room(c, body["room_id"], agent["id"])
                if room["status"] != "OPEN":
                    raise APIError(403, "ROOM_NOT_OPEN")
                terms = body.get("terms")
                if not isinstance(terms, dict) or not terms:
                    raise APIError(400, "INVALID_TERMS")
                if c.execute("SELECT 1 FROM agreements WHERE room_id=?", (room["id"],)).fetchone():
                    raise APIError(409, "AGREEMENT_ALREADY_PROPOSED")
                agreement_id = new_id("agreement")
                c.execute(
                    "INSERT INTO agreements (id,room_id,terms,created_at) VALUES (?,?,?,?)",
                    (agreement_id, room["id"], json.dumps(terms, sort_keys=True), now())
                )
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        new_id("evt"),
                        room["id"],
                        agent["id"],
                        "AGREEMENT_PROPOSED",
                        json.dumps({"agreement_id": agreement_id, "terms": terms}, sort_keys=True),
                        now()
                    )
                )
                return 201, {
                    "agreement_id": agreement_id,
                    "status": "PENDING_BILATERAL_ACCEPTANCE",
                    "payment_authority": "NOT_GRANTED"
                }

            if path == "/api/v1/agreements/accept" and method == "POST":
                agent = self.agent(c)
                self.required(body, "room_id", "agreement_id")
                room = self.room(c, body["room_id"], agent["id"])
                agreement = c.execute(
                    "SELECT * FROM agreements WHERE id=? AND room_id=?",
                    (body["agreement_id"], room["id"])
                ).fetchone()
                if agreement is None:
                    raise APIError(404, "AGREEMENT_NOT_FOUND")
                column = "buyer_accepted" if agent["id"] == room["buyer"] else "seller_accepted"
                c.execute(
                    f"UPDATE agreements SET {column}=1 WHERE id=?",
                    (agreement["id"],)
                )
                updated = c.execute(
                    "SELECT * FROM agreements WHERE id=?",
                    (agreement["id"],)
                ).fetchone()
                agreed = bool(updated["buyer_accepted"] and updated["seller_accepted"])
                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        new_id("evt"),
                        room["id"],
                        agent["id"],
                        "AGREEMENT_ACCEPTED",
                        json.dumps({"agreement_id": agreement["id"], "status": "AGREED" if agreed else "AWAITING_COUNTERPARTY"}, sort_keys=True),
                        now()
                    )
                )
                return 200, {
                    "agreement_id": agreement["id"],
                    "status": "AGREED" if agreed else "AWAITING_COUNTERPARTY",
                    "payment_authority": "NOT_GRANTED"
                }

            if path == "/api/v1/demo/actions/execute" and method == "POST":
                if os.environ.get("CLOUDLINE_LOCAL_DEMO") != "1":
                    raise APIError(404, "ENDPOINT_NOT_FOUND")

                agent = self.agent(c)
                self.required(body, "room_id", "demo_authorization")

                from partner_action_bridge import (
                    prepare_action, run_demo_action, BridgeDenied
                )
                from action_gate import Permit, Denied
                from datetime import timedelta

                try:
                    prepared = prepare_action(
                        c, agent["id"], body["room_id"]
                    )
                except BridgeDenied as exc:
                    raise APIError(403, str(exc))

                action = prepared.action

                if (
                    action.action != "demo_service_delivery"
                    or action.network != "local-demo"
                    or action.asset != "demo-unit"
                    or action.amount_units != 0
                ):
                    raise APIError(403, "DEMO_ACTION_ONLY")

                configured = os.environ.get(
                    "CLOUDLINE_DEMO_AUTHORIZATION", ""
                )
                supplied = body["demo_authorization"]

                def verifier(candidate):
                    if (
                        not configured
                        or len(configured) < 32
                        or not hmac.compare_digest(configured, supplied)
                    ):
                        raise Denied("DEMO_AUTHORIZATION_DENIED")

                    return Permit(
                        action_digest=candidate.digest(),
                        evidence_ref="LOCAL_DEMO_AUTHORIZATION_ONLY",
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(seconds=30)
                    )

                def sign(candidate):
                    return {
                        "type": "LOCAL_DEMO_ACTION",
                        "action_digest": candidate.digest()
                    }

                def submit(signed):
                    if signed["type"] != "LOCAL_DEMO_ACTION":
                        raise RuntimeError("Invalid demo action")
                    # No network call or payment submission.
                    return None

                result = run_demo_action(
                    c,
                    agent["id"],
                    body["room_id"],
                    DB_PATH.parent / "partner_demo_gate.sqlite",
                    verifier=verifier,
                    sign=sign,
                    submit=submit
                )

                return 200, {
                    "demo": True,
                    "result": result,
                    "payment_submitted": False,
                    "settlement_verified": False
                }

            if path == "/api/v1/actions/check" and method == "POST":
                agent = self.agent(c)
                self.required(body, "room_id", "action")
                self.room(c, body["room_id"], agent["id"])
                room = self.room(c, body["room_id"], agent["id"])

                reason = "AUTHORITY_VERIFIER_NOT_CONNECTED"

                if room["status"] != "OPEN":
                    reason = "ROOM_NOT_OPEN"
                elif agent["id"] != room["buyer"]:
                    reason = "ACTOR_NOT_AUTHENTICATED_BUYER"
                else:
                    agreement = c.execute(
                        "SELECT * FROM agreements WHERE room_id=?",
                        (room["id"],)
                    ).fetchone()

                    if agreement is None:
                        reason = "AGREEMENT_NOT_FOUND"
                    elif (
                        not agreement["buyer_accepted"]
                        or not agreement["seller_accepted"]
                    ):
                        reason = "AGREEMENT_NOT_ACCEPTED"
                    elif body.get("agreement_id") != agreement["id"]:
                        reason = "AGREEMENT_ID_MISMATCH"
                    else:
                        import hashlib

                        terms = json.loads(agreement["terms"])
                        canonical = json.dumps(
                            terms,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False
                        )
                        expected_hash = hashlib.sha256(
                            canonical.encode()
                        ).hexdigest()

                        if body.get("terms_hash") != expected_hash:
                            reason = "AGREEMENT_TERMS_MISMATCH"

                c.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?)",
                    (
                        new_id("evt"),
                        room["id"],
                        agent["id"],
                        "ACTION_BLOCKED",
                        json.dumps({
                            "action": body["action"],
                            "reason": reason
                        }, sort_keys=True),
                        now()
                    )
                )

                return 200, {
                    "authorized": False,
                    "decision": "DENY",
                    "reason": reason,
                    "action": body["action"],
                    "execution_permitted": False,
                    "payment_submitted": False
                }

            raise APIError(404, "ENDPOINT_NOT_FOUND")

    def dispatch(self, method):
        if self.headers.get("Host") != f"{HOST}:{PORT}":
            return self.reply(403, {"error": "INVALID_HOST"})
        try:
            status, result = self.handle_api(method)
            self.reply(status, result)
        except APIError as exc:
            self.reply(exc.status, {"error": exc.code})
        except (sqlite3.Error, OSError):
            self.reply(500, {"error": "INTERNAL_ERROR"})

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

if __name__ == "__main__":
    initialize()
    print(f"cloudline Partner API listening on http://{HOST}:{PORT}", flush=True)
    HTTPServer((HOST, PORT), Handler).serve_forever()
