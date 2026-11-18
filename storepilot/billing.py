"""Pure draft-billing calculations, independent of the terminal or database."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from storepilot.catalogue import Product, parse_positive_decimal


@dataclass(frozen=True)
class Selection:
    product_code: str
    quantity: str
    unit: str | None = None


@dataclass(frozen=True)
class BillLine:
    product_code: str
    name: str
    quantity: Decimal
    unit: str
    price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class Bill:
    lines: tuple[BillLine, ...]
    total: Decimal


def selling_quantity(product: Product, selection: Selection) -> Decimal:
    quantity = parse_positive_decimal(selection.quantity, "Quantity")
    unit = product.unit if selection.unit is None else selection.unit.strip().casefold()
    if product.unit == "kg":
        if unit == "g":
            quantity = quantity / Decimal("1000")
        elif unit != "kg":
            raise ValueError("Loose goods accept 'kg' or 'g'.")
        if quantity != quantity.quantize(Decimal("0.001")):
            raise ValueError("Loose quantities must be accurate to a whole gram.")
    else:
        if unit != "piece":
            raise ValueError("Packaged goods accept 'piece' only.")
        if quantity != quantity.to_integral_value():
            raise ValueError("Packaged quantities must be whole numbers.")
    return quantity


def calculate_bill(catalogue: dict[str, Product], selections: list[Selection]) -> Bill:
    if not selections:
        raise ValueError("A bill needs at least one item.")
    lines = []
    for selection in selections:
        product = catalogue.get(selection.product_code)
        if product is None:
            raise ValueError(f"Unknown product: {selection.product_code}.")
        quantity = selling_quantity(product, selection)
        amount = (product.price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Copy these values so a later catalogue update cannot change this draft.
        lines.append(BillLine(product.code, product.name, quantity,
                              product.unit, product.price, amount))
    total = sum((line.amount for line in lines), Decimal("0.00"))
    return Bill(tuple(lines), total)
