"""HTTP endpoints around StorePilot's existing catalogue and billing logic."""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from storepilot.catalogue import load_catalogue, search_products

DEFAULT_CATALOGUE = Path(__file__).resolve().parents[1] / "data" / "catalogue.json"


class ProductResponse(BaseModel):
    code: str
    name: str
    unit: Literal["kg", "piece"]
    price: str


def create_app(catalogue_path: Path = DEFAULT_CATALOGUE) -> FastAPI:
    """Load the catalogue once. Invalid data prevents the server from starting."""
    catalogue = load_catalogue(catalogue_path)
    app = FastAPI(title="StorePilot API", version="0.2.0",
                  description="Product catalogue and draft billing for a general store.")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/products", response_model=list[ProductResponse])
    def products(q: str = "") -> list[ProductResponse]:
        return [ProductResponse(code=product.code, name=product.name,
                                unit=product.unit, price=f"{product.price:.2f}")
                for product in search_products(catalogue, q)]

    return app
