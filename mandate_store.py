"""Persistent, room-scoped negotiation mandates."""

import json
from datetime import datetime, timezone
from mandates import Mandate


class MandateStore:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS negotiation_mandates (
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                mandate_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (room_id, address)
            )
        """)
        self.db.commit()

    def role_for(self, room_id, address):
        room = self.store.get_room(room_id)

        if address == room["buyer"]:
            return "buyer"
        if address == room["seller"]:
            return "seller"

        raise PermissionError("NOT_ROOM_PARTICIPANT")

    def register(self, room_id, address, values):
        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        if not isinstance(values, dict):
            raise ValueError("INVALID_MANDATE")

        role = self.role_for(room_id, address)

        mandate = Mandate(
            role=role,
            target_units=values.get("target_units"),
            limit_units=values.get("limit_units"),
            patience=values.get("patience", 5),
            flexibility=values.get("flexibility", 50)
        )

        payload = {
            "role": mandate.role,
            "target_units": mandate.target_units,
            "limit_units": mandate.limit_units,
            "patience": mandate.patience,
            "flexibility": mandate.flexibility
        }

        with self.db:
            existing = self.db.execute("""
                SELECT 1 FROM negotiation_mandates
                WHERE room_id=? AND address=?
            """, (room_id, address)).fetchone()

            if existing:
                raise PermissionError("MANDATE_ALREADY_REGISTERED")

            offers = self.db.execute("""
                SELECT 1 FROM negotiation_offers
                WHERE room_id=? LIMIT 1
            """, (room_id,)).fetchone()

            if offers:
                raise PermissionError("NEGOTIATION_ALREADY_STARTED")

            self.db.execute("""
                INSERT INTO negotiation_mandates
                (room_id, address, mandate_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                room_id,
                address,
                json.dumps(payload, sort_keys=True),
                datetime.now(timezone.utc).isoformat()
            ))

        return payload

    def get(self, room_id, address):
        role = self.role_for(room_id, address)

        row = self.db.execute("""
            SELECT mandate_json FROM negotiation_mandates
            WHERE room_id=? AND address=?
        """, (room_id, address)).fetchone()

        if row is None:
            raise PermissionError("MANDATE_REQUIRED")

        values = json.loads(row[0])

        if values["role"] != role:
            raise PermissionError("MANDATE_ROLE_MISMATCH")

        return Mandate(**values)

    def check_amount(self, room_id, address, amount_units):
        mandate = self.get(room_id, address)

        if not mandate.permits(amount_units):
            raise PermissionError("MANDATE_PRICE_LIMIT_EXCEEDED")

        return True
