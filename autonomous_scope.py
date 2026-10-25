"""Bilateral authorization of immutable autonomous negotiation scope."""

import hashlib
import json
from datetime import datetime, timezone


FIELDS = ("service", "resource", "network", "asset", "recipient")


def canonical_scope(scope):
    if not isinstance(scope, dict):
        raise ValueError("INVALID_SCOPE")

    if set(scope) != set(FIELDS):
        raise ValueError("INVALID_SCOPE_FIELDS")

    for field in FIELDS:
        value = scope[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("INVALID_SCOPE_VALUE")

        if len(value) > 512:
            raise ValueError("SCOPE_VALUE_TOO_LONG")

    if scope["network"] != "xrpl:0":
        raise PermissionError("UNSUPPORTED_NETWORK")

    if scope["asset"] not in ("XRP", "RLUSD", "USDC"):
        raise PermissionError("UNSUPPORTED_ASSET")

    return json.dumps(
        scope, sort_keys=True, separators=(",", ":")
    )


def scope_hash(scope):
    return hashlib.sha256(
        canonical_scope(scope).encode()
    ).hexdigest()


class AutonomousScope:
    def __init__(self, store):
        self.store = store
        self.db = store.db

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS autonomous_scope (
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                scope_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (room_id, address)
            )
        """)
        self.db.commit()

    def authorize(self, room_id, address, scope):
        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("NOT_ROOM_PARTICIPANT")

        encoded = canonical_scope(scope)
        digest = hashlib.sha256(encoded.encode()).hexdigest()

        existing_offer = self.db.execute(
            "SELECT 1 FROM negotiation_offers WHERE room_id=? LIMIT 1",
            (room_id,)
        ).fetchone()

        if existing_offer:
            raise PermissionError("NEGOTIATION_ALREADY_STARTED")

        with self.db:
            self.db.execute("""
                INSERT INTO autonomous_scope
                    (room_id, address, scope_json, scope_hash, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(room_id, address)
                DO UPDATE SET
                    scope_json=excluded.scope_json,
                    scope_hash=excluded.scope_hash,
                    updated_at=excluded.updated_at
            """, (
                room_id,
                address,
                encoded,
                digest,
                datetime.now(timezone.utc).isoformat()
            ))

        return {
            "room_id": room_id,
            "scope_hash": digest,
            "authorized": True,
            "payment_authority": "NOT_GRANTED"
        }

    def require_bilateral(self, room_id, scope):
        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        expected = scope_hash(scope)

        for address in (room["buyer"], room["seller"]):
            row = self.db.execute("""
                SELECT scope_hash FROM autonomous_scope
                WHERE room_id=? AND address=?
            """, (room_id, address)).fetchone()

            if row is None or row[0] != expected:
                raise PermissionError(
                    "BILATERAL_SCOPE_AUTHORIZATION_REQUIRED"
                )

        return True
