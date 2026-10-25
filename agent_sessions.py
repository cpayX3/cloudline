"""Wallet-authenticated, room-scoped negotiation sessions."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone


class AgentSessions:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS agent_sessions (
                token_hash TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                address TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.db.commit()

    def issue(self, room_id, address):
        room = self.store.get_room(room_id)

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("NOT_PARTICIPANT")

        verified = self.db.execute("""
            SELECT 1 FROM admission_verified
            WHERE room_id=? AND address=?
        """, (room_id, address)).fetchone()

        if not verified:
            raise PermissionError("IDENTITY_NOT_VERIFIED")

        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        expiry = (
            datetime.now(timezone.utc) + timedelta(minutes=30)
        ).isoformat()

        with self.db:
            self.db.execute("""
                INSERT INTO agent_sessions
                (token_hash, room_id, address, expires_at)
                VALUES (?, ?, ?, ?)
            """, (digest, room_id, address, expiry))

        return {"token": token, "expires_at": expiry}

    def authenticate(self, room_id, authorization):
        if not isinstance(authorization, str):
            raise PermissionError("SESSION_REQUIRED")

        if not authorization.startswith("Bearer "):
            raise PermissionError("SESSION_REQUIRED")

        token = authorization[7:]

        if not 32 <= len(token) <= 256:
            raise PermissionError("INVALID_SESSION")

        digest = hashlib.sha256(token.encode()).hexdigest()

        row = self.db.execute("""
            SELECT address, expires_at, revoked
            FROM agent_sessions
            WHERE token_hash=? AND room_id=?
        """, (digest, room_id)).fetchone()

        if row is None:
            raise PermissionError("INVALID_SESSION")

        address, expiry, revoked = row

        if revoked or datetime.fromisoformat(expiry) <= datetime.now(timezone.utc):
            raise PermissionError("SESSION_EXPIRED_OR_REVOKED")

        room = self.store.get_room(room_id)

        if room["state"] != "OPEN":
            raise PermissionError("ROOM_NOT_OPEN")

        if address not in (room["buyer"], room["seller"]):
            raise PermissionError("NOT_PARTICIPANT")

        return address

    def revoke(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()

        with self.db:
            self.db.execute("""
                UPDATE agent_sessions
                SET revoked=1
                WHERE token_hash=?
            """, (digest,))
