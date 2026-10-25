import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from room_core import RoomStore
from negotiation import Negotiation
from action_gate import Action, ActionGate, Permit
from agreement_verifier import AgreementVerifier


class AgreementVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.tmp.name) / "test.db")
        self.room = self.store.request_room(
            "buyer", "hunter", "wallet report"
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (self.room,)
            )

        self.n = Negotiation(self.store)
        self.terms = {
            "service": "wallet-vibe-check",
            "resource": "rExampleWallet",
            "network": "xrpl:0",
            "asset": "RLUSD",
            "recipient": "rExampleSeller",
            "amount_units": 100000,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()
        }
        self.offer = self.n.offer(
            self.room, "hunter", self.terms
        )
        self.digest = self.n.get(self.offer)["terms_hash"]

        self.action = Action(
            self.room, "buyer", self.offer, self.digest,
            "purchase", self.terms["resource"],
            self.terms["network"], self.terms["asset"],
            self.terms["recipient"], self.terms["amount_units"]
        )
        self.sign = Mock(return_value="fixture-signed")
        self.submit = Mock()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def agree(self):
        self.n.accept(
            self.room, "buyer", self.offer, self.digest
        )
        self.n.accept(
            self.room, "hunter", self.offer, self.digest
        )

    def execute(self, authority=None, action=None):
        verifier = AgreementVerifier(self.store, authority)
        gate = ActionGate(self.store, verifier)
        return gate.execute(
            action or self.action, "buyer",
            sign=self.sign, submit=self.submit
        )

    def fixture_authority(self, action, terms):
        return Permit(
            action.digest(), "TEST_ONLY_NOT_REAL_AUTHORITY",
            datetime.now(timezone.utc) + timedelta(minutes=1)
        )

    def test_unaccepted_agreement_blocks(self):
        result = self.execute(self.fixture_authority)
        self.assertEqual(
            result["reason"], "AGREEMENT_NOT_ACCEPTED"
        )
        self.submit.assert_not_called()

    def test_agreed_but_no_authority_blocks(self):
        self.agree()
        result = self.execute()
        self.assertEqual(
            result["reason"],
            "AUTHORITY_VERIFIER_NOT_CONNECTED"
        )
        self.submit.assert_not_called()

    def test_changed_payment_terms_block(self):
        self.agree()
        changes = (
            {"amount_units": 200000},
            {"recipient": "different"},
            {"asset": "XRP"},
            {"network": "other"},
            {"resource": "other"},
            {"action": "transfer"},
            {"terms_hash": "b" * 64},
        )
        for change in changes:
            with self.subTest(change=change):
                result = self.execute(
                    self.fixture_authority,
                    replace(self.action, **change)
                )
                self.assertEqual(result["status"], "BLOCKED")
                self.submit.assert_not_called()

    def test_valid_fixture_submits_not_settles(self):
        self.agree()
        result = self.execute(self.fixture_authority)
        self.assertEqual(result["status"], "SUBMITTED")
        self.submit.assert_called_once()
        kinds = [
            e["kind"] for e in self.store.events(self.room)
        ]
        self.assertNotIn("SETTLED", kinds)

    def test_missing_bilateral_acceptance_blocks(self):
        self.agree()
        with self.store.db:
            self.store.db.execute("""
                DELETE FROM negotiation_acceptances
                WHERE offer_id=? AND actor='buyer'
            """, (self.offer,))
        result = self.execute(self.fixture_authority)
        self.assertEqual(
            result["reason"],
            "BILATERAL_ACCEPTANCE_MISSING"
        )

    def test_cross_room_agreement_blocks(self):
        self.agree()
        other = self.store.request_room(
            "buyer", "hunter", "different report"
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (other,)
            )
        changed = replace(self.action, room_id=other)
        result = self.execute(
            self.fixture_authority, changed
        )
        self.assertEqual(
            result["reason"], "AGREEMENT_ROOM_MISMATCH"
        )

    def test_authority_denial_blocks(self):
        self.agree()
        from action_gate import Denied

        def deny(action, terms):
            raise Denied("BUDGET_EXCEEDED")

        result = self.execute(deny)
        self.assertEqual(
            result["reason"], "BUDGET_EXCEEDED"
        )
        self.sign.assert_not_called()
        self.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
