import tempfile
import unittest
from pathlib import Path

from room_core import RoomStore
from negotiation import Negotiation
from autonomous_scope import AutonomousScope


class AutonomousScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = RoomStore(Path(self.tmp.name) / "rooms.sqlite")
        self.negotiation = Negotiation(self.store)
        self.scope = AutonomousScope(self.store)

        self.buyer = "buyer-agent"
        self.seller = "seller-agent"

        self.room = self.store.request_room(
            self.buyer, self.seller, "Wallet report"
        )

        with self.store.db:
            self.store.db.execute(
                "UPDATE rooms SET state='OPEN' WHERE id=?",
                (self.room,)
            )

        self.terms = {
            "service": "wallet-report",
            "resource": "/agent/v3/wallet-vibe-check",
            "network": "xrpl:0",
            "asset": "RLUSD",
            "recipient": "seller-wallet"
        }

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_one_party_cannot_authorize_both(self):
        self.scope.authorize(self.room, self.buyer, self.terms)

        with self.assertRaisesRegex(
            PermissionError,
            "BILATERAL_SCOPE_AUTHORIZATION_REQUIRED"
        ):
            self.scope.require_bilateral(self.room, self.terms)

    def test_matching_scopes_authorize(self):
        self.scope.authorize(self.room, self.buyer, self.terms)
        self.scope.authorize(self.room, self.seller, self.terms)

        self.assertTrue(
            self.scope.require_bilateral(self.room, self.terms)
        )

    def test_changed_recipient_is_blocked(self):
        self.scope.authorize(self.room, self.buyer, self.terms)
        self.scope.authorize(self.room, self.seller, self.terms)

        changed = dict(self.terms)
        changed["recipient"] = "attacker-wallet"

        with self.assertRaises(PermissionError):
            self.scope.require_bilateral(self.room, changed)

    def test_changed_asset_is_blocked(self):
        self.scope.authorize(self.room, self.buyer, self.terms)
        self.scope.authorize(self.room, self.seller, self.terms)

        changed = dict(self.terms)
        changed["asset"] = "XRP"

        with self.assertRaises(PermissionError):
            self.scope.require_bilateral(self.room, changed)

    def test_unsupported_network_blocked(self):
        changed = dict(self.terms)
        changed["network"] = "eip155:8453"

        with self.assertRaises(PermissionError):
            self.scope.authorize(self.room, self.buyer, changed)

    def test_scope_does_not_grant_payment_authority(self):
        result = self.scope.authorize(
            self.room, self.buyer, self.terms
        )

        self.assertEqual(
            result["payment_authority"], "NOT_GRANTED"
        )


if __name__ == "__main__":
    unittest.main()
