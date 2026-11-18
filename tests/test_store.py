from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from storepilot.catalogue import Product
from storepilot.store import Store, StoreError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "store.sqlite3"
        self.catalogue = {"RICE": Product("RICE", "Rice", "kg", Decimal("40.00")),
                          "SOAP": Product("SOAP", "Soap", "piece", Decimal("10.00"))}
        self.store = Store(self.path, self.catalogue)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def receive(self, quantity="2", request_id="stock-1", code="RICE"):
        return self.store.change_stock({"product_code": code, "quantity": quantity,
                                       "kind": "receive", "request_id": request_id})

    def sale(self, **changes):
        data = {"items": [{"product_code": "RICE", "quantity": "1"}],
                "paid_amount": "40.00", "payment_method": "cash", "request_id": "sale-1"}
        data.update(changes)
        return self.store.create_sale(data)

    def test_durable_stock_and_no_fake_transactions(self):
        self.assertEqual(self.store.summary()["today"]["sales_count"], 0)
        self.receive()
        self.store.close()
        self.store = Store(self.path, self.catalogue)
        self.assertEqual(self.store.product("RICE")["stock"], "2")
        self.assertEqual(self.store.summary()["outstanding_total"], "0.00")

    def test_sale_and_historical_price_snapshot(self):
        self.receive()
        sale = self.sale()
        self.assertEqual(sale["total"], "40.00")
        self.assertEqual(sale["number"], "SP-000001")
        self.assertEqual(self.store.product("RICE")["stock"], "1")
        self.store.update_product("RICE", {"name": "Changed", "price": "99.00", "reorder_level": "0"})
        self.assertEqual(self.store.sale(sale["id"])["lines"][0]["name"], "Rice")
        self.assertEqual(self.store.sale(sale["id"])["lines"][0]["price"], "40.00")

    def test_repeated_sku_insufficient_stock_rolls_back(self):
        self.receive(quantity="1")
        customer = self.store.create_customer({"name": "Asha"})
        with self.assertRaises(StoreError):
            self.sale(items=[{"product_code": "RICE", "quantity": "0.6"},
                             {"product_code": "RICE", "quantity": "0.6"}],
                      customer_id=customer["id"], paid_amount="0.00")
        self.assertEqual(self.store.product("RICE")["stock"], "1")
        self.assertEqual(self.store.sales(), [])
        self.assertEqual(self.store.ledger(customer["id"])["entries"], [])
        self.assertEqual(len(self.store.movements("RICE")), 1)

    def test_credit_and_repayments(self):
        self.receive()
        with self.assertRaises(StoreError):
            self.sale(paid_amount="10.00")
        customer = self.store.create_customer({"name": "Asha"})
        self.sale(customer_id=customer["id"], paid_amount="10.00")
        payment = {"amount": "15.00", "method": "upi", "request_id": "pay-1"}
        result = self.store.pay_customer(customer["id"], payment)
        self.assertEqual(result["customer"]["balance"], "15.00")
        self.assertEqual([e["amount"] for e in self.store.ledger(customer["id"])["entries"]], ["30.00", "-15.00"])
        self.assertEqual(self.store.summary()["today"]["paid_total"], "25.00")
        with self.assertRaises(StoreError):
            self.store.pay_customer(customer["id"], {"amount": "15.01", "method": "cash", "request_id": "pay-2"})

    def test_idempotent_mutations_and_conflicting_body(self):
        first = self.receive()
        self.assertEqual(self.receive(), first)
        with self.assertRaises(StoreError) as failure:
            self.receive(quantity="3")
        self.assertEqual(failure.exception.status_code, 409)
        customer = self.store.create_customer({"name": "Asha"})
        sale = self.sale(customer_id=customer["id"], paid_amount="10.00")
        self.assertEqual(self.sale(customer_id=customer["id"], paid_amount="10.00"), sale)
        payment = {"amount": "10.00", "method": "cash", "request_id": "pay-1"}
        result = self.store.pay_customer(customer["id"], payment)
        self.assertEqual(self.store.pay_customer(customer["id"], payment), result)
        self.assertEqual(self.store.ledger(customer["id"])["customer"]["balance"], "20.00")

    def test_invalid_precision_and_stock(self):
        for quantity in ("0.0001", "NaN", "0", "-1"):
            with self.subTest(quantity=quantity), self.assertRaises(StoreError):
                self.receive(quantity=quantity, request_id=quantity)
        with self.assertRaises(StoreError):
            self.receive(code="SOAP", quantity="1.5")
        with self.assertRaises(StoreError):
            self.store.change_stock({"product_code": "RICE", "quantity": "-1", "kind": "adjust", "reason": "count", "request_id": "adjust-1"})
        with self.assertRaises(StoreError):
            self.store.create_product({"code": "NEW", "name": "New", "unit": "kg", "price": "1.001"})

    def test_order_fulfillment_is_atomic_and_terminal(self):
        self.receive(quantity="1")
        order = self.store.create_order({"customer_name": "Asha", "source": "whatsapp", "items": [{"product_code": "RICE", "quantity": "2"}]})
        self.assertEqual(order["estimated_total"], "80.00")
        self.assertEqual(self.store.product("RICE")["stock"], "1")
        with self.assertRaises(StoreError):
            self.sale(items=[{"product_code": "RICE", "quantity": "2"}], paid_amount="80.00", order_id=order["id"])
        self.assertEqual(self.store.orders()[0]["status"], "pending")
        sale = self.sale(order_id=order["id"])
        self.assertEqual(self.store.orders()[0]["sale_id"], sale["id"])
        with self.assertRaises(StoreError):
            self.sale(order_id=order["id"], request_id="sale-2")
        with self.assertRaises(StoreError):
            self.store.update_order_status(order["id"], "pending")

    def test_other_connection_cannot_oversell(self):
        self.receive(quantity="1")
        other = Store(self.path, self.catalogue)
        try:
            self.sale()
            with self.assertRaises(StoreError):
                other.create_sale({"items": [{"product_code": "RICE", "quantity": "1"}], "paid_amount": "40.00", "payment_method": "cash", "request_id": "other-sale"})
            self.assertEqual(other.product("RICE")["stock"], "0")
        finally:
            other.close()

    def test_fraction_beyond_decimal_context_is_not_rounded_into_stock(self):
        for code, quantity in (("SOAP", "1.0000000000000000000000000001"),
                               ("RICE", "0.001000000000000000000000000001")):
            with self.subTest(code=code), self.assertRaises(StoreError):
                self.receive(code=code, quantity=quantity, request_id=code)
            self.assertEqual(self.store.product(code)["stock"], "0")

    def test_valid_bill_over_one_million_can_be_fully_paid(self):
        self.receive(quantity="100000")
        sale = self.sale(items=[{"product_code": "RICE", "quantity": "100000"}],
                         paid_amount="4000000.00")
        self.assertEqual(sale["total"], "4000000.00")
        self.assertEqual(sale["due_amount"], "0.00")

    def test_catalogue_preserves_seed_order(self):
        path = Path(self.directory.name) / "ordered.sqlite3"
        ordered = Store(path, {"SOAP": self.catalogue["SOAP"], "RICE": self.catalogue["RICE"]})
        try:
            self.assertEqual(list(ordered.catalogue()), ["SOAP", "RICE"])
        finally:
            ordered.close()
