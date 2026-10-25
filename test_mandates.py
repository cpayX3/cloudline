import unittest
from mandates import Mandate, evaluate


class MandateTests(unittest.TestCase):
    def test_buyer_ceiling(self):
        buyer = Mandate("buyer", 15, 25)
        self.assertTrue(buyer.permits(25))
        self.assertFalse(buyer.permits(26))

    def test_seller_floor(self):
        seller = Mandate("seller", 40, 30)
        self.assertTrue(seller.permits(30))
        self.assertFalse(seller.permits(29))

    def test_no_authorized_overlap(self):
        buyer = Mandate("buyer", 15, 25)
        seller = Mandate("seller", 40, 30)
        result = evaluate(buyer, seller)
        self.assertFalse(result["agreement_possible"])

    def test_authorized_overlap(self):
        buyer = Mandate("buyer", 15, 35)
        seller = Mandate("seller", 40, 30)
        result = evaluate(buyer, seller)
        self.assertTrue(result["agreement_possible"])

    def test_invalid_buyer_target(self):
        with self.assertRaises(ValueError):
            Mandate("buyer", 50, 25)

    def test_invalid_seller_target(self):
        with self.assertRaises(ValueError):
            Mandate("seller", 20, 30)


if __name__ == "__main__":
    unittest.main()
