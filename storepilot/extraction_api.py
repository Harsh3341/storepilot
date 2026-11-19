"""Protected, read-only shopping-list suggestions; saving stays in order routes."""
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from storepilot.groq import ProviderError
from storepilot.order_extraction import MAX_TEXT
from storepilot.store import StoreError


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: Annotated[StrictStr, Field(min_length=1, max_length=MAX_TEXT)]


def make_extraction_router(service):
    router = APIRouter(prefix='/api/orders')

    @router.get('/extraction-status')
    def status():
        return service.status()

    @router.post('/extract')
    def extract(body: ExtractionRequest):
        try:
            return service.extract(body.text)
        except (ProviderError, StoreError) as error:
            raise HTTPException(status_code=error.status_code, detail=str(error)) from None

    return router
