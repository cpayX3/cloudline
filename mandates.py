"""Hard constraints for cloudline bilateral negotiations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Mandate:
    role: str
    target_units: int
    limit_units: int
    patience: int = 5
    flexibility: int = 50

    def __post_init__(self):
        if self.role not in ("buyer", "seller"):
            raise ValueError("INVALID_ROLE")

        if type(self.target_units) is not int or self.target_units <= 0:
            raise ValueError("INVALID_TARGET")

        if type(self.limit_units) is not int or self.limit_units <= 0:
            raise ValueError("INVALID_LIMIT")

        if self.role == "buyer" and self.target_units > self.limit_units:
            raise ValueError("BUYER_TARGET_EXCEEDS_CEILING")

        if self.role == "seller" and self.target_units < self.limit_units:
            raise ValueError("SELLER_TARGET_BELOW_FLOOR")

        if type(self.patience) is not int or not 1 <= self.patience <= 20:
            raise ValueError("INVALID_PATIENCE")

        if type(self.flexibility) is not int or not 0 <= self.flexibility <= 100:
            raise ValueError("INVALID_FLEXIBILITY")

    def permits(self, amount_units):
        if type(amount_units) is not int or amount_units <= 0:
            return False

        if self.role == "buyer":
            return amount_units <= self.limit_units

        return amount_units >= self.limit_units


def evaluate(buyer, seller):
    if buyer.role != "buyer" or seller.role != "seller":
        raise ValueError("INVALID_MANDATE_PAIR")

    if buyer.limit_units < seller.limit_units:
        return {
            "status": "NO_AUTHORIZED_PRICE_OVERLAP",
            "agreement_possible": False
        }

    return {
        "status": "NEGOTIATION_POSSIBLE",
        "agreement_possible": True,
        "minimum_units": seller.limit_units,
        "maximum_units": buyer.limit_units
    }
