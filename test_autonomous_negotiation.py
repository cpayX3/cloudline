import unittest
from mandates import Mandate
from autonomous_negotiation import plan


class AutonomousNegotiationTests(unittest.TestCase):
    def test_authorized_deal(self):
        buyer = Mandate("buyer", 15, 35)
        seller = Mandate("seller", 40, 30)

        result = plan(buyer, seller)

        self.assertEqual(result["status"], "AGREEMENT_POSSIBLE")
        self.assertTrue(buyer.permits(result["amount_units"]))
        self.assertTrue(seller.permits(result["amount_units"]))

    def test_incompatible_limits(self):
        buyer = Mandate("buyer", 15, 25)
        seller = Mandate("seller", 40, 30)

        result = plan(buyer, seller)

        self.assertEqual(result["status"], "NO_AGREEMENT")
        self.assertEqual(result["steps"], [])

    def test_no_payment_authority(self):
        buyer = Mandate("buyer", 15, 35)
        seller = Mandate("seller", 40, 30)

        result = plan(buyer, seller)

        self.assertEqual(result["payment_authority"], "NOT_GRANTED")

    def test_agreement_requires_both_acceptances(self):
        buyer = Mandate("buyer", 15, 35)
        seller = Mandate("seller", 40, 30)

        result = plan(buyer, seller)

        actors = [
            step["actor"]
            for step in result["steps"]
            if step["action"] == "ACCEPT"
        ]

        self.assertEqual(actors, ["buyer", "seller"])


if __name__ == "__main__":
    unittest.main()
