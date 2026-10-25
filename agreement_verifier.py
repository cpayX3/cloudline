"""Bind an Action to a bilateral agreement before authority checks.

Internal-only adapter. No live Mastercard or XRPL integration.
"""
from datetime import datetime, timezone

from action_gate import Denied, Permit
from negotiation import Negotiation


class AgreementVerifier:
    def __init__(self, store, authority_verifier=None):
        self.store = store
        self.negotiation = Negotiation(store)
        self.authority_verifier = authority_verifier

    def __call__(self, action):
        room = self.store.get_room(action.room_id)

        if room["state"] != "OPEN":
            raise Denied("ROOM_NOT_OPEN")

        if action.actor != room["buyer"]:
            raise Denied("BUYER_MISMATCH")

        try:
            offer = self.negotiation.get(action.agreement_id)
        except KeyError:
            raise Denied("AGREEMENT_NOT_FOUND")

        if offer["room_id"] != action.room_id:
            raise Denied("AGREEMENT_ROOM_MISMATCH")

        if offer["state"] != "AGREED":
            raise Denied("AGREEMENT_NOT_ACCEPTED")

        if offer["terms_hash"] != action.terms_hash:
            raise Denied("AGREEMENT_HASH_MISMATCH")

        terms = offer["terms"]

        try:
            encoded, digest = self.negotiation.canonical(terms)
        except (ValueError, TypeError, OverflowError):
            raise Denied("AGREEMENT_EXPIRED_OR_INVALID")

        if digest != action.terms_hash:
            raise Denied("AGREEMENT_HASH_MISMATCH")

        # Confirm both participants accepted this exact version.
        accepted = {
            row[0]
            for row in self.store.db.execute("""
                SELECT actor FROM negotiation_acceptances
                WHERE offer_id=? AND terms_hash=?
            """, (offer["id"], action.terms_hash))
        }

        if accepted != {room["buyer"], room["seller"]}:
            raise Denied("BILATERAL_ACCEPTANCE_MISSING")

        expected = {
            "action": "purchase",
            "resource": terms["resource"],
            "network": terms["network"],
            "asset": terms["asset"],
            "recipient": terms["recipient"],
            "amount_units": terms["amount_units"],
        }

        for field, value in expected.items():
            if getattr(action, field) != value:
                raise Denied("ACTION_TERMS_MISMATCH")

        if self.authority_verifier is None:
            raise Denied("AUTHORITY_VERIFIER_NOT_CONNECTED")

        # Trusted adapter must independently check:
        # authenticated identity, signed delegation, scope,
        # service, revocation, expiry, budget and payee.
        # It must reserve budget atomically before permitting.
        permit = self.authority_verifier(action, terms)

        if not isinstance(permit, Permit):
            raise Denied("INVALID_AUTHORITY_PERMIT")

        if permit.action_digest != action.digest():
            raise Denied("AUTHORITY_ACTION_MISMATCH")

        if (
            not isinstance(permit.expires_at, datetime)
            or permit.expires_at.tzinfo is None
            or permit.expires_at.utcoffset() is None
            or permit.expires_at <= datetime.now(timezone.utc)
        ):
            raise Denied("AUTHORITY_EXPIRED")

        if not isinstance(permit.evidence_ref, str) or not permit.evidence_ref.strip():
            raise Denied("MISSING_VERIFICATION_EVIDENCE")

        return permit
