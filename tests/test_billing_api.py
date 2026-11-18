import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from storepilot.api import create_app


class BillingApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "catalogue.json"
        rows = [
            {"code": "SUGAR-LOOSE", "name": "Loose sugar", "unit": "kg", "price": "48.00"},
            {"code": "SUGAR-PACK-1KG", "name": "Sugar 1 kg packet", "unit": "piece", "price": "55.00"},
            {"code": "OIL-1L", "name": "Oil 1 litre bottle", "unit": "piece", "price": "150.00"},
            {"code": "RICE", "name": "Rice", "unit": "kg", "price": "5.00"},
        ]
        path.write_text(json.dumps(rows), encoding="utf-8")
        self.client = TestClient(create_app(path))
        self.addCleanup(self.client.close)

    def preview(self, *items):
        return self.client.post("/bills/preview", json={"items": list(items)})

    def test_mixed_bill_returns_a_draft_with_exact_prices(self):
        response = self.preview(
            {"product_code": "SUGAR-LOOSE", "quantity": "250", "unit": "g"},
            {"product_code": "SUGAR-PACK-1KG", "quantity": "2"},
            {"product_code": "OIL-1L", "quantity": "2"},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["kind"], "draft")
        self.assertEqual(result["currency"], "INR")
        self.assertFalse(result["saved"])
        self.assertEqual(result["total"], "422.00")
        self.assertEqual(result["lines"][0], {
            "product_code": "SUGAR-LOOSE", "name": "Loose sugar", "quantity": "0.25",
            "unit": "kg", "price": "48.00", "amount": "12.00",
        })

    def test_fractional_kilograms_preserve_decimal_values_in_json(self):
        response = self.preview({"product_code": "SUGAR-LOOSE", "quantity": "0.1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], "4.80")

    def test_codes_quantities_and_units_are_normalized(self):
        response = self.preview({"product_code": " sugar-loose ", "quantity": " 250 ", "unit": " G "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], "12.00")

    def test_unknown_products_return_readable_validation_errors(self):
        response = self.preview({"product_code": "MISSING", "quantity": "1"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Unknown product", response.json()["detail"])

    def test_invalid_quantities_return_422(self):
        for quantity, unit in [("0", "kg"), ("-1", "kg"), ("NaN", "kg"),
                               ("Infinity", "kg"), ("abc", "kg"), ("1000001", "kg"),
                               ("0.0001", "kg"), ("0.5", "g"), ("1e-9999999", "g"),
                               ("", "kg"), ("1" * 33, "kg")]:
            with self.subTest(quantity=quantity, unit=unit):
                response = self.preview({"product_code": "SUGAR-LOOSE", "quantity": quantity, "unit": unit})
                self.assertEqual(response.status_code, 422)

    def test_json_numeric_quantities_are_rejected(self):
        for quantity in [0.1, 1, True, None]:
            with self.subTest(quantity=quantity):
                response = self.preview({"product_code": "SUGAR-LOOSE", "quantity": quantity})
                self.assertEqual(response.status_code, 422)

    def test_fractional_packets_are_rejected(self):
        response = self.preview({"product_code": "SUGAR-PACK-1KG", "quantity": "0.5"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("whole numbers", response.json()["detail"])

    def test_unsupported_or_mismatched_units_are_rejected(self):
        for code, unit in [("SUGAR-LOOSE", "bag"), ("SUGAR-PACK-1KG", "kg"),
                           ("SUGAR-LOOSE", "piece")]:
            with self.subTest(code=code, unit=unit):
                self.assertEqual(self.preview({"product_code": code, "quantity": "1", "unit": unit}).status_code, 422)

    def test_item_list_must_have_between_one_and_one_hundred_items(self):
        item = {"product_code": "SUGAR-PACK-1KG", "quantity": "1"}
        self.assertEqual(self.preview().status_code, 422)
        self.assertEqual(self.preview(*([item] * 101)).status_code, 422)
        accepted = self.preview(*([item] * 100))
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["total"], "5500.00")

    def test_client_cannot_supply_prices_or_totals(self):
        item = {"product_code": "SUGAR-PACK-1KG", "quantity": "1", "price": "1.00"}
        self.assertEqual(self.preview(item).status_code, 422)
        response = self.client.post("/bills/preview", json={
            "items": [{"product_code": "SUGAR-PACK-1KG", "quantity": "1"}], "total": "1.00",
        })
        self.assertEqual(response.status_code, 422)

    def test_malformed_requests_return_422_instead_of_server_errors(self):
        for body in [{}, {"items": "not a list"}, {"items": [None]},
                     {"items": [{"product_code": "SUGAR-LOOSE"}]},
                     {"items": [{"product_code": 123, "quantity": "1"}]}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/bills/preview", json=body).status_code, 422)

    def test_omitted_or_null_unit_uses_the_catalogue_unit(self):
        for item in [{"product_code": "SUGAR-LOOSE", "quantity": "0.25"},
                     {"product_code": "SUGAR-LOOSE", "quantity": "0.25", "unit": None}]:
            with self.subTest(item=item):
                response = self.preview(item)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total"], "12.00")

    def test_rounds_each_line_then_sums_the_rounded_amounts(self):
        item = {"product_code": "RICE", "quantity": "1", "unit": "g"}
        response = self.preview(item, item)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lines"][0]["amount"], "0.01")
        self.assertEqual(response.json()["total"], "0.02")


if __name__ == "__main__":
    unittest.main()
