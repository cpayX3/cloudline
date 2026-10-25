"""HTTP client for independently authenticated cloudline agents."""

import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8787"


class CloudlineClient:
    def __init__(self, private_key, base=BASE):
        try:
            from eth_account import Account
        except ImportError as exc:
            raise RuntimeError(
                "Missing eth-account. Install with: "
                "python3 -m pip install eth-account"
            ) from exc

        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.base = base
        self.token = None

    def request(self, method, path, payload=None):
        headers = {"Host": "127.0.0.1:8787"}

        if method == "POST":
            headers["Content-Type"] = "application/json"
            headers["Origin"] = "http://127.0.0.1:8787"

        if self.token:
            headers["Authorization"] = "Bearer " + self.token

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method
        )

        try:
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"cloudline HTTP {exc.code}: {body}"
            ) from exc

    def authenticate(self, room_id):
        from eth_account.messages import encode_defunct

        challenge = self.request(
            "POST",
            "/api/admission/challenge",
            {
                "room_id": room_id,
                "address": self.address
            }
        )

        signed = self.account.sign_message(
            encode_defunct(text=challenge["message"])
        )

        result = self.request(
            "POST",
            "/api/admission/verify",
            {
                "room_id": room_id,
                "address": self.address,
                "challenge_id": challenge["challenge_id"],
                "signature": "0x" + signed.signature.hex().removeprefix("0x")
            }
        )

        self.token = result["session_token"]
        return result

    def register_mandate(self, room_id, policy):
        return self.request(
            "POST",
            "/api/mandates",
            {
                "room_id": room_id,
                "mandate": {
                    "role": policy.role,
                    "target_units": policy.target,
                    "limit_units": policy.limit,
                    "patience": policy.max_rounds,
                    "flexibility": 50
                }
            }
        )

    def room(self, room_id):
        return self.request("GET", "/api/rooms/" + room_id)

    def negotiation(self, room_id):
        return self.request(
            "GET",
            "/api/rooms/" + room_id + "/negotiation"
        )

    def offer(self, room_id, terms, parent_id=None):
        return self.request(
            "POST",
            "/api/negotiation/offer",
            {
                "room_id": room_id,
                "terms": terms,
                "parent_id": parent_id
            }
        )

    def accept(self, room_id, offer_id, terms_hash):
        return self.request(
            "POST",
            "/api/negotiation/accept",
            {
                "room_id": room_id,
                "offer_id": offer_id,
                "expected_hash": terms_hash
            }
        )
