"""Internal execution boundary. Default denies.
The trusted verifier must check identity, exact agreement, scope,
current authority, revocation, and budget before returning a Permit.
No live Mastercard verification is implemented here.
"""
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Action:
    room_id: str
    actor: str
    agreement_id: str
    terms_hash: str
    action: str
    resource: str
    network: str
    asset: str
    recipient: str
    amount_units: int

    def digest(self):
        for name, value in asdict(self).items():
            if name == "amount_units":
                if type(value) is not int or value < 0:
                    raise ValueError("amount_units must be a nonnegative integer")
            elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise ValueError("Invalid action field: " + name)

        if len(self.terms_hash) != 64 or any(
            c not in "0123456789abcdef" for c in self.terms_hash
        ):
            raise ValueError("terms_hash must be a lowercase SHA-256 digest")

        encoded = json.dumps(
            asdict(self), sort_keys=True,
            separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Permit:
    action_digest: str
    evidence_ref: str
    expires_at: datetime


class Denied(Exception):
    pass


def deny_by_default(action):
    raise Denied("AUTHORITY_VERIFIER_NOT_CONNECTED")


class ActionGate:
    def __init__(self, store, verifier=deny_by_default):
        self.store = store
        self.verifier = verifier
        self.store.db.execute("""
            CREATE TABLE IF NOT EXISTS action_attempts (
                digest TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                state TEXT NOT NULL
            )
        """)
        self.store.db.commit()

    def _event(self, action, kind, reason, evidence_ref=None):
        self.store.db.execute("""
            INSERT INTO events
            (room_id, occurred_at, kind, payload)
            VALUES (?, ?, ?, ?)
        """, (
            action.room_id,
            datetime.now(timezone.utc).isoformat(),
            kind,
            json.dumps({
                "action": asdict(action),
                "reason": reason,
                "evidence_ref": evidence_ref
            })
        ))

    def _block(self, action, reason):
        with self.store.db:
            self._event(action, "ACTION_BLOCKED", reason)
        return {"status": "BLOCKED", "reason": reason}

    def execute(self, action, authenticated_actor, *, sign, submit):
        """Internal only; authenticated_actor must come from authentication.
        sign and submit are backend functions, never client-selected.
        Submission is not proof of validated settlement.
        """
        digest = action.digest()
        room = self.store.get_room(action.room_id)

        if room["state"] != "OPEN":
            return self._block(action, "ROOM_NOT_OPEN")

        if authenticated_actor != action.actor or action.actor != room["buyer"]:
            return self._block(action, "ACTOR_NOT_AUTHENTICATED_BUYER")

        try:
            permit = self.verifier(action)
        except Denied as exc:
            reason = str(exc)
            if (
                not reason or len(reason) > 100
                or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in reason)
            ):
                reason = "AUTHORITY_DENIED"
            return self._block(action, reason)
        except Exception:
            return self._block(action, "VERIFICATION_UNAVAILABLE")

        if not isinstance(permit, Permit) or permit.action_digest != digest:
            return self._block(action, "INVALID_OR_MISMATCHED_VERIFICATION")

        if not isinstance(permit.evidence_ref, str) or not permit.evidence_ref.strip():
            return self._block(action, "MISSING_VERIFICATION_EVIDENCE")

        expiry = permit.expires_at
        if (
            not isinstance(expiry, datetime)
            or expiry.tzinfo is None
            or expiry.utcoffset() is None
        ):
            return self._block(action, "INVALID_AUTHORITY_EXPIRY")

        if expiry <= datetime.now(timezone.utc):
            return self._block(action, "AUTHORITY_EXPIRED")

        # Reserve before signing. The unique record survives restarts.
        try:
            with self.store.db:
                self.store.db.execute(
                    "INSERT INTO action_attempts VALUES (?, ?, ?)",
                    (digest, action.room_id, "RESERVED")
                )
                self._event(
                    action, "ACTION_AUTHORIZED",
                    "VERIFIED_FOR_EXECUTION", permit.evidence_ref
                )
        except sqlite3.IntegrityError:
            return self._block(action, "DUPLICATE_OR_UNRESOLVED_ATTEMPT")

        try:
            signed = sign(action)
            submit(signed)
        except Exception:
            with self.store.db:
                self.store.db.execute(
                    "UPDATE action_attempts SET state=? WHERE digest=?",
                    ("RECONCILIATION_REQUIRED", digest)
                )
                self._event(
                    action, "ACTION_RECONCILIATION_REQUIRED",
                    "EXECUTION_OUTCOME_UNCERTAIN"
                )
            return {"status": "RECONCILIATION_REQUIRED"}

        with self.store.db:
            self.store.db.execute(
                "UPDATE action_attempts SET state=? WHERE digest=?",
                ("SUBMITTED", digest)
            )
            self._event(
                action, "ACTION_SUBMITTED",
                "SETTLEMENT_NOT_YET_VERIFIED"
            )

        return {"status": "SUBMITTED"}
