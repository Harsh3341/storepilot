from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from storepilot.catalogue import Product
from storepilot.store import Store
from storepilot.store_api import make_store_router


class StoreApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "store.sqlite3", {"RICE": Product("RICE", "Rice", "kg", Decimal("40.00"))})
        app = FastAPI()
        app.include_router(make_store_router(self.store))
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.directory.cleanup()

    def test_products_and_gram_stock(self):
        response = self.client.post("/api/products", json={"code": "SOAP", "name": "Soap", "unit": "piece", "price": "10.00", "opening_stock": "5", "reorder_level": "2"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["stock"], "5")
        self.assertEqual(len(self.client.get("/api/products?q=soap").json()), 1)
        response = self.client.post("/api/stock", json={"product_code": "RICE", "quantity": "1250", "unit": "g", "kind": "receive", "request_id": "stock-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stock"], "1.25")
        self.assertEqual(self.client.get("/api/products/RICE/movements").json()[0]["unit"], "kg")

    def test_money_and_quantity_are_strict_strings(self):
        bodies = [("/api/products", {"code": "SOAP", "name": "Soap", "unit": "piece", "price": 10}),
                  ("/api/products", {"code": "SOAP", "name": "Soap", "unit": "piece", "price": "10.001"}),
                  ("/api/stock", {"product_code": "RICE", "quantity": 1, "kind": "receive", "request_id": "r"}),
                  ("/api/stock", {"product_code": "RICE", "quantity": "1", "kind": "receive", "request_id": "r", "surprise": True}),
                  ("/api/customers", {"name": "Asha", "unexpected": "field"})]
        for path, body in bodies:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(path, json=body).status_code, 422)

    def test_sale_credit_and_repayment(self):
        self.client.post("/api/stock", json={"product_code": "RICE", "quantity": "2", "kind": "receive", "request_id": "stock-1"})
        customer = self.client.post("/api/customers", json={"name": "Asha"}).json()
        body = {"items": [{"product_code": "RICE", "quantity": "500", "unit": "g"}], "customer_id": customer["id"], "paid_amount": "5.00", "payment_method": "cash", "request_id": "sale-1"}
        response = self.client.post("/api/sales", json=body)
        self.assertEqual(response.status_code, 201)
        sale = response.json()
        self.assertEqual(sale["due_amount"], "15.00")
        self.assertEqual(self.client.post("/api/sales", json=body).json(), sale)
        self.assertEqual(self.client.get(f"/api/sales/{sale['id']}").json(), sale)
        payment = {"amount": "10.00", "method": "upi", "request_id": "pay-1"}
        self.assertEqual(self.client.post(f"/api/customers/{customer['id']}/payments", json=payment).json()["customer"]["balance"], "5.00")
        payment["amount"] = "11.00"
        self.assertEqual(self.client.post(f"/api/customers/{customer['id']}/payments", json=payment).status_code, 409)
        self.assertEqual(self.client.get("/api/summary").json()["today"]["paid_total"], "15.00")

    def test_missing_records(self):
        for path in ("/api/sales/999", "/api/customers/999/ledger", "/api/products/NOPE/movements"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertIsInstance(response.json()["detail"], str)

    def test_order_status_and_empty_order_validation(self):
        response = self.client.post("/api/orders", json={"customer_name": "Asha", "source": "whatsapp", "note": "Call when rice arrives"})
        self.assertEqual(response.status_code, 201)
        order = response.json()
        self.assertIsNone(order["estimated_total"])
        self.assertEqual(self.client.patch(f"/api/orders/{order['id']}/status", json={"status": "ready"}).json()["status"], "ready")
        self.assertEqual(self.client.get("/api/orders?status=ready").json()[0]["id"], order["id"])
        self.assertEqual(self.client.patch(f"/api/orders/{order['id']}/status", json={"status": "cancelled"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/orders/{order['id']}/status", json={"status": "pending"}).status_code, 409)
        self.assertEqual(self.client.post("/api/orders", json={"source": "walk-in"}).status_code, 422)

    def test_request_limits_match_bill_preview(self):
        for body in ({"code": "A" * 65, "name": "Long code", "unit": "kg", "price": "1.00"},
                     {"code": "NEW", "name": "Long number", "unit": "kg", "price": "0" * 30 + "1.00"}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/products", json=body).status_code, 422)
        items = [{"product_code": "RICE", "quantity": "1"}] * 101
        self.assertEqual(self.client.post("/api/orders", json={"items": items}).status_code, 422)
