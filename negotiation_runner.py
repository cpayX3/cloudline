"""Execute mandate-checked autonomous negotiations in cloudline rooms."""

from datetime import datetime, timedelta, timezone

from autonomous_negotiation import plan


def run_negotiation(store, negotiation, mandates, room_id, service,
                    resource, network, asset, recipient):
    # AUTONOMOUS_CONSENT_GATE_V1
    from autonomous_consent import AutonomousConsent

    AutonomousConsent(store).require_bilateral(room_id)

    existing = store.db.execute(
        "SELECT 1 FROM negotiation_offers WHERE room_id=? LIMIT 1",
        (room_id,)
    ).fetchone()

    if existing:
        raise PermissionError("NEGOTIATION_ALREADY_STARTED")

    room = store.get_room(room_id)

    if room["state"] != "OPEN":
        raise PermissionError("ROOM_NOT_OPEN")

    buyer = room["buyer"]
    seller = room["seller"]

    buyer_mandate = mandates.get(room_id, buyer)
    seller_mandate = mandates.get(room_id, seller)

    result = plan(buyer_mandate, seller_mandate)

    if result["status"] == "NO_AGREEMENT":
        return {
            "status": "NO_AGREEMENT",
            "reason": result["reason"],
            "payment_authority": "NOT_GRANTED"
        }

    expiry = (
        datetime.now(timezone.utc) + timedelta(minutes=15)
    ).isoformat()

    parent_id = None
    final_offer_id = None

    for step in result["steps"]:
        actor = buyer if step["actor"] == "buyer" else seller
        amount = step["amount_units"]

        mandates.check_amount(room_id, actor, amount)

        if step["action"] in ("PROPOSAL", "COUNTEROFFER"):
            terms = {
                "service": service,
                "resource": resource,
                "network": network,
                "asset": asset,
                "recipient": recipient,
                "amount_units": amount,
                "expires_at": expiry
            }

            final_offer_id = negotiation.offer(
                room_id, actor, terms, parent_id
            )
            parent_id = final_offer_id

        elif step["action"] == "ACCEPT":
            if not final_offer_id:
                raise RuntimeError("NO_OFFER_TO_ACCEPT")

            offer = negotiation.get(final_offer_id)

            mandates.check_amount(
                room_id, actor, offer["terms"]["amount_units"]
            )

            negotiation.accept(
                room_id,
                actor,
                final_offer_id,
                offer["terms_hash"]
            )

    return {
        "status": "NEGOTIATION_COMPLETED",
        "room_id": room_id,
        "offer_id": final_offer_id,
        "amount_units": result["amount_units"],
        "room_state": store.get_room(room_id)["state"],
        "payment_authority": "NOT_GRANTED"
    }
