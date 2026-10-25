import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

class RoomStore:
    """Persistent admission requests. Authentication adapter comes next."""

    def __init__(self, database):
        self.db = sqlite3.connect(database)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                buyer TEXT NOT NULL,
                seller TEXT NOT NULL,
                purpose TEXT NOT NULL,
                state TEXT NOT NULL
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """)
        self.db.commit()

    def request_room(self, buyer, seller, purpose):
        fields = (buyer, seller, purpose)
        if any(not isinstance(v, str) or not v.strip() for v in fields):
            raise ValueError("Buyer, seller, and purpose are required")
        if any(len(v) > 2000 for v in fields):
            raise ValueError("Admission field exceeds length limit")
        if buyer.strip() == seller.strip():
            raise ValueError("Buyer and seller must be separate identities")

        room_id = "room_" + uuid4().hex
        event = {
            "claimed_buyer": buyer.strip(),
            "claimed_seller": seller.strip(),
            "purpose": purpose.strip(),
            "identity": "UNVERIFIED",
            "authority": "UNVERIFIED",
            "payment_adapter": "mastercard_ap4m",
            "reason": "Waiting for authenticated admission verification"
        }

        with self.db:
            self.db.execute(
                "INSERT INTO rooms VALUES (?, ?, ?, ?, ?)",
                (room_id, buyer.strip(), seller.strip(),
                 purpose.strip(), "AWAITING_VERIFICATION")
            )
            self.db.execute(
                """INSERT INTO events
                   (room_id, occurred_at, kind, payload)
                   VALUES (?, ?, ?, ?)""",
                (room_id, datetime.now(timezone.utc).isoformat(),
                 "ROOM_REQUESTED", json.dumps(event))
            )
        return room_id

    def get_room(self, room_id):
        row = self.db.execute(
            "SELECT id, buyer, seller, purpose, state FROM rooms WHERE id=?",
            (room_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Room not found")
        return dict(zip(("id", "buyer", "seller", "purpose", "state"), row))

    def events(self, room_id):
        self.get_room(room_id)
        rows = self.db.execute(
            """SELECT sequence, occurred_at, kind, payload FROM events
               WHERE room_id=? ORDER BY sequence""", (room_id,)
        )
        return [
            {"sequence": seq, "at": at, "kind": kind,
             "payload": json.loads(payload)}
            for seq, at, kind, payload in rows
        ]


    def record_greeting(self, room_id, authenticated_agent, text):
        """Internal service method; caller identity must come from authentication.
        Never pass a client-supplied sender name here.
        No HTTP write route is exposed until authentication is integrated.
        """
        room = self.get_room(room_id)
        if room["state"] != "OPEN":
            raise PermissionError("Room admission is not complete")
        if authenticated_agent not in (room["buyer"], room["seller"]):
            raise PermissionError("Agent is not a room participant")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("Greeting must contain 1–4000 characters")

        payload = {
            "sender": authenticated_agent,
            "text": text.strip(),
            "intent": "greet"
        }
        with self.db:
            cursor = self.db.execute(
                """INSERT INTO events
                   (room_id, occurred_at, kind, payload)
                   VALUES (?, ?, ?, ?)""",
                (room_id, datetime.now(timezone.utc).isoformat(),
                 "GREETING", json.dumps(payload))
            )
        return cursor.lastrowid

    def close(self):
        self.db.close()
