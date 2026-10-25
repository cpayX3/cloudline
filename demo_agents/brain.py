"""Independent, deterministic negotiation decision engine.

This module runs inside each agent process.
It does not require access to the counterparty's private policy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentPolicy:
    role: str
    target: int
    limit: int
    concession: int = 5
    max_rounds: int = 8

    def __post_init__(self):
        if self.role not in ("buyer", "seller"):
            raise ValueError("INVALID_ROLE")
        if self.target <= 0 or self.limit <= 0:
            raise ValueError("INVALID_PRICE")
        if self.concession <= 0 or self.max_rounds < 1:
            raise ValueError("INVALID_STRATEGY")
        if self.role == "buyer" and self.target > self.limit:
            raise ValueError("BUYER_TARGET_EXCEEDS_LIMIT")
        if self.role == "seller" and self.target < self.limit:
            raise ValueError("SELLER_TARGET_BELOW_FLOOR")


class AgentBrain:
    def __init__(self, policy):
        self.policy = policy
        self.rounds = 0
        self.last_offer = None

    def permitted(self, amount):
        if type(amount) is not int or amount <= 0:
            return False
        if self.policy.role == "buyer":
            return amount <= self.policy.limit
        return amount >= self.policy.limit

    def opening_offer(self):
        self.last_offer = self.policy.target
        self.rounds += 1
        return {
            "action": "OFFER",
            "amount_units": self.last_offer
        }

    def evaluate_offer(self, amount):
        if type(amount) is not int or amount <= 0:
            return {"action": "REJECT", "reason": "INVALID_AMOUNT"}

        p = self.policy

        # Never accept terms outside the hard boundary.
        if self.permitted(amount):
            if p.role == "buyer":
                acceptable = amount <= p.target
            else:
                acceptable = amount >= p.target

            if acceptable:
                return {"action": "ACCEPT", "amount_units": amount}

        if self.rounds >= p.max_rounds:
            if self.permitted(amount):
                return {"action": "ACCEPT", "amount_units": amount}
            return {"action": "REJECT", "reason": "ROUND_LIMIT"}

        if self.last_offer is None:
            proposed = p.target
        elif p.role == "buyer":
            proposed = min(
                p.limit,
                self.last_offer + p.concession
            )
        else:
            proposed = max(
                p.limit,
                self.last_offer - p.concession
            )

        # If the counterparty's offer is already better than
        # our next counteroffer, accept it instead.
        if self.permitted(amount):
            if p.role == "buyer" and amount <= proposed:
                return {"action": "ACCEPT", "amount_units": amount}
            if p.role == "seller" and amount >= proposed:
                return {"action": "ACCEPT", "amount_units": amount}

        # Stop when no further concession is possible.
        if self.last_offer == proposed:
            return {"action": "REJECT", "reason": "HARD_LIMIT_REACHED"}

        self.last_offer = proposed
        self.rounds += 1

        return {"action": "COUNTER", "amount_units": proposed}
