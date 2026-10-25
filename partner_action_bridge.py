"""Isolated bridge from Partner API records to ActionGate.

No live payment signer, payment submission, or Mastercard verifier.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from action_gate import Action, ActionGate
from room_core import RoomStore


class BridgeDenied(Exception):
    pass


@dataclass(frozen=True)
class PreparedAction:
    action: Action
    agreement_id: str


def canonical_hash(value):
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def prepare_action(connection, authenticated_agent_id, room_id):
    """All identities and agreement terms come from trusted DB records."""

    room = connection.execute(
        "SELECT * FROM rooms WHERE id=?",
        (room_id,)
    ).fetchone()

    if room is None:
        raise BridgeDenied("ROOM_NOT_FOUND")

    if room["status"] != "OPEN":
        raise BridgeDenied("ROOM_NOT_OPEN")

    if authenticated_agent_id != room["buyer"]:
        raise BridgeDenied("ACTOR_NOT_AUTHENTICATED_BUYER")

    agreement = connection.execute(
        "SELECT * FROM agreements WHERE room_id=?",
        (room_id,)
    ).fetchone()

    if agreement is None:
        raise BridgeDenied("AGREEMENT_NOT_FOUND")

    if not (
        agreement["buyer_accepted"]
        and agreement["seller_accepted"]
    ):
        raise BridgeDenied("AGREEMENT_NOT_ACCEPTED")

    terms = json.loads(agreement["terms"])

    # Demo terms are intentionally explicit.
    required = (
        "action",
        "resource",
        "network",
        "asset",
        "recipient",
        "amount_units"
    )

    if any(k not in terms for k in required):
        raise BridgeDenied("INCOMPLETE_ACTION_TERMS")

    if (
        type(terms["amount_units"]) is not int
        or terms["amount_units"] < 0
    ):
        raise BridgeDenied("INVALID_AMOUNT")

    try:
        action = Action(
            room_id=room_id,
            actor=authenticated_agent_id,
            agreement_id=agreement["id"],
            terms_hash=canonical_hash(terms),
            action=terms["action"],
            resource=terms["resource"],
            network=terms["network"],
            asset=terms["asset"],
            recipient=terms["recipient"],
            amount_units=terms["amount_units"]
        )
        action.digest()
    except (ValueError, TypeError):
        raise BridgeDenied("INVALID_ACTION_TERMS")

    return PreparedAction(action, agreement["id"])


class PartnerGateStore:
    """Adapter for ActionGate using a separate, private SQLite database."""

    def __init__(self, database):
        self._store = RoomStore(database)
        self.db = self._store.db

    def ensure_room(self, action):
        room = self._store.get_room(action.room_id) if self._exists(
            action.room_id
        ) else None

        if room is None:
            with self.db:
                self.db.execute(
                    """INSERT INTO rooms
                       (id,buyer,seller,purpose,state)
                       VALUES (?,?,?,?,?)""",
                    (
                        action.room_id,
                        action.actor,
                        "partner-counterparty",
                        "Partner API authorization",
                        "OPEN"
                    )
                )
        elif room["buyer"] != action.actor:
            raise BridgeDenied("GATE_ROOM_IDENTITY_MISMATCH")
        elif room["state"] != "OPEN":
            raise BridgeDenied("GATE_ROOM_NOT_OPEN")

    def _exists(self, room_id):
        return self.db.execute(
            "SELECT 1 FROM rooms WHERE id=?",
            (room_id,)
        ).fetchone() is not None

    def get_room(self, room_id):
        return self._store.get_room(room_id)

    def close(self):
        self._store.close()


def run_demo_action(
    connection,
    authenticated_agent_id,
    room_id,
    gate_database,
    verifier,
    sign,
    submit
):
    """Only backend-supplied verifier/sign/submit functions are accepted."""

    prepared = prepare_action(
        connection,
        authenticated_agent_id,
        room_id
    )

    store = PartnerGateStore(gate_database)

    try:
        store.ensure_room(prepared.action)

        gate = ActionGate(store, verifier)

        return gate.execute(
            prepared.action,
            authenticated_agent_id,
            sign=sign,
            submit=submit
        )
    finally:
        store.close()
