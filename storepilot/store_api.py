"""Validated HTTP routes for the persistent store, independent of app setup."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from storepilot.store import Store, StoreError


Text = Annotated[StrictStr, Field(max_length=5000)]
ShortText = Annotated[StrictStr, Field(max_length=160)]
CodeText = Annotated[StrictStr, Field(min_length=1, max_length=64)]
DecimalText = Annotated[StrictStr, Field(min_length=1, max_length=32)]
RequestId = Annotated[StrictStr, Field(min_length=1, max_length=160)]
Identifier = Annotated[int, Field(strict=True, gt=0)]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductCreate(Request):
    code: CodeText
    name: ShortText
    unit: Literal["kg", "piece"]
    price: DecimalText
    opening_stock: DecimalText = "0"
    reorder_level: DecimalText = "0"


class ProductUpdate(Request):
    name: ShortText
    price: DecimalText
    reorder_level: DecimalText


class StockChange(Request):
    product_code: CodeText
    quantity: DecimalText
    unit: Literal["kg", "g", "piece"] | None = None
    kind: Literal["receive", "adjust"]
    reason: Text = ""
    reference: ShortText = ""
    request_id: RequestId


class CustomerCreate(Request):
    name: ShortText
    phone: ShortText = ""


class PaymentCreate(Request):
    amount: DecimalText
    method: Literal["cash", "upi"]
    note: Text = ""
    request_id: RequestId


class SaleItem(Request):
    product_code: CodeText
    quantity: DecimalText
    unit: Literal["kg", "g", "piece"] | None = None


class SaleCreate(Request):
    items: Annotated[list[SaleItem], Field(min_length=1, max_length=100)]
    customer_id: Identifier | None = None
    paid_amount: DecimalText
    payment_method: Literal["cash", "upi"]
    request_id: RequestId
    order_id: Identifier | None = None


class OrderCreate(Request):
    customer_id: Identifier | None = None
    customer_name: ShortText = ""
    source: Literal["walk-in", "whatsapp"] = "walk-in"
    note: Text = ""
    items: Annotated[list[SaleItem], Field(max_length=100)] = Field(default_factory=list)


class OrderStatus(Request):
    status: Literal["pending", "ready", "cancelled"]


def make_store_router(store: Store) -> APIRouter:
    router = APIRouter(prefix="/api")

    def call(method, *args):
        try:
            return method(*args)
        except StoreError as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    @router.get("/summary")
    def summary():
        return call(store.summary)

    @router.get("/products")
    def products(q: str = ""):
        return call(store.products, q)

    @router.post("/products", status_code=201)
    def create_product(body: ProductCreate):
        return call(store.create_product, body.model_dump())

    @router.put("/products/{code}")
    def update_product(code: str, body: ProductUpdate):
        return call(store.update_product, code, body.model_dump())

    @router.post("/stock")
    def change_stock(body: StockChange):
        return call(store.change_stock, body.model_dump())

    @router.get("/products/{code}/movements")
    def movements(code: str):
        return call(store.movements, code)

    @router.get("/customers")
    def customers(q: str = ""):
        return call(store.customers, q)

    @router.post("/customers", status_code=201)
    def create_customer(body: CustomerCreate):
        return call(store.create_customer, body.model_dump())

    @router.get("/customers/{customer_id}/ledger")
    def ledger(customer_id: int):
        return call(store.ledger, customer_id)

    @router.post("/customers/{customer_id}/payments")
    def pay_customer(customer_id: int, body: PaymentCreate):
        return call(store.pay_customer, customer_id, body.model_dump())

    @router.post("/sales", status_code=201)
    def create_sale(body: SaleCreate):
        return call(store.create_sale, body.model_dump())

    @router.get("/sales")
    def sales():
        return call(store.sales)

    @router.get("/sales/{sale_id}")
    def sale(sale_id: int):
        return call(store.sale, sale_id)

    @router.get("/orders")
    def orders(status: str | None = None):
        return call(store.orders, status)

    @router.post("/orders", status_code=201)
    def create_order(body: OrderCreate):
        return call(store.create_order, body.model_dump())

    @router.patch("/orders/{order_id}/status")
    def order_status(order_id: int, body: OrderStatus):
        return call(store.update_order_status, order_id, body.status)

    return router
