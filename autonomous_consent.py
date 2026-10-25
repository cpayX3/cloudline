"""Persistent, bilateral, room-scoped autonomous negotiation consent."""

from datetime import datetime, timezone


class AutonomousConsent:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_consent (
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (room_id, address)
            )
        """)
        self.db.commit()

    def set(self, room_id, address, enabled):
        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("NOT_ROOM_PARTICIPANT")

        if type(enabled) is not bool:
            raise ValueError("INVALID_AUTONOMOUS_CONSENT")

        with self.db:
            self.db.execute("""
                INSERT INTO autonomous_consent
                    (room_id, address, enabled, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room_id, address)
                DO UPDATE SET
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
            """, (
                room_id,
                address,
                int(enabled),
                datetime.now(timezone.utc).isoformat()
            ))

        return {
            "room_id": room_id,
            "address": address,
            "autonomous_negotiation": enabled,
            "payment_authority": "NOT_GRANTED"
        }

    def require_bilateral(self, room_id):
        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        for address in (room["buyer"], room["seller"]):
            row = self.db.execute("""
                SELECT enabled FROM autonomous_consent
                WHERE room_id=? AND address=?
            """, (room_id, address)).fetchone()

            if row is None or row[0] != 1:
                raise PermissionError("BILATERAL_AUTONOMOUS_CONSENT_REQUIRED")

        return True
