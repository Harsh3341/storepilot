"""Run with python -m storepilot; use --demo for a sample draft bill."""

import argparse
import sys
from pathlib import Path

from storepilot.billing import Bill, Selection, calculate_bill
from storepilot.catalogue import Product, load_catalogue, search_products

DEFAULT_CATALOGUE = Path(__file__).resolve().parents[1] / "data" / "catalogue.json"


def print_products(products: list[Product]):
    if not products:
        print("No products found.")
    for product in products:
        print(f"{product.code:<20} {product.name:<28} INR {product.price:.2f}/{product.unit}")


def print_bill(bill: Bill):
    print("\nStorePilot - DRAFT BILL")
    print("-" * 60)
    for line in bill.lines:
        print(f"{line.name}: {line.quantity:f} {line.unit} x INR {line.price:.2f} = INR {line.amount:.2f}")
    print("-" * 60)
    print(f"TOTAL: INR {bill.total:.2f}")
    print("No sale, stock, or payment has been saved.\n")


def interactive_bill(catalogue: dict[str, Product]) -> int:
    print("StorePilot - catalogue and draft billing")
    print("Commands: list | search NAME | PRODUCT_CODE QUANTITY [UNIT] | done | quit")
    print("Examples: SUGAR-LOOSE 250 g | SUGAR-PACK-1KG 2")
    print("Loose quantities default to kg. Packaged quantities default to piece.")
    selections = []
    while True:
        try:
            command = input("Item> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDraft cancelled.")
            return 0
        if not command:
            continue
        if command.casefold() == "quit":
            print("Draft cancelled.")
            return 0
        if command.casefold() == "list":
            print_products(list(catalogue.values()))
            continue
        if command.casefold().startswith("search "):
            print_products(search_products(catalogue, command[7:]))
            continue
        try:
            if command.casefold() == "done":
                print_bill(calculate_bill(catalogue, selections))
                return 0
            parts = command.split()
            if len(parts) not in (2, 3):
                raise ValueError("Use PRODUCT_CODE QUANTITY [UNIT], for example SUGAR-LOOSE 250 g.")
            selection = Selection(parts[0].upper(), parts[1], parts[2] if len(parts) == 3 else None)
            bill = calculate_bill(catalogue, selections + [selection])
            selections.append(selection)
            print(f"Added {bill.lines[-1].name}. Draft total: INR {bill.total:.2f}")
        except ValueError as error:
            print(f"Cannot add or finish: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="StorePilot product catalogue and draft bills.")
    parser.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE,
                        help="Path to an editable JSON catalogue.")
    parser.add_argument("--demo", action="store_true", help="Print an illustrative mixed draft bill.")
    arguments = parser.parse_args()
    try:
        catalogue = load_catalogue(arguments.catalogue)
    except (OSError, ValueError) as error:
        print(f"Cannot load catalogue: {error}", file=sys.stderr)
        return 1
    if arguments.demo:
        selections = [Selection("SUGAR-LOOSE", "250", "g"),
                      Selection("SUGAR-PACK-1KG", "2"), Selection("OIL-1L", "2")]
        try:
            print_bill(calculate_bill(catalogue, selections))
        except ValueError as error:
            print(f"Cannot create demo: {error}", file=sys.stderr)
            return 1
        return 0
    return interactive_bill(catalogue)


if __name__ == "__main__":
    sys.exit(main())
