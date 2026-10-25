import tempfile
import unittest
from pathlib import Path

from room_core import RoomStore
from negotiation import Negotiation
from mandate_store import MandateStore
from negotiation_runner import run_negotiation


class NegotiationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.tmp.name) / "rooms.sqlite")
        self.negotiation = Negotiation(self.store)
        self.mandates = MandateStore(self.store)

        self.buyer = "buyer-agent"
        self.seller = "seller-agent"

        self.room_id = self.store.request_room(
            self.buyer, self.seller, "Wallet report purchase"
        )

        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (self.room_id,)
            )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def register(self, buyer_limit, seller_floor):
        self.mandates.register(self.room_id, self.buyer, {
            "target_units": 15,
            "limit_units": buyer_limit
        })

        self.mandates.register(self.room_id, self.seller, {
            "target_units": 40,
            "limit_units": seller_floor
        })

    # RUNNER_CONSENT_TESTS_V1
    def consent_both(self):
        from autonomous_consent import AutonomousConsent
        consent = AutonomousConsent(self.store)
        consent.set(self.room_id, self.buyer, True)
        consent.set(self.room_id, self.seller, True)

    def test_missing_consent_blocks_runner(self):
        self.register(35, 30)
        with self.assertRaisesRegex(
            PermissionError, "BILATERAL_AUTONOMOUS_CONSENT_REQUIRED"
        ):
            self.execute()

    def test_repeat_run_is_blocked(self):
        self.register(35, 30)
        self.consent_both()
        self.execute()
        with self.assertRaisesRegex(
            PermissionError, "NEGOTIATION_ALREADY_STARTED"
        ):
            self.execute()

    def execute(self):
        return run_negotiation(
            self.store,
            self.negotiation,
            self.mandates,
            self.room_id,
            "wallet-report",
            "/agent/v3/wallet-vibe-check",
            "xrpl:0",
            "RLUSD",
            "seller-wallet"
        )

    def test_authorized_agreement(self):
        self.register(35, 30)
        self.consent_both()
        result = self.execute()

        self.assertEqual(result["room_state"], "OPEN")
        self.assertEqual(
            self.negotiation.get(result["offer_id"])["state"],
            "AGREED"
        )
        self.assertEqual(result["payment_authority"], "NOT_GRANTED")

        offer = self.negotiation.get(result["offer_id"])

        self.assertEqual(
            offer["terms"]["amount_units"],
            result["amount_units"]
        )

        kinds = [
            event["kind"]
            for event in self.store.events(self.room_id)
        ]

        self.assertIn("PROPOSAL", kinds)
        self.assertIn("COUNTEROFFER", kinds)
        self.assertIn("AGREEMENT_RECORDED", kinds)

    def test_incompatible_mandates(self):
        self.register(25, 30)
        self.consent_both()
        result = self.execute()

        self.assertEqual(result["status"], "NO_AGREEMENT")
        self.assertEqual(result["payment_authority"], "NOT_GRANTED")
        self.assertNotEqual(
            self.store.get_room(self.room_id)["state"],
            "AGREED"
        )


if __name__ == "__main__":
    unittest.main()
