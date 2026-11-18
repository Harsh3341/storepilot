import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from storepilot.catalogue import Product, load_catalogue, search_products


class CatalogueTests(unittest.TestCase):
    def test_loads_prices_exactly_from_saved_json(self):
        rows = [{"code": "SUGAR", "name": "Loose sugar", "unit": "kg", "price": "48.10"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            products = load_catalogue(path)
        self.assertEqual(products["SUGAR"].price, Decimal("48.10"))

    def test_rejects_duplicate_codes_instead_of_losing_a_product(self):
        row = {"code": "SUGAR", "name": "Sugar", "unit": "kg", "price": "48"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            path.write_text(json.dumps([row, row]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_catalogue(path)

    def test_searches_names_and_codes_without_case_sensitivity(self):
        products = {"SUGAR": Product("SUGAR", "Loose sugar", "kg", Decimal("48"))}
        self.assertEqual(search_products(products, "  SuGaR  "), list(products.values()))
        self.assertEqual(search_products(products, "rice"), [])

    def test_rejects_bad_prices(self):
        for price in [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
                      Decimal("1.001"), Decimal("1000001"), 48.10]:
            with self.subTest(price=price), self.assertRaises(ValueError):
                Product("SUGAR", "Sugar", "kg", price)

    def test_rejects_invalid_product_fields(self):
        for code, name, unit in [("", "Sugar", "kg"), ("sugar", "Sugar", "kg"),
                                 ("SUGAR", " ", "kg"), ("SUGAR", "Sugar", "bag")]:
            with self.subTest(code=code, name=name, unit=unit), self.assertRaises(ValueError):
                Product(code, name, unit, Decimal("48"))

    def test_rejects_malformed_catalogues_with_useful_errors(self):
        bad_documents = ["not JSON", "{}", "[]", '["sugar"]',
                         '[{"code":"SUGAR"}]',
                         '[{"code":"SUGAR","name":"Sugar","unit":"kg","price":48.1}]']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.json"
            for document in bad_documents:
                with self.subTest(document=document), self.assertRaises(ValueError):
                    path.write_text(document, encoding="utf-8")
                    load_catalogue(path)


if __name__ == "__main__":
    unittest.main()
