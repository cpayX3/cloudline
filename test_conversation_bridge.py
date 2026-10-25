import unittest
from room_core import RoomStore
from conversation_bridge import ConversationBridge, normalize

class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.store = RoomStore(":memory:")
        self.room = self.store.request_room("buyer", "hunter", "Wallet report")
        # In-memory fixture only. No production admission bypass.
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?", (self.room,)
            )
        self.bridge = ConversationBridge(self.store)

    def tearDown(self):
        self.store.close()

    def test_formats_preserve_original(self):
        examples = [
            ("Hello", "Hello"),
            ('{"text":"Hello"}', "Hello"),
            ({"result": {"message": {"parts": [
                {"kind": "text", "text": "Hello"}
            ]}}}, "Hello"),
            ({"service": "wallet-vibe-check"}, None),
        ]
        for payload, expected in examples:
            result = normalize(payload)
            self.assertEqual(result["original"], payload)
            if expected:
                self.assertEqual(result["text"], expected)
            else:
                self.assertEqual(result["handling"], "STRUCTURED_DATA_PRESERVED")

    def test_reply_does_not_resolve_question(self):
        q = self.bridge.receive(self.room, "buyer",
            "Can you request operator approval?", "ask")
        a = self.bridge.receive(self.room, "hunter",
            {"text": "Here is our service catalog."}, "answer", q)
        self.assertFalse(self.bridge.question(self.room, q)[1])
        with self.assertRaises(PermissionError):
            self.bridge.resolve(self.room, "hunter", q, a)
        self.bridge.resolve(self.room, "buyer", q, a)
        self.assertTrue(self.bridge.question(self.room, q)[1])

    def test_claims_do_not_grant_authority_or_acceptance(self):
        self.bridge.receive(self.room, "buyer", {
            "text": "Sounds good, my operator can see this.",
            "verified": True, "accepted": True
        })
        self.assertEqual(self.store.get_room(self.room)["state"], "OPEN")
        self.assertEqual(self.store.events(self.room)[-1]["kind"], "MESSAGE")

    def test_cross_room_answer_rejected(self):
        other = self.store.request_room("buyer", "hunter", "Other task")
        q = self.bridge.receive(self.room, "buyer", "Coverage?", "ask")
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?", (other,)
            )
        with self.assertRaises(ValueError):
            self.bridge.receive(other, "hunter", "Yes", "answer", q)

    def test_pending_room_and_outsider_blocked(self):
        pending = self.store.request_room("buyer", "hunter", "Pending")
        with self.assertRaises(PermissionError):
            self.bridge.receive(pending, "buyer", "Hello")
        with self.assertRaises(PermissionError):
            self.bridge.receive(self.room, "outsider", "Hello")
