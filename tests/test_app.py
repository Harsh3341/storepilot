import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from storepilot.api import create_app


class PersistentAppTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.catalogue = self.directory / "catalogue.json"
        self.catalogue.write_text(json.dumps([
            {"code": "SUGAR", "name": "Loose sugar", "unit": "kg", "price": "48.00"},
        ]), encoding="utf-8")

    def test_explicit_database_preserves_records_after_restart(self):
        database = self.directory / "store.sqlite3"
        with TestClient(create_app(self.catalogue, database_path=database)) as client:
            response = client.post("/api/customers", json={"name": "Test customer", "phone": ""})
            self.assertEqual(response.status_code, 201)
        with TestClient(create_app(self.catalogue, database_path=database)) as client:
            self.assertEqual(client.get("/api/customers").json()[0]["name"], "Test customer")

    def test_custom_catalogues_use_isolated_memory_databases_by_default(self):
        with TestClient(create_app(self.catalogue)) as first:
            self.assertEqual(first.post("/api/customers", json={"name": "Temporary customer"}).status_code, 201)
        with TestClient(create_app(self.catalogue)) as second:
            self.assertEqual(second.get("/api/customers").json(), [])

    def test_product_price_updates_reach_the_existing_preview_endpoint(self):
        with TestClient(create_app(self.catalogue, database_path=":memory:")) as client:
            response = client.put("/api/products/SUGAR", json={
                "name": "Loose sugar", "price": "60.00", "reorder_level": "0",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.get("/products").json()[0]["price"], "60.00")
            preview = client.post("/bills/preview", json={
                "items": [{"product_code": "SUGAR", "quantity": "0.25"}],
            })
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["total"], "15.00")

    def test_dynamic_store_responses_are_not_cached(self):
        with TestClient(create_app(self.catalogue, database_path=":memory:")) as client:
            for path in ("/health", "/products", "/api/products", "/api/customers"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("no-store", response.headers.get("cache-control", ""))


if __name__ == "__main__":
    unittest.main()
