import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from storepilot.api import create_app


class CatalogueApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "catalogue.json"
        self.rows = [
            {"code": "SUGAR-LOOSE", "name": "Loose sugar", "unit": "kg", "price": "48.00"},
            {"code": "SUGAR-PACK-1KG", "name": "Sugar 1 kg packet", "unit": "piece", "price": "55.00"},
            {"code": "OIL-1L", "name": "Oil 1 litre bottle", "unit": "piece", "price": "150.00"},
        ]
        self.path.write_text(json.dumps(self.rows), encoding="utf-8")
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def test_health_returns_ready_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_products_use_the_configured_catalogue_and_exact_string_prices(self):
        response = self.client.get("/products")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.rows)

    def test_search_matches_names_and_codes_case_insensitively(self):
        response = self.client.get("/products", params={"q": "  SuGaR  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["code"] for row in response.json()],
                         ["SUGAR-LOOSE", "SUGAR-PACK-1KG"])

    def test_no_matches_returns_an_empty_list(self):
        response = self.client.get("/products", params={"q": "rice"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_catalogue_edits_take_effect_on_restart(self):
        self.rows[0]["price"] = "60.00"
        self.path.write_text(json.dumps(self.rows), encoding="utf-8")
        self.assertEqual(self.client.get("/products").json()[0]["price"], "48.00")
        with TestClient(create_app(self.path)) as restarted_client:
            self.assertEqual(restarted_client.get("/products").json()[0]["price"], "60.00")

    def test_invalid_catalogue_stops_application_creation(self):
        self.path.write_text("not JSON", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            create_app(self.path)
        with self.assertRaises(OSError):
            create_app(self.path.parent / "missing.json")

    def test_interactive_api_docs_and_schema_are_available(self):
        self.assertEqual(self.client.get("/docs").status_code, 200)
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/products", schema["paths"])
        self.assertIn("/health", schema["paths"])


if __name__ == "__main__":
    unittest.main()
