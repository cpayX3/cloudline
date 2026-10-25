"""Cryptographic admission for bilateral cloudline rooms."""

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from wallet_identity import verify_wallet_signature


class RoomAdmission:
    def __init__(self, store):
        self.store = store
        self.db = store.db

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS admission_challenges (
                challenge_id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                message TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0
            )
        """)

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS admission_verified (
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                PRIMARY KEY (room_id, address)
            )
        """)

        self.db.commit()

    def challenge(self, room_id, address):
        room = self.store.get_room(room_id)

        if room["state"] != "AWAITING_VERIFICATION":
            raise PermissionError("ROOM_NOT_AWAITING_VERIFICATION")

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("ADDRESS_NOT_REGISTERED")

        challenge_id = secrets.token_hex(24)
        expires = datetime.now(timezone.utc) + timedelta(minutes=5)

        message = (
            "cloudline room admission\n"
            f"Room: {room_id}\n"
            f"Wallet: {address}\n"
            f"Challenge: {challenge_id}\n"
            f"Expires: {expires.isoformat()}"
        )

        with self.db:
            self.db.execute("""
                INSERT INTO admission_challenges
                (challenge_id, room_id, address, message, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                challenge_id, room_id, address,
                message, expires.isoformat()
            ))

        return {
            "challenge_id": challenge_id,
            "message": message,
            "expires_at": expires.isoformat()
        }

    def verify(self, room_id, address, challenge_id, signature):
        if not all(
            isinstance(v, str) and v
            for v in (room_id, address, challenge_id, signature)
        ):
            raise ValueError("INVALID_ADMISSION_PROOF")

        room = self.store.get_room(room_id)

        if room["state"] != "AWAITING_VERIFICATION":
            raise PermissionError("ROOM_NOT_AWAITING_VERIFICATION")

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("ADDRESS_NOT_REGISTERED")

        record = self.db.execute("""
            SELECT message, expires_at, consumed
            FROM admission_challenges
            WHERE challenge_id=? AND room_id=? AND address=?
        """, (challenge_id, room_id, address)).fetchone()

        if record is None:
            raise PermissionError("CHALLENGE_NOT_FOUND")

        message, expiry, consumed = record

        if consumed:
            raise PermissionError("CHALLENGE_ALREADY_USED")

        if datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
            raise PermissionError("CHALLENGE_EXPIRED")

        if not verify_wallet_signature(address, message, signature):
            raise PermissionError("INVALID_WALLET_SIGNATURE")

        now = datetime.now(timezone.utc).isoformat()

        try:
            with self.db:
                updated = self.db.execute("""
                    UPDATE admission_challenges
                    SET consumed=1
                    WHERE challenge_id=? AND consumed=0
                """, (challenge_id,)).rowcount

                if updated != 1:
                    raise PermissionError("CHALLENGE_ALREADY_USED")

                self.db.execute("""
                    INSERT INTO admission_verified
                    (room_id, address, verified_at)
                    VALUES (?, ?, ?)
                """, (room_id, address, now))

                verified = {
                    row[0] for row in self.db.execute("""
                        SELECT address FROM admission_verified
                        WHERE room_id=?
                    """, (room_id,))
                }

                opened = verified == {room["buyer"], room["seller"]}

                if opened:
                    updated = self.db.execute("""
                        UPDATE rooms SET state='OPEN'
                        WHERE id=? AND state='AWAITING_VERIFICATION'
                    """, (room_id,)).rowcount
                    if updated != 1:
                        raise PermissionError("ROOM_STATE_CHANGED")

                import json
                self.db.execute("""
                    INSERT INTO events
                    (room_id, occurred_at, kind, payload)
                    VALUES (?, ?, ?, ?)
                """, (
                    room_id,
                    now,
                    "ROOM_OPENED" if opened else "AGENT_VERIFIED",
                    json.dumps({
                        "address": address,
                        "authentication": "EVM_PERSONAL_SIGN",
                        "payment_authority": "NOT_GRANTED"
                    })
                ))

        except sqlite3.IntegrityError:
            raise PermissionError("ALREADY_VERIFIED")

        return {
            "status": "OPEN" if opened else "AWAITING_COUNTERPARTY",
            "address": address,
            "payment_authority": "NOT_GRANTED"
        }
