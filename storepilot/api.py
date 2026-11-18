"""HTTP endpoints around StorePilot's existing catalogue and billing logic."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from storepilot.billing import Selection, calculate_bill
from storepilot.catalogue import load_catalogue, search_products

DEFAULT_CATALOGUE = Path(__file__).resolve().parents[1] / "data" / "catalogue.json"


class ProductResponse(BaseModel):
    code: str
    name: str
    unit: Literal["kg", "piece"]
    price: str


class BillItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_code: Annotated[str, StringConstraints(strict=True, strip_whitespace=True,
                                                   min_length=1, max_length=64)]
    quantity: Annotated[str, StringConstraints(strict=True, strip_whitespace=True,
                                              min_length=1, max_length=32)]
    unit: Literal["kg", "g", "piece"] | None = None

    @field_validator("product_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class BillPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {"items": [
            {"product_code": "SUGAR-LOOSE", "quantity": "250", "unit": "g"},
            {"product_code": "SUGAR-PACK-1KG", "quantity": "2"},
            {"product_code": "OIL-1L", "quantity": "2"},
        ]},
    })

    items: list[BillItemRequest] = Field(min_length=1, max_length=100)


class BillLineResponse(BaseModel):
    product_code: str
    name: str
    quantity: str
    unit: Literal["kg", "piece"]
    price: str
    amount: str


class BillPreviewResponse(BaseModel):
    kind: Literal["draft"] = "draft"
    currency: Literal["INR"] = "INR"
    saved: Literal[False] = False
    lines: list[BillLineResponse]
    total: str


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

    @app.post("/bills/preview", response_model=BillPreviewResponse,
              summary="Calculate a draft bill",
              description="Prices come from the catalogue. No sale, stock, or payment is saved.")
    def preview_bill(request: BillPreviewRequest) -> BillPreviewResponse:
        selections = [Selection(item.product_code, item.quantity, item.unit) for item in request.items]
        try:
            bill = calculate_bill(catalogue, selections)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return BillPreviewResponse(
            lines=[BillLineResponse(product_code=line.product_code, name=line.name,
                                    quantity=f"{line.quantity.normalize():f}", unit=line.unit,
                                    price=f"{line.price:.2f}", amount=f"{line.amount:.2f}")
                   for line in bill.lines],
            total=f"{bill.total:.2f}",
        )

    return app
