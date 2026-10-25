import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from room_core import RoomStore
from negotiation import Negotiation


class NegotiationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.tmp.name) / "test.db")
        self.room = self.store.request_room("buyer", "hunter", "report")
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

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_bilateral_acceptance(self):
        oid = self.n.offer(self.room, "hunter", self.terms)
        digest = self.n.get(oid)["terms_hash"]
        first = self.n.accept(self.room, "buyer", oid, digest)
        self.assertEqual(first["status"], "AWAITING_COUNTERPARTY")
        second = self.n.accept(self.room, "hunter", oid, digest)
        self.assertEqual(second["status"], "AGREED")
        self.assertEqual(self.n.get(oid)["state"], "AGREED")
        kinds = [e["kind"] for e in self.store.events(self.room)]
        self.assertIn("AGREEMENT_RECORDED", kinds)
        self.assertNotIn("ACTION_AUTHORIZED", kinds)

    def test_counteroffer_invalidates_old_terms(self):
        first = self.n.offer(self.room, "hunter", self.terms)
        changed = dict(self.terms, amount_units=120000)
        second = self.n.offer(
            self.room, "buyer", changed, parent_id=first
        )
        self.assertEqual(self.n.get(first)["state"], "SUPERSEDED")
        with self.assertRaises(ValueError):
            self.n.accept(
                self.room, "buyer", first,
                self.n.get(first)["terms_hash"]
            )
        self.assertEqual(self.n.get(second)["state"], "ACTIVE")

    def test_wrong_hash_and_unauthorized_actor(self):
        oid = self.n.offer(self.room, "hunter", self.terms)
        with self.assertRaises(ValueError):
            self.n.accept(self.room, "buyer", oid, "bad")
        with self.assertRaises(PermissionError):
            self.n.accept(
                self.room, "outsider", oid,
                self.n.get(oid)["terms_hash"]
            )

    def test_pending_room_blocks(self):
        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='AWAITING_VERIFICATION'"
            )
        with self.assertRaises(PermissionError):
            self.n.offer(self.room, "hunter", self.terms)

    def test_duplicate_acceptance_blocked(self):
        oid = self.n.offer(self.room, "hunter", self.terms)
        digest = self.n.get(oid)["terms_hash"]
        self.n.accept(self.room, "buyer", oid, digest)
        with self.assertRaises(Exception):
            self.n.accept(self.room, "buyer", oid, digest)

    def test_expired_terms_blocked(self):
        bad = dict(self.terms)
        bad["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        with self.assertRaises(ValueError):
            self.n.offer(self.room, "hunter", bad)


if __name__ == "__main__":
    unittest.main()
