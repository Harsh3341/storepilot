"""HTTP endpoints around StorePilot's existing catalogue and billing logic."""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from storepilot.billing import Selection, calculate_bill
from storepilot.catalogue import load_catalogue, search_products
from storepilot.settings import Settings

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


def create_app(catalogue_path: Path = DEFAULT_CATALOGUE,
               database_path: Path | str | None = None,
               frontend_directory: Path | None = None,
               settings: Settings | None = None) -> FastAPI:
    """Create a persistent store; custom test catalogues are isolated by default."""
    from storepilot.store import Store
    from storepilot.store_api import make_store_router
    from storepilot.auth import Auth
    from storepilot.auth_api import make_auth_router

    configuration = settings or Settings.from_environment(load_file=catalogue_path == DEFAULT_CATALOGUE)
    seed = load_catalogue(catalogue_path)
    if database_path is None:
        database_path = (configuration.database_url or os.environ.get("STOREPILOT_DB", str(DEFAULT_CATALOGUE.parent / "storepilot.sqlite3"))
                         if catalogue_path == DEFAULT_CATALOGUE else ":memory:")
    store = Store(database_path, seed)
    try:
        auth = Auth(store.database)
        if configuration.owner_username:
            auth.setup_owner_hash(configuration.owner_username, configuration.owner_password_hash)
        if configuration.environment == 'production' and not auth.has_owner():
            raise ValueError('Provision an owner account before starting production.')
    except Exception:
        store.close()
        raise

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="StorePilot API", version="0.3.0", lifespan=lifespan,
                  description="Inventory, billing, customer credit, receipts, and orders for a local general store.")
    app.state.store = store
    app.state.auth = auth
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=configuration.trusted_hosts)
    app.include_router(make_auth_router(auth, configuration))
    app.include_router(make_store_router(store))

    @app.middleware("http")
    async def protect_store(request: Request, call_next):
        path = request.url.path
        protected = (path.startswith(('/api/', '/products', '/bills', '/docs', '/redoc'))
                     or path == '/openapi.json')
        public_auth = path in ('/api/auth/session', '/api/auth/login')
        response = None
        if protected and not public_auth and await run_in_threadpool(auth.has_owner):
            token = request.cookies.get(configuration.session_cookie, '')
            session = await run_in_threadpool(auth.session, token)
            if session is None:
                response = JSONResponse({'detail': 'Please sign in to access your store.'}, status_code=401)
            elif request.method not in ('GET', 'HEAD', 'OPTIONS'):
                csrf = request.headers.get('x-csrf-token', '')
                if (not configuration.accepts_origin(request)
                        or not secrets.compare_digest(csrf.encode('utf-8'), session['csrf_token'].encode('utf-8'))):
                    response = JSONResponse({'detail': 'Invalid session or request origin. Refresh and try again.'}, status_code=403)
        if response is None:
            response = await call_next(request)
        if protected or path == '/health':
            response.headers["Cache-Control"] = "no-store"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        if configuration.environment == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/products", response_model=list[ProductResponse])
    def products(q: str = "") -> list[ProductResponse]:
        return [ProductResponse(code=product.code, name=product.name,
                                unit=product.unit, price=f"{product.price:.2f}")
                for product in search_products(store.catalogue(), q)]

    @app.post("/bills/preview", response_model=BillPreviewResponse,
              summary="Calculate a draft bill",
              description="Prices come from the catalogue. No sale, stock, or payment is saved.")
    def preview_bill(request: BillPreviewRequest) -> BillPreviewResponse:
        selections = [Selection(item.product_code, item.quantity, item.unit) for item in request.items]
        try:
            bill = calculate_bill(store.catalogue(), selections)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return BillPreviewResponse(
            lines=[BillLineResponse(product_code=line.product_code, name=line.name,
                                    quantity=f"{line.quantity.normalize():f}", unit=line.unit,
                                    price=f"{line.price:.2f}", amount=f"{line.amount:.2f}")
                   for line in bill.lines],
            total=f"{bill.total:.2f}",
        )

    frontend = frontend_directory or DEFAULT_CATALOGUE.parent.parent / "frontend" / "dist"
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="web")
    return app
