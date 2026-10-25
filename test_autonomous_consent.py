import tempfile
import unittest
from pathlib import Path

from room_core import RoomStore
from autonomous_consent import AutonomousConsent


class AutonomousConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.temp.name) / "rooms.sqlite")
        self.room_id = self.store.request_room(
            "buyer-agent", "seller-agent", "Test negotiation"
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (self.room_id,)
            )
        self.consent = AutonomousConsent(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_both_parties_must_consent(self):
        self.consent.set(self.room_id, "buyer-agent", True)

        with self.assertRaisesRegex(
            PermissionError, "BILATERAL_AUTONOMOUS_CONSENT_REQUIRED"
        ):
            self.consent.require_bilateral(self.room_id)

        self.consent.set(self.room_id, "seller-agent", True)
        self.assertTrue(self.consent.require_bilateral(self.room_id))

    def test_revocation_blocks_negotiation(self):
        self.consent.set(self.room_id, "buyer-agent", True)
        self.consent.set(self.room_id, "seller-agent", True)

        self.consent.set(self.room_id, "seller-agent", False)

        with self.assertRaises(PermissionError):
            self.consent.require_bilateral(self.room_id)

    def test_nonparticipant_cannot_consent(self):
        with self.assertRaisesRegex(
            PermissionError, "NOT_ROOM_PARTICIPANT"
        ):
            self.consent.set(self.room_id, "outsider", True)

    def test_consent_does_not_grant_payment_authority(self):
        result = self.consent.set(
            self.room_id, "buyer-agent", True
        )
        self.assertEqual(result["payment_authority"], "NOT_GRANTED")


if __name__ == "__main__":
    unittest.main()
