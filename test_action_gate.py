import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from action_gate import Action, ActionGate, Permit, Denied
from room_core import RoomStore
from conversation_bridge import ConversationBridge


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite"
        self.store = RoomStore(self.path)
        self.room = self.store.request_room("buyer", "hunter", "wallet report")

        # Test fixture only. Never changes the application's real database.
        with self.store.db:
            self.store.db.execute("UPDATE rooms SET state='OPEN'")

        self.action = Action(
            self.room, "buyer", "agreement_test", "a" * 64,
            "purchase", "wallet-vibe-check",
            "test-network", "test-asset", "test-seller", 10
        )
        self.sign = Mock(return_value="fake-signed-payload")
        self.submit = Mock()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def permit(self, action):
        # Test fixture, not a real verification adapter.
        return Permit(
            action.digest(), "fixture-evidence",
            datetime.now(timezone.utc) + timedelta(minutes=1)
        )

    def run_gate(self, verifier=None, action=None, actor="buyer"):
        gate = (
            ActionGate(self.store) if verifier is None
            else ActionGate(self.store, verifier)
        )
        return gate.execute(
            action or self.action, actor,
            sign=self.sign, submit=self.submit
        )

    def blocked(self, result, reason):
        self.assertEqual(result, {"status": "BLOCKED", "reason": reason})
        self.sign.assert_not_called()
        self.submit.assert_not_called()

    def test_no_authority_blocks_but_conversation_continues(self):
        self.blocked(
            self.run_gate(), "AUTHORITY_VERIFIER_NOT_CONNECTED"
        )
        ConversationBridge(self.store).receive(
            self.room, "buyer", "Please ask my operator."
        )
        events = self.store.events(self.room)
        self.assertEqual(events[-2]["kind"], "ACTION_BLOCKED")
        self.assertEqual(events[-1]["kind"], "MESSAGE")
        self.assertEqual(self.store.get_room(self.room)["state"], "OPEN")

    def test_client_verified_flag_is_not_a_permit(self):
        self.blocked(
            self.run_gate(lambda a: {"verified": True}),
            "INVALID_OR_MISMATCHED_VERIFICATION"
        )

    def test_expired_authority(self):
        self.blocked(
            self.run_gate(lambda a: replace(
                self.permit(a),
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
            )),
            "AUTHORITY_EXPIRED"
        )

    def test_changed_terms_recipient_network_asset_or_price(self):
        original = self.permit(self.action)
        changes_list = (
            {"terms_hash": "b" * 64},
            {"recipient": "other"},
            {"network": "other"},
            {"asset": "other"},
            {"amount_units": 11},
            {"action": "transfer"},
        )
        for changes in changes_list:
            with self.subTest(changes=changes):
                self.blocked(
                    self.run_gate(
                        lambda a: original,
                        replace(self.action, **changes)
                    ),
                    "INVALID_OR_MISMATCHED_VERIFICATION"
                )

    def test_verifier_denials_and_unavailability(self):
        for reason in (
            "BUDGET_EXCEEDED", "AUTHORITY_REVOKED",
            "AGREEMENT_NOT_ACCEPTED", "ACTION_OUT_OF_SCOPE"
        ):
            def deny(a):
                raise Denied(reason)

            self.blocked(self.run_gate(deny), reason)

        def unavailable(a):
            raise RuntimeError("private upstream detail")

        self.blocked(
            self.run_gate(unavailable), "VERIFICATION_UNAVAILABLE"
        )

    def test_pending_room_and_wrong_identity(self):
        self.blocked(
            self.run_gate(self.permit, actor="outsider"),
            "ACTOR_NOT_AUTHENTICATED_BUYER"
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='AWAITING_VERIFICATION'"
            )
        self.blocked(self.run_gate(self.permit), "ROOM_NOT_OPEN")

    def test_allowed_runs_once_even_after_restart(self):
        self.assertEqual(
            self.run_gate(self.permit), {"status": "SUBMITTED"}
        )
        self.sign.assert_called_once_with(self.action)
        self.submit.assert_called_once_with("fake-signed-payload")

        self.store.close()
        self.store = RoomStore(self.path)
        self.sign.reset_mock()
        self.submit.reset_mock()

        self.blocked(
            self.run_gate(self.permit),
            "DUPLICATE_OR_UNRESOLVED_ATTEMPT"
        )
        self.assertNotIn(
            "SETTLED", [e["kind"] for e in self.store.events(self.room)]
        )

    def test_uncertain_submission_cannot_retry(self):
        self.submit.side_effect = TimeoutError()
        self.assertEqual(
            self.run_gate(self.permit),
            {"status": "RECONCILIATION_REQUIRED"}
        )
        self.sign.reset_mock()
        self.submit.reset_mock()
        self.blocked(
            self.run_gate(self.permit),
            "DUPLICATE_OR_UNRESOLVED_ATTEMPT"
        )

    def test_float_and_negative_amount_rejected(self):
        for amount in (1.5, -1, True):
            with self.assertRaises(ValueError):
                self.run_gate(
                    self.permit,
                    replace(self.action, amount_units=amount)
                )
        self.sign.assert_not_called()
        self.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
