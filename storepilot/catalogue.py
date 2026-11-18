"""Product data and JSON loading. Prices are per kilogram or per piece."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

MAX_NUMBER = Decimal("1000000")


def parse_positive_decimal(text: str, label: str) -> Decimal:
    """Parse text directly, without converting through a binary float."""
    if not isinstance(text, str):
        raise ValueError(f"{label} must be text, for example '0.25'.")
    try:
        value = Decimal(text.strip())
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a valid number.") from error
    if not value.is_finite() or not Decimal("0") < value <= MAX_NUMBER:
        raise ValueError(f"{label} must be positive and at most {MAX_NUMBER}.")
    return value


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    unit: str
    price: Decimal

    def __post_init__(self):
        if not isinstance(self.code, str) or not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", self.code):
            raise ValueError("Product code must use uppercase letters, digits, and single hyphens.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Product name is required.")
        if self.unit not in ("kg", "piece"):
            raise ValueError("Product unit must be 'kg' or 'piece'.")
        if not isinstance(self.price, Decimal) or not self.price.is_finite():
            raise ValueError("Price must be a finite Decimal.")
        if not Decimal("0") < self.price <= MAX_NUMBER:
            raise ValueError(f"Price must be positive and at most {MAX_NUMBER}.")
        if self.price != self.price.quantize(Decimal("0.01")):
            raise ValueError("Price must have at most two decimal places.")


def load_catalogue(path: Path) -> dict[str, Product]:
    """Read an editable catalogue; never silently overwrite duplicate codes."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Catalogue is not valid JSON: {error.msg}.") from error
    if not isinstance(rows, list) or not rows:
        raise ValueError("Catalogue must be a non-empty JSON list of products.")
    catalogue = {}
    required_fields = {"code", "name", "unit", "price"}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != required_fields:
            raise ValueError(f"Product {index} must contain code, name, unit, and price only.")
        product = Product(row["code"], row["name"], row["unit"],
                          parse_positive_decimal(row["price"], "Price"))
        if product.code in catalogue:
            raise ValueError(f"Duplicate product code: {product.code}.")
        catalogue[product.code] = product
    return catalogue


def search_products(catalogue: dict[str, Product], query: str) -> list[Product]:
    query = query.strip().casefold()
    return [product for product in catalogue.values()
            if query in product.name.casefold() or query in product.code.casefold()]
