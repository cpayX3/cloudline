import unittest
from room_core import RoomStore

class MessageBoundaryTests(unittest.TestCase):
    def test_pending_room_rejects_greeting_without_recording_it(self):
        store = RoomStore(":memory:")
        try:
            room_id = store.request_room("buyer-demo", "hunter", "Wallet report")
            before = store.events(room_id)
            with self.assertRaises(PermissionError):
                store.record_greeting(room_id, "buyer-demo", "Hello Hunter")
            self.assertEqual(store.events(room_id), before)
        finally:
            store.close()

    def test_open_room_requires_participant_and_persists_greeting(self):
        store = RoomStore(":memory:")
        try:
            room_id = store.request_room("buyer-demo", "hunter", "Wallet report")
            # Test-only fixture. This is NOT an admission implementation.
            with store.db:
                store.db.execute(
                    "UPDATE rooms SET state='OPEN' WHERE id=?", (room_id,)
                )
            with self.assertRaises(PermissionError):
                store.record_greeting(room_id, "outsider", "Hello")
            with self.assertRaises(ValueError):
                store.record_greeting(room_id, "buyer-demo", "")
            store.record_greeting(room_id, "buyer-demo", "Hello Hunter")
            events = store.events(room_id)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["kind"], "GREETING")
            self.assertEqual(events[-1]["payload"]["text"], "Hello Hunter")
        finally:
            store.close()
