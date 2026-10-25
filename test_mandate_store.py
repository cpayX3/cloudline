import tempfile
import unittest
from pathlib import Path

from room_core import RoomStore
from negotiation import Negotiation
from mandate_store import MandateStore


class MandateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.tmp.name) / "rooms.sqlite")
        self.negotiation = Negotiation(self.store)
        self.mandates = MandateStore(self.store)

        self.buyer = "buyer-wallet"
        self.seller = "seller-wallet"

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

    def test_buyer_ceiling_blocks_excess(self):
        self.mandates.register(self.room_id, self.buyer, {
            "target_units": 15,
            "limit_units": 25
        })

        self.assertTrue(
            self.mandates.check_amount(self.room_id, self.buyer, 25)
        )

        with self.assertRaisesRegex(
            PermissionError, "MANDATE_PRICE_LIMIT_EXCEEDED"
        ):
            self.mandates.check_amount(self.room_id, self.buyer, 26)

    def test_seller_floor_blocks_underpayment(self):
        self.mandates.register(self.room_id, self.seller, {
            "target_units": 40,
            "limit_units": 30
        })

        self.assertTrue(
            self.mandates.check_amount(self.room_id, self.seller, 30)
        )

        with self.assertRaisesRegex(
            PermissionError, "MANDATE_PRICE_LIMIT_EXCEEDED"
        ):
            self.mandates.check_amount(self.room_id, self.seller, 29)

    def test_unregistered_mandate_rejected(self):
        with self.assertRaisesRegex(
            PermissionError, "MANDATE_REQUIRED"
        ):
            self.mandates.check_amount(self.room_id, self.buyer, 10)

    def test_mandate_cannot_be_replaced(self):
        values = {"target_units": 15, "limit_units": 25}
        self.mandates.register(self.room_id, self.buyer, values)

        with self.assertRaisesRegex(
            PermissionError, "MANDATE_ALREADY_REGISTERED"
        ):
            self.mandates.register(self.room_id, self.buyer, values)

    def test_other_party_cannot_use_registered_mandate(self):
        self.mandates.register(self.room_id, self.buyer, {
            "target_units": 15,
            "limit_units": 25
        })

        with self.assertRaisesRegex(
            PermissionError, "MANDATE_REQUIRED"
        ):
            self.mandates.check_amount(self.room_id, self.seller, 20)


if __name__ == "__main__":
    unittest.main()
