import tempfile
import unittest
from pathlib import Path
from room_core import RoomStore

class EntranceTests(unittest.TestCase):
    def test_request_never_grants_authority_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rooms.sqlite"
            store = RoomStore(path)
            room_id = store.request_room(
                "buyer-demo", "hunter", "Purchase a Wallet Vibe Check"
            )
            store.close()
            store = RoomStore(path)
            try:
                self.assertEqual(
                    store.get_room(room_id)["state"],
                    "AWAITING_VERIFICATION"
                )
                event = store.events(room_id)[0]
                self.assertEqual(event["payload"]["authority"], "UNVERIFIED")
                self.assertEqual(event["payload"]["identity"], "UNVERIFIED")
                self.assertIn("+00:00", event["at"])
            finally:
                store.close()

    def test_invalid_participants_create_no_room(self):
        store = RoomStore(":memory:")
        try:
            for buyer, seller in [("", "hunter"), ("hunter", "hunter")]:
                with self.assertRaises(ValueError):
                    store.request_room(buyer, seller, "Wallet report")
            self.assertEqual(
                store.db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0],
                0
            )
        finally:
            store.close()

if __name__ == "__main__":
    unittest.main(verbosity=2)
