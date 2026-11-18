import unittest
from decimal import Decimal

from storepilot.billing import Selection, calculate_bill
from storepilot.catalogue import Product


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.catalogue = {
            "SUGAR-LOOSE": Product("SUGAR-LOOSE", "Loose sugar", "kg", Decimal("48")),
            "SUGAR-PACK": Product("SUGAR-PACK", "Sugar 1 kg packet", "piece", Decimal("55")),
            "OIL-1L": Product("OIL-1L", "Oil 1 litre bottle", "piece", Decimal("150")),
        }

    def test_converts_grams_to_kilograms(self):
        bill = calculate_bill(self.catalogue, [Selection("SUGAR-LOOSE", "250", "g")])
        self.assertEqual(bill.lines[0].quantity, Decimal("0.25"))
        self.assertEqual(bill.total, Decimal("12.00"))

    def test_accepts_decimal_kilograms_without_float_error(self):
        bill = calculate_bill(self.catalogue, [Selection("SUGAR-LOOSE", "0.1", "kg")])
        self.assertEqual(bill.total, Decimal("4.80"))

    def test_calculates_a_mixed_bill(self):
        bill = calculate_bill(self.catalogue, [Selection("SUGAR-LOOSE", "250", "g"),
                                             Selection("SUGAR-PACK", "2"),
                                             Selection("OIL-1L", "2", "piece")])
        self.assertEqual(bill.total, Decimal("422.00"))

    def test_rounds_half_a_paisa_up_and_sums_rounded_lines(self):
        catalogue = {"RICE": Product("RICE", "Rice", "kg", Decimal("5"))}
        bill = calculate_bill(catalogue, [Selection("RICE", "1", "g"), Selection("RICE", "1", "g")])
        self.assertEqual(bill.lines[0].amount, Decimal("0.01"))
        self.assertEqual(bill.total, Decimal("0.02"))

    def test_rejects_fractional_packaged_quantities(self):
        with self.assertRaisesRegex(ValueError, "whole"):
            calculate_bill(self.catalogue, [Selection("SUGAR-PACK", "0.5")])

    def test_rejects_invalid_quantities(self):
        for quantity in ["0", "-1", "abc", "", "NaN", "Infinity", "1e999", "1000001", 0.1]:
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                calculate_bill(self.catalogue, [Selection("SUGAR-LOOSE", quantity)])

    def test_rejects_quantities_smaller_than_gram_precision(self):
        for quantity, unit in [("0.0001", "kg"), ("0.5", "g")]:
            with self.subTest(quantity=quantity), self.assertRaisesRegex(ValueError, "gram"):
                calculate_bill(self.catalogue, [Selection("SUGAR-LOOSE", quantity, unit)])

    def test_rejects_units_that_do_not_match_the_product(self):
        for code, unit in [("SUGAR-LOOSE", "piece"), ("SUGAR-PACK", "kg"), ("SUGAR-LOOSE", "bag")]:
            with self.subTest(code=code, unit=unit), self.assertRaises(ValueError):
                calculate_bill(self.catalogue, [Selection(code, "1", unit)])

    def test_rejects_unknown_products(self):
        with self.assertRaisesRegex(ValueError, "Unknown product"):
            calculate_bill(self.catalogue, [Selection("MISSING", "1")])

    def test_rejects_an_empty_bill(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            calculate_bill(self.catalogue, [])

    def test_existing_bill_keeps_its_price_after_catalogue_change(self):
        bill = calculate_bill(self.catalogue, [Selection("SUGAR-PACK", "2")])
        self.catalogue["SUGAR-PACK"] = Product("SUGAR-PACK", "New name", "piece", Decimal("60"))
        self.assertEqual(bill.lines[0].price, Decimal("55"))
        self.assertEqual(bill.lines[0].name, "Sugar 1 kg packet")
        self.assertEqual(bill.total, Decimal("110.00"))


if __name__ == "__main__":
    unittest.main()
