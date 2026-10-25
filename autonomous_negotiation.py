"""Deterministic negotiation planning with enforceable hard limits."""

from mandates import evaluate


def plan(buyer, seller):
    overlap = evaluate(buyer, seller)

    if not overlap["agreement_possible"]:
        return {
            "status": "NO_AGREEMENT",
            "reason": "HARD_LIMITS_DO_NOT_OVERLAP",
            "steps": [],
            "payment_authority": "NOT_GRANTED"
        }

    low = seller.limit_units
    high = buyer.limit_units

    # Initial buyer offer is never above its authorized ceiling.
    buyer_offer = min(buyer.target_units, high)

    # Seller counteroffer must meet its hard floor.
    seller_offer = max(seller.limit_units, min(seller.target_units, high))

    steps = [{
        "actor": "buyer",
        "action": "PROPOSAL",
        "amount_units": buyer_offer
    }]

    if buyer_offer >= seller.limit_units:
        final_price = buyer_offer
    else:
        steps.append({
            "actor": "seller",
            "action": "COUNTEROFFER",
            "amount_units": seller_offer
        })
        final_price = seller_offer

    assert buyer.permits(final_price)
    assert seller.permits(final_price)

    steps.extend([
        {
            "actor": "buyer",
            "action": "ACCEPT",
            "amount_units": final_price
        },
        {
            "actor": "seller",
            "action": "ACCEPT",
            "amount_units": final_price
        }
    ])

    return {
        "status": "AGREEMENT_POSSIBLE",
        "amount_units": final_price,
        "steps": steps,
        "payment_authority": "NOT_GRANTED"
    }
