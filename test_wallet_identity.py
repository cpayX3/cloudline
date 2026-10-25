import subprocess
import unittest

from wallet_identity import verify_wallet_signature


class WalletIdentityTests(unittest.TestCase):

    def test_valid_signature(self):
        script = r"""
const { Wallet } = require("ethers");
(async () => {
  const wallet = Wallet.createRandom();
  const message = "cloudline identity test";
  const signature = await wallet.signMessage(message);
  console.log(JSON.stringify({
    address: wallet.address,
    message,
    signature
  }));
})();
"""
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=True
        )

        import json
        proof = json.loads(result.stdout)

        self.assertTrue(
            verify_wallet_signature(
                proof["address"],
                proof["message"],
                proof["signature"]
            )
        )

        self.assertFalse(
            verify_wallet_signature(
                proof["address"],
                "different message",
                proof["signature"]
            )
        )

    def test_invalid_signature(self):
        self.assertFalse(
            verify_wallet_signature(
                "not-an-address",
                "cloudline",
                "invalid-signature"
            )
        )


if __name__ == "__main__":
    unittest.main()
