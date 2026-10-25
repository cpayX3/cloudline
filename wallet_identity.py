"""Wallet signature verification using the local ethers adapter."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERIFIER = ROOT / "adapters" / "verify_signature.cjs"


def verify_wallet_signature(address, message, signature):
    if not all(isinstance(v, str) for v in (address, message, signature)):
        return False

    if len(message) > 4096 or len(signature) > 1024 or len(address) > 100:
        return False

    try:
        result = subprocess.run(
            ["node", str(VERIFIER)],
            input=json.dumps({
                "address": address,
                "message": message,
                "signature": signature
            }) + "\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=True
        )

        response = json.loads(result.stdout)
        return response.get("valid") is True

    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        json.JSONDecodeError
    ):
        return False
