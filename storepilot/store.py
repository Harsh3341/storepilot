"""Persistent inventory, checkout, customer credit, and shopping orders."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from storepilot.billing import Selection, calculate_bill, selling_quantity
from storepilot.catalogue import MAX_NUMBER, Product, parse_positive_decimal
from storepilot.database import Database


INDIA = timezone(timedelta(hours=5, minutes=30))


class StoreError(ValueError):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _money_text(paise: int) -> str:
    return format(Decimal(paise) / Decimal("100"), ".2f")


def _quantity_text(quantity: int, unit: str) -> str:
    value = Decimal(quantity) / (Decimal("1000") if unit == "kg" else Decimal("1"))
    return format(value, "f").rstrip("0").rstrip(".") if unit == "kg" and "." in format(value, "f") else format(value, "f")


def _money(value: str, positive: bool = False) -> int:
    if not isinstance(value, str):
        raise StoreError("Amount must be a decimal string.")
    try:
        amount = Decimal(value.strip())
    except InvalidOperation as error:
        raise StoreError("Amount must be a valid number.") from error
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise StoreError("Amount must be positive." if positive else "Amount must be a finite nonnegative number.")
    # Prices and individual quantities keep the domain cap; bill totals and
    # accumulated customer balances may exceed it. Keep storage within INTEGER.
    if amount > Decimal("92233720368547758.07"):
        raise StoreError("Amount is too large to save.")
    if amount != amount.quantize(Decimal("0.01")):
        raise StoreError("Amount must have at most two decimal places.")
    return int(amount * Decimal("100"))


def _stock_quantity(product: Product, value: str, unit: str | None = None, zero: bool = False, signed: bool = False) -> int:
    if not isinstance(value, str):
        raise StoreError("Quantity must be a decimal string.")
    try:
        number = Decimal(value.strip())
    except InvalidOperation as error:
        raise StoreError("Quantity must be a valid number.") from error
    if not number.is_finite():
        raise StoreError("Quantity must be finite.")
    if number == 0 and zero:
        # Validate the chosen unit even when there is no opening stock.
        selling_quantity(product, Selection(product.code, "1", unit))
        return 0
    if number < 0 and not signed:
        raise StoreError("Quantity must be positive.")
    normalized = selling_quantity(product, Selection(product.code, str(number.copy_abs()), unit))
    integer = int(normalized * (Decimal("1000") if product.unit == "kg" else Decimal("1")))
    return -integer if number < 0 else integer


def _required_name(value: str, label: str = "Name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise StoreError(f"{label} is required.")
    return value.strip()


class Store:
    def __init__(self, database_path: Path | str, catalogue: dict[str, Product]):
        self.database = Database(database_path)
        self.connection = self.database.connection
        with self.database.transaction() as connection:
            initialized = connection.execute("SELECT value FROM metadata WHERE key='initialized'").fetchone()
            if initialized is None:
                connection.executemany("INSERT INTO products(code,name,unit,price,stock,reorder_level) VALUES(?,?,?,?,0,0)",
                                       [(p.code, p.name, p.unit, int(p.price * Decimal("100"))) for p in catalogue.values()])
                connection.execute("INSERT INTO metadata VALUES('initialized','1')")

    def close(self):
        self.database.close()

    def _row(self, table: str, key, column: str = "id"):
        # Table/column names are exclusively internal constants.
        row = self.connection.execute(f"SELECT * FROM {table} WHERE {column}=?", (key,)).fetchone()
        if row is None:
            raise StoreError(f"{table.rstrip('s').capitalize()} not found: {key}.", 404)
        return row

    @staticmethod
    def _domain(row) -> Product:
        return Product(row["code"], row["name"], row["unit"], Decimal(row["price"]) / Decimal("100"))

    @staticmethod
    def _product(row) -> dict:
        return {"code": row["code"], "name": row["name"], "unit": row["unit"],
                "price": _money_text(row["price"]), "stock": _quantity_text(row["stock"], row["unit"]),
                "reorder_level": _quantity_text(row["reorder_level"], row["unit"]),
                "low_stock": row["stock"] <= row["reorder_level"]}

    @staticmethod
    def _customer(row) -> dict:
        return {"id": row["id"], "name": row["name"], "phone": row["phone"], "balance": _money_text(row["balance"])}

    def catalogue(self) -> dict[str, Product]:
        with self.database.lock:
            return {row["code"]: self._domain(row) for row in self.connection.execute("SELECT * FROM products ORDER BY rowid")}

    def products(self, q: str = "") -> list[dict]:
        with self.database.lock:
            query = q.strip().casefold()
            return [self._product(row) for row in self.connection.execute("SELECT * FROM products ORDER BY code")
                    if query in row["name"].casefold() or query in row["code"].casefold()]

    def product(self, code: str) -> dict:
        with self.database.lock:
            return self._product(self._row("products", code, "code"))

    def _write(self, operation: str, body: dict, action, request_id: str | None = None):
        try:
            with self.database.transaction():
                fingerprint = None
                if request_id is not None:
                    _required_name(request_id, "Request ID")
                    fingerprint = hashlib.sha256(json.dumps([operation, body], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    previous = self.connection.execute("SELECT fingerprint,result FROM requests WHERE request_id=?", (request_id,)).fetchone()
                    if previous:
                        if previous["fingerprint"] != fingerprint:
                            raise StoreError("Request ID was already used for a different request.", 409)
                        return json.loads(previous["result"])
                result = action()
                if request_id is not None:
                    self.connection.execute("INSERT INTO requests VALUES(?,?,?)", (request_id, fingerprint, json.dumps(result)))
                return result
        except StoreError:
            raise
        except (ValueError, InvalidOperation) as error:
            raise StoreError(str(error)) from error
        except sqlite3.IntegrityError as error:
            raise StoreError("The request conflicts with an existing record.", 409) from error

    def create_product(self, data: dict) -> dict:
        def action():
            product = Product(data["code"], _required_name(data["name"]), data["unit"], parse_positive_decimal(data["price"], "Price"))
            stock = _stock_quantity(product, data.get("opening_stock", "0"), zero=True)
            reorder = _stock_quantity(product, data.get("reorder_level", "0"), zero=True)
            self.connection.execute("INSERT INTO products VALUES(?,?,?,?,?,?)", (product.code, product.name, product.unit, int(product.price * Decimal("100")), stock, reorder))
            if stock:
                self._movement(product.code, "opening", stock, "", "Opening stock", _now())
            return self.product(product.code)
        return self._write("product", data, action)

    def update_product(self, code: str, data: dict) -> dict:
        def action():
            previous = self._row("products", code, "code")
            product = Product(code, _required_name(data["name"]), previous["unit"], parse_positive_decimal(data["price"], "Price"))
            reorder = _stock_quantity(product, data["reorder_level"], zero=True)
            self.connection.execute("UPDATE products SET name=?,price=?,reorder_level=? WHERE code=?", (product.name, int(product.price * Decimal("100")), reorder, code))
            return self.product(code)
        return self._write("update-product", data, action)

    def _movement(self, code, kind, quantity, reference, reason, created_at, sale_id=None):
        self.connection.execute("INSERT INTO movements(product_code,kind,quantity,reference,reason,created_at,sale_id) VALUES(?,?,?,?,?,?,?)",
                                (code, kind, quantity, reference, reason, created_at, sale_id))

    def change_stock(self, data: dict) -> dict:
        body = {"unit": None, "reason": "", "reference": "", **data}
        def action():
            row = self._row("products", body["product_code"], "code")
            if body["kind"] not in ("receive", "adjust"):
                raise StoreError("Stock kind must be receive or adjust.")
            if body["kind"] == "adjust":
                _required_name(body["reason"], "Adjustment reason")
            quantity = _stock_quantity(self._domain(row), body["quantity"], body["unit"], signed=body["kind"] == "adjust")
            if row["stock"] + quantity < 0:
                raise StoreError("Stock cannot become negative.")
            self.connection.execute("UPDATE products SET stock=stock+? WHERE code=?", (quantity, row["code"]))
            self._movement(row["code"], body["kind"], quantity, body["reference"], body["reason"], _now())
            return self.product(row["code"])
        return self._write("stock", body, action, body["request_id"])

    def movements(self, code: str) -> list[dict]:
        with self.database.lock:
            product = self._row("products", code, "code")
            return [{"id": row["id"], "kind": row["kind"], "quantity": _quantity_text(row["quantity"], product["unit"]),
                     "unit": product["unit"], "reference": row["reference"], "reason": row["reason"],
                     "created_at": row["created_at"], "sale_id": row["sale_id"]}
                    for row in self.connection.execute("SELECT * FROM movements WHERE product_code=? ORDER BY id", (code,))]

    def customers(self, q: str = "") -> list[dict]:
        with self.database.lock:
            query = q.strip().casefold()
            return [self._customer(row) for row in self.connection.execute("SELECT * FROM customers ORDER BY name,id")
                    if query in row["name"].casefold() or query in row["phone"].casefold()]

    def create_customer(self, data: dict) -> dict:
        def action():
            cursor = self.connection.execute("INSERT INTO customers(name,phone) VALUES(?,?)", (_required_name(data["name"]), data.get("phone", "").strip()))
            return self._customer(self._row("customers", cursor.lastrowid))
        return self._write("customer", data, action)

    def ledger(self, customer_id: int) -> dict:
        with self.database.lock:
            customer = self._customer(self._row("customers", customer_id))
            entries = [{"id": r["id"], "kind": r["kind"], "description": r["description"], "amount": _money_text(r["amount"]),
                        "created_at": r["created_at"], "sale_id": r["sale_id"]}
                       for r in self.connection.execute("SELECT * FROM ledger WHERE customer_id=? ORDER BY id", (customer_id,))]
            return {"customer": customer, "entries": entries}

    def pay_customer(self, customer_id: int, data: dict) -> dict:
        body = {"note": "", **data, "customer_id": customer_id}
        def action():
            customer = self._row("customers", customer_id)
            amount = _money(body["amount"], positive=True)
            if body["method"] not in ("cash", "upi"):
                raise StoreError("Payment method must be cash or upi.")
            if amount > customer["balance"]:
                raise StoreError("Payment cannot exceed the customer's outstanding balance.")
            created_at = _now()
            payment = self.connection.execute("INSERT INTO payments(customer_id,amount,method,note,created_at) VALUES(?,?,?,?,?)", (customer_id, amount, body["method"], body["note"], created_at))
            self.connection.execute("UPDATE customers SET balance=balance-? WHERE id=?", (amount, customer_id))
            self.connection.execute("INSERT INTO ledger(customer_id,kind,description,amount,created_at) VALUES(?,?,?,?,?)", (customer_id, "payment", body["note"] or f"Repayment ({body['method']})", -amount, created_at))
            return {"customer": self._customer(self._row("customers", customer_id)), "payment_id": payment.lastrowid}
        return self._write("payment", body, action, body["request_id"])

    def create_sale(self, data: dict) -> dict:
        body = {"customer_id": None, "order_id": None, **data}
        body["items"] = [{"unit": None, **item} for item in body["items"]]
        def action():
            catalogue = self.catalogue()
            for item in body["items"]:
                if item["product_code"] not in catalogue:
                    raise StoreError(f"Product not found: {item['product_code']}.", 404)
            bill = calculate_bill(catalogue, [Selection(**item) for item in body["items"]])
            total = int(bill.total * Decimal("100"))
            paid = _money(body["paid_amount"])
            if paid > total:
                raise StoreError("Paid amount cannot exceed the bill total.")
            due = total - paid
            customer = self._row("customers", body["customer_id"]) if body["customer_id"] is not None else None
            if due and customer is None:
                raise StoreError("Choose a customer when any amount remains due.")
            if body["payment_method"] not in ("cash", "upi"):
                raise StoreError("Payment method must be cash or upi.")
            order = self._row("orders", body["order_id"]) if body["order_id"] is not None else None
            if order and order["status"] in ("completed", "cancelled"):
                raise StoreError("A completed or cancelled order cannot be fulfilled.", 409)
            quantities = defaultdict(int)
            for line in bill.lines:
                quantities[line.product_code] += int(line.quantity * (Decimal("1000") if line.unit == "kg" else Decimal("1")))
            for code, quantity in quantities.items():
                if self._row("products", code, "code")["stock"] < quantity:
                    raise StoreError(f"Insufficient stock for {catalogue[code].name}.")
            created_at = _now()
            customer_name = customer["name"] if customer else (order["customer_name"] if order else "")
            cursor = self.connection.execute("INSERT INTO sales(created_at,customer_id,customer_name,total,paid,due,payment_method) VALUES(?,?,?,?,?,?,?)", (created_at, body["customer_id"], customer_name, total, paid, due, body["payment_method"]))
            sale_id = cursor.lastrowid
            for line in bill.lines:
                quantity = int(line.quantity * (Decimal("1000") if line.unit == "kg" else Decimal("1")))
                self.connection.execute("INSERT INTO sale_lines(sale_id,product_code,name,quantity,unit,price,amount) VALUES(?,?,?,?,?,?,?)", (sale_id, line.product_code, line.name, quantity, line.unit, int(line.price * Decimal("100")), int(line.amount * Decimal("100"))))
            for code, quantity in quantities.items():
                self.connection.execute("UPDATE products SET stock=stock-? WHERE code=?", (quantity, code))
                self._movement(code, "sale", -quantity, f"SP-{sale_id:06d}", "Sale", created_at, sale_id)
            if due:
                self.connection.execute("UPDATE customers SET balance=balance+? WHERE id=?", (due, body["customer_id"]))
                self.connection.execute("INSERT INTO ledger(customer_id,kind,description,amount,created_at,sale_id) VALUES(?,?,?,?,?,?)", (body["customer_id"], "credit", f"Credit for SP-{sale_id:06d}", due, created_at, sale_id))
            if order:
                self.connection.execute("UPDATE orders SET status='completed',sale_id=? WHERE id=?", (sale_id, order["id"]))
            return self.sale(sale_id)
        return self._write("sale", body, action, body["request_id"])

    def sale(self, sale_id: int) -> dict:
        with self.database.lock:
            row = self._row("sales", sale_id)
            lines = [{"product_code": r["product_code"], "name": r["name"], "quantity": _quantity_text(r["quantity"], r["unit"]),
                      "unit": r["unit"], "price": _money_text(r["price"]), "amount": _money_text(r["amount"])}
                     for r in self.connection.execute("SELECT * FROM sale_lines WHERE sale_id=? ORDER BY id", (sale_id,))]
            return {"id": row["id"], "number": f"SP-{row['id']:06d}", "created_at": row["created_at"],
                    "customer_id": row["customer_id"], "customer_name": row["customer_name"], "total": _money_text(row["total"]),
                    "paid_amount": _money_text(row["paid"]), "due_amount": _money_text(row["due"]),
                    "payment_method": row["payment_method"], "lines": lines, "kind": "sale", "saved": True}

    def sales(self) -> list[dict]:
        with self.database.lock:
            ids = [row["id"] for row in self.connection.execute("SELECT id FROM sales ORDER BY id DESC LIMIT 100")]
            return [{key: value for key, value in self.sale(sale_id).items() if key != "lines"} for sale_id in ids]

    def create_order(self, data: dict) -> dict:
        body = {"customer_id": None, "customer_name": "", "source": "walk-in", "note": "", "items": [], **data}
        request_id = body.pop('request_id', None)
        def action():
            if not body["note"].strip() and not body["items"]:
                raise StoreError("An order needs a note or at least one item.")
            if body["source"] not in ("walk-in", "whatsapp"):
                raise StoreError("Order source must be walk-in or whatsapp.")
            customer = self._row("customers", body["customer_id"]) if body["customer_id"] is not None else None
            items, estimated = [], None
            if body["items"]:
                catalogue = self.catalogue()
                for item in body["items"]:
                    if item["product_code"] not in catalogue:
                        raise StoreError(f"Product not found: {item['product_code']}.", 404)
                bill = calculate_bill(catalogue, [Selection(**item) for item in body["items"]])
                items = [{"product_code": line.product_code, "name": line.name,
                          "quantity": _quantity_text(int(line.quantity * (Decimal("1000") if line.unit == "kg" else Decimal("1"))), line.unit), "unit": line.unit} for line in bill.lines]
                estimated = int(bill.total * Decimal("100"))
            cursor = self.connection.execute("INSERT INTO orders(customer_id,customer_name,source,note,status,created_at,items,estimated_total) VALUES(?,?,?,?,?,?,?,?)", (body["customer_id"], customer["name"] if customer else body["customer_name"].strip(), body["source"], body["note"].strip(), "pending", _now(), json.dumps(items), estimated))
            return self._order(self._row("orders", cursor.lastrowid))
        return self._write("order", body, action, request_id)

    @staticmethod
    def _order(row) -> dict:
        return {"id": row["id"], "customer_id": row["customer_id"], "customer_name": row["customer_name"], "source": row["source"],
                "note": row["note"], "status": row["status"], "created_at": row["created_at"], "items": json.loads(row["items"]),
                "estimated_total": _money_text(row["estimated_total"]) if row["estimated_total"] is not None else None, "sale_id": row["sale_id"]}

    def orders(self, status: str | None = None) -> list[dict]:
        if status not in (None, "", "pending", "ready", "completed", "cancelled"):
            raise StoreError("Unknown order status.")
        with self.database.lock:
            if status:
                rows = self.connection.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC", (status,))
            else:
                rows = self.connection.execute("SELECT * FROM orders ORDER BY id DESC")
            return [self._order(row) for row in rows]

    def update_order_status(self, order_id: int, status: str) -> dict:
        def action():
            order = self._row("orders", order_id)
            if status not in ("pending", "ready", "cancelled"):
                raise StoreError("Order status must be pending, ready, or cancelled.")
            if order["status"] in ("completed", "cancelled"):
                raise StoreError("Completed and cancelled orders cannot change status.", 409)
            self.connection.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
            return self._order(self._row("orders", order_id))
        return self._write("order-status", {"id": order_id, "status": status}, action)

    def summary(self) -> dict:
        with self.database.lock:
            local_now = datetime.now(INDIA)
            start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end = start + timedelta(days=1)
            bounds = (start.isoformat(timespec="microseconds"), end.isoformat(timespec="microseconds"))
            totals = self.connection.execute("SELECT COUNT(*) AS count,COALESCE(SUM(total),0) AS total,COALESCE(SUM(paid),0) AS paid,COALESCE(SUM(due),0) AS due FROM sales WHERE created_at>=? AND created_at<?", bounds).fetchone()
            payments = self.connection.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE created_at>=? AND created_at<?", bounds).fetchone()[0]
            outstanding = self.connection.execute("SELECT COALESCE(SUM(balance),0) FROM customers").fetchone()[0]
            low_stock = self.connection.execute("SELECT COUNT(*) FROM products WHERE stock<=reorder_level").fetchone()[0]
            pending = self.connection.execute("SELECT COUNT(*) FROM orders WHERE status IN ('pending','ready')").fetchone()[0]
            return {"today": {"sales_count": totals["count"], "sales_total": _money_text(totals["total"]),
                              "paid_total": _money_text(totals["paid"] + payments), "credit_total": _money_text(totals["due"])},
                    "outstanding_total": _money_text(outstanding), "low_stock_count": low_stock, "pending_orders_count": pending}
