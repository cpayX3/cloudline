import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from room_core import RoomStore
from room_admission import RoomAdmission


def wallet():
    result = subprocess.run(
        ["node", "-e", """
const {Wallet} = require('ethers');
const w = Wallet.createRandom();
console.log(JSON.stringify({
  address: w.address,
  privateKey: w.privateKey
}));
"""],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)


def sign(private_key, message):
    result = subprocess.run(
        ["node", "-e", """
const {Wallet} = require('ethers');
(async () => {
  const wallet = new Wallet(process.argv[1]);
  console.log(await wallet.signMessage(process.argv[2]));
})();
""", private_key, message],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


class RoomAdmissionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RoomStore(
            Path(self.temp.name) / "admission.sqlite"
        )
        self.buyer = wallet()
        self.seller = wallet()
        self.room = self.store.request_room(
            self.buyer["address"],
            self.seller["address"],
            "Wallet Vibe Check"
        )
        self.admission = RoomAdmission(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def authenticate(self, participant):
        challenge = self.admission.challenge(
            self.room, participant["address"]
        )
        signature = sign(
            participant["privateKey"],
            challenge["message"]
        )
        return self.admission.verify(
            self.room,
            participant["address"],
            challenge["challenge_id"],
            signature
        )

    def test_both_signatures_required(self):
        first = self.authenticate(self.buyer)

        self.assertEqual(first["status"], "AWAITING_COUNTERPARTY")
        self.assertEqual(
            self.store.get_room(self.room)["state"],
            "AWAITING_VERIFICATION"
        )

        second = self.authenticate(self.seller)

        self.assertEqual(second["status"], "OPEN")
        self.assertEqual(
            self.store.get_room(self.room)["state"],
            "OPEN"
        )

    def test_signature_cannot_be_replayed(self):
        challenge = self.admission.challenge(
            self.room, self.buyer["address"]
        )
        signature = sign(
            self.buyer["privateKey"],
            challenge["message"]
        )

        self.admission.verify(
            self.room,
            self.buyer["address"],
            challenge["challenge_id"],
            signature
        )

        with self.assertRaises(PermissionError):
            self.admission.verify(
                self.room,
                self.buyer["address"],
                challenge["challenge_id"],
                signature
            )

    def test_wrong_wallet_cannot_authenticate(self):
        challenge = self.admission.challenge(
            self.room, self.buyer["address"]
        )

        signature = sign(
            self.seller["privateKey"],
            challenge["message"]
        )

        with self.assertRaises(PermissionError):
            self.admission.verify(
                self.room,
                self.buyer["address"],
                challenge["challenge_id"],
                signature
            )

        self.assertEqual(
            self.store.get_room(self.room)["state"],
            "AWAITING_VERIFICATION"
        )


if __name__ == "__main__":
    unittest.main()
