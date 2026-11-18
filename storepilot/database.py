"""SQLite connection and explicit transactions for the local store."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
 code TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL CHECK(unit IN ('kg','piece')),
 price INTEGER NOT NULL CHECK(price>0), stock INTEGER NOT NULL CHECK(stock>=0),
 reorder_level INTEGER NOT NULL CHECK(reorder_level>=0));
CREATE TABLE IF NOT EXISTS customers (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
 balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0));
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
 customer_name TEXT NOT NULL, source TEXT NOT NULL, note TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL, items TEXT NOT NULL,
 estimated_total INTEGER, sale_id INTEGER REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS sales (
 id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, customer_id INTEGER REFERENCES customers(id),
 customer_name TEXT NOT NULL, total INTEGER NOT NULL, paid INTEGER NOT NULL,
 due INTEGER NOT NULL, payment_method TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sale_lines (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id),
 product_code TEXT NOT NULL REFERENCES products(code), name TEXT NOT NULL,
 quantity INTEGER NOT NULL, unit TEXT NOT NULL, price INTEGER NOT NULL, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS movements (
 id INTEGER PRIMARY KEY, product_code TEXT NOT NULL REFERENCES products(code),
 kind TEXT NOT NULL, quantity INTEGER NOT NULL, reference TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL, sale_id INTEGER REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
 amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL, note TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger (
 id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
 kind TEXT NOT NULL, description TEXT NOT NULL, amount INTEGER NOT NULL,
 created_at TEXT NOT NULL, sale_id INTEGER REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS requests (
 request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS movements_product ON movements(product_code,id);
CREATE INDEX IF NOT EXISTS ledger_customer ON ledger(customer_id,id);
CREATE INDEX IF NOT EXISTS sales_created ON sales(created_at);
CREATE INDEX IF NOT EXISTS payments_created ON payments(created_at);
"""


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def close(self):
        with self.lock:
            self.connection.close()
