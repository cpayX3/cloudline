"""Local cloudline walkthrough. No real agents, credentials or payments."""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from room_core import RoomStore
from conversation_bridge import ConversationBridge
from negotiation import Negotiation
from agreement_verifier import AgreementVerifier
from action_gate import Action, ActionGate, Permit


def main():
    with tempfile.TemporaryDirectory() as tmp:
        store = RoomStore(Path(tmp) / "demo.sqlite")
        try:
            room = store.request_room(
                "buyer", "hunter", "Wallet Vibe Check"
            )

            # Demo-only admission fixture. Not real authentication.
            with store.db:
                store.db.execute(
                    "UPDATE rooms SET state='OPEN' WHERE id=?",
                    (room,)
                )

            chat = ConversationBridge(store)
            deals = Negotiation(store)

            question = chat.receive(
                room, "buyer",
                "Does your wallet report cover stablecoin activity?",
                action="ask"
            )
            answer = chat.receive(
                room, "hunter",
                "The Wallet Vibe Check includes supported "
                "stablecoin activity indicators.",
                action="answer",
                question_id=question
            )
            chat.resolve(room, "buyer", question, answer)

            expiry = (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()

            terms = {
                "service": "wallet-vibe-check",
                "resource": "rExampleWallet",
                "network": "xrpl:0",
                "asset": "RLUSD",
                "recipient": "rExampleSeller",
                "amount_units": 100000,
                "expires_at": expiry
            }

            original = deals.offer(room, "hunter", terms)

            # Counteroffer demonstrates negotiation, not an
            # assertion that Hunter's live API discounts prices.
            revised = dict(terms)
            revised["amount_units"] = 120000
            final_offer = deals.offer(
                room, "buyer", revised, parent_id=original
            )
            digest = deals.get(final_offer)["terms_hash"]

            first = deals.accept(
                room, "hunter", final_offer, digest
            )
            second = deals.accept(
                room, "buyer", final_offer, digest
            )

            action = Action(
                room, "buyer", final_offer, digest,
                "purchase", revised["resource"],
                revised["network"], revised["asset"],
                revised["recipient"], revised["amount_units"]
            )

            signed_calls = []
            submitted_calls = []

            def fake_sign(a):
                signed_calls.append(a.digest())
                return "DEMO_SIGNATURE_NOT_REAL"

            def fake_submit(payload):
                submitted_calls.append(payload)

            denied_gate = ActionGate(
                store, AgreementVerifier(store)
            )
            denied = denied_gate.execute(
                action, "buyer",
                sign=fake_sign, submit=fake_submit
            )
            assert denied["status"] == "BLOCKED"
            assert signed_calls == []
            assert submitted_calls == []

            def fixture_authority(a, agreed_terms):
                assert agreed_terms == revised
                return Permit(
                    a.digest(),
                    "DEMO_ONLY_NOT_MASTERCARD",
                    datetime.now(timezone.utc)
                    + timedelta(minutes=1)
                )

            allowed_gate = ActionGate(
                store,
                AgreementVerifier(store, fixture_authority)
            )
            allowed = allowed_gate.execute(
                action, "buyer",
                sign=fake_sign, submit=fake_submit
            )
            assert allowed["status"] == "SUBMITTED"
            assert len(submitted_calls) == 1

            print("\n===== CLOUDLINE LOCAL DEMO =====")
            print("Question: stablecoin coverage")
            print("Question resolved: yes")
            print("Initial proposal:", original)
            print("Counteroffer:", final_offer)
            print("First acceptance:", first["status"])
            print("Second acceptance:", second["status"])
            print("Agreement hash:", digest)
            print("No authority:", denied)
            print("Fixture authority:", allowed)
            print("Real XRPL payments: ZERO")
            print("Real Mastercard verification: NONE")
            print("\n===== AUDIT EVENTS =====")
            for event in store.events(room):
                print(
                    event["sequence"],
                    event["kind"],
                    event["at"]
                )
            print("\nDEMO COMPLETE")
        finally:
            store.close()


if __name__ == "__main__":
    main()
