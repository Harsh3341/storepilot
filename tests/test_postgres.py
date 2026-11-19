"""Real PostgreSQL checks; each test owns a fresh, isolated schema."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

import test_store as store_tests
from storepilot.catalogue import Product
from storepilot.backup import migrate_database
from storepilot.store import Store, StoreError


TEST_URL = os.environ.get("STOREPILOT_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_URL, "Set STOREPILOT_TEST_DATABASE_URL for real PostgreSQL tests.")
class PostgresStoreTests(store_tests.StoreTests):
    def new_database_url(self):
        schema = "storepilot_test_" + uuid4().hex
        admin = psycopg.connect(TEST_URL, autocommit=True)
        self.addCleanup(admin.close)
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

        def cleanup():
            if not re.fullmatch(r"storepilot_test_[0-9a-f]{32}", schema):
                raise RuntimeError("Refusing to drop an unexpected test schema.")
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

        self.addCleanup(cleanup)
        parts = urlsplit(TEST_URL)
        query = dict(parse_qsl(parts.query))
        query["options"] = "-csearch_path=" + schema
        return urlunsplit(parts._replace(query=urlencode(query)))

    def setUp(self):
        self.path = self.new_database_url()
        self.catalogue = {"RICE": Product("RICE", "Rice", "kg", Decimal("40.00")),
                          "SOAP": Product("SOAP", "Soap", "piece", Decimal("10.00"))}
        try:
            self.store = Store(self.path, self.catalogue)
        except OSError:
            self.fail("A PostgreSQL URL must select PostgreSQL instead of a SQLite file.")

    def tearDown(self):
        self.store.close()

    def test_catalogue_preserves_seed_order(self):
        ordered = Store(self.new_database_url(), {"SOAP": self.catalogue["SOAP"],
                                                 "RICE": self.catalogue["RICE"]})
        try:
            self.assertEqual(list(ordered.catalogue()), ["SOAP", "RICE"])
        finally:
            ordered.close()

    def test_row_and_cursor_support_backups(self):
        cursor = self.store.connection.execute("SELECT code,price FROM products ORDER BY code")
        row = cursor.fetchone()
        self.assertEqual(row[0], row["code"])
        self.assertEqual(dict(row), {"code": "RICE", "price": 4000})
        self.assertEqual(cursor.description[0][0], "code")
        self.assertEqual(len(cursor.fetchall()), 1)

    def test_constraint_error_rolls_back_and_connection_recovers(self):
        with self.assertRaises(StoreError) as failure:
            self.store.create_product({"code": "RICE", "name": "Duplicate", "unit": "kg", "price": "1"})
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(self.receive()["stock"], "2")
        with self.assertRaises(sqlite3.Error), self.store.database.transaction():
            self.store.connection.execute("SELECT CAST(? AS BIGINT)", ("not an integer",))
        self.assertEqual(self.store.product("RICE")["stock"], "2")

    def test_auth_schema_and_upsert_are_compatible(self):
        with self.store.database.transaction():
            self.store.connection.executescript("""
                CREATE TABLE IF NOT EXISTS auth_owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    id TEXT PRIMARY KEY, ip TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
            for username in ("first", "second"):
                self.store.connection.execute(
                    "INSERT INTO auth_owner(id,username,password_hash) VALUES(1,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET username=excluded.username",
                    (username, "hash"))
        self.assertEqual(self.store.connection.execute("SELECT username FROM auth_owner").fetchone()[0], "second")

    def test_schema_script_failure_rolls_back_all_statements(self):
        with self.assertRaises(sqlite3.Error):
            self.store.connection.executescript("""
                CREATE TABLE script_probe (amount INTEGER NOT NULL);
                INSERT INTO script_probe VALUES('not an integer');
            """)
        self.assertIsNone(self.store.connection.execute("SELECT to_regclass('script_probe')").fetchone()[0])

    def test_sqlite_postgres_round_trip_preserves_receipts_credit_and_retry_ids(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            restored_path = Path(directory) / "restored.sqlite3"
            sqlite_store = Store(source, {"SOAP": self.catalogue["SOAP"], "RICE": self.catalogue["RICE"]})
            try:
                sqlite_store.change_stock({"product_code": "RICE", "quantity": "2",
                                           "kind": "receive", "request_id": "opening"})
                customer = sqlite_store.create_customer({"name": "Asha"})
                sale_body = {"items": [{"product_code": "RICE", "quantity": "1"}],
                             "customer_id": customer["id"], "paid_amount": "10.00",
                             "payment_method": "cash", "request_id": "sale"}
                sale = sqlite_store.create_sale(sale_body)
                target_url = self.new_database_url()
                migrate_database(source, target_url)
                migrated = Store(target_url, self.catalogue)
                try:
                    self.assertEqual(list(migrated.catalogue()), ["SOAP", "RICE"])
                    self.assertEqual(migrated.sale(sale["id"]), sale)
                    self.assertEqual(migrated.product("RICE")["stock"], "1")
                    self.assertEqual(migrated.ledger(customer["id"])["customer"]["balance"], "30.00")
                    self.assertEqual(migrated.create_sale(sale_body), sale)
                    self.assertEqual(migrated.create_customer({"name": "Bina"})["id"], 2)
                    migrate_database(target_url, restored_path)
                finally:
                    migrated.close()
                restored = Store(restored_path, self.catalogue)
                try:
                    self.assertEqual(list(restored.catalogue()), ["SOAP", "RICE"])
                    self.assertEqual(restored.sale(sale["id"]), sale)
                    self.assertEqual(restored.create_sale(sale_body), sale)
                    self.assertEqual(restored.product("RICE")["stock"], "1")
                finally:
                    restored.close()
            finally:
                sqlite_store.close()

    def test_money_and_stock_columns_use_bigint(self):
        product = self.store.create_product({"code": "BIG", "name": "Bulk", "unit": "piece",
                                             "price": "1000000.00", "opening_stock": "100000"})
        sale = self.sale(items=[{"product_code": product["code"], "quantity": "100000"}],
                         paid_amount="100000000000.00")
        self.assertEqual(sale["total"], "100000000000.00")
        row = self.store.connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='sales' AND column_name='total'").fetchone()
        self.assertEqual(row[0], "bigint")

    def test_concurrent_connections_cannot_oversell(self):
        self.receive(quantity="1")
        other = Store(self.path, self.catalogue)
        barrier = Barrier(2)

        def checkout(store, request_id):
            barrier.wait(timeout=10)
            try:
                return store.create_sale({"items": [{"product_code": "RICE", "quantity": "1"}],
                                          "paid_amount": "40.00", "payment_method": "cash",
                                          "request_id": request_id})
            except StoreError:
                return None

        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(checkout, self.store, "sale-a"),
                           workers.submit(checkout, other, "sale-b")]
                results = [future.result(timeout=20) for future in futures]
            self.assertEqual(sum(result is not None for result in results), 1)
            self.assertEqual(self.store.product("RICE")["stock"], "0")
            self.assertEqual(len(self.store.sales()), 1)
        finally:
            other.close()

    def test_concurrent_repayments_cannot_exceed_balance(self):
        self.receive()
        customer = self.store.create_customer({"name": "Asha"})
        self.sale(customer_id=customer["id"], paid_amount="10.00")
        other = Store(self.path, self.catalogue)
        barrier = Barrier(2)

        def repay(store, request_id):
            barrier.wait(timeout=10)
            try:
                return store.pay_customer(customer["id"], {"amount": "20.00", "method": "cash",
                                                           "request_id": request_id})
            except StoreError:
                return None

        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(repay, self.store, "pay-a"),
                           workers.submit(repay, other, "pay-b")]
                results = [future.result(timeout=20) for future in futures]
            self.assertEqual(sum(result is not None for result in results), 1)
            self.assertEqual(self.store.ledger(customer["id"])["customer"]["balance"], "10.00")
        finally:
            other.close()
