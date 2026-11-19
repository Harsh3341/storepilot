"""Validate model drafts and reserve a small persisted daily inference budget."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from storepilot.billing import Selection, selling_quantity
from storepilot.groq import ProviderError
from storepilot.store import INDIA, StoreError

MAX_TEXT = 2000
DAILY_LIMIT = 25
COOLDOWN = 10
MAX_PRODUCTS = 100
MAX_CATALOGUE_BYTES = 12000


class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original: Annotated[StrictStr, Field(min_length=1, max_length=2000)]
    product_code: Annotated[StrictStr, Field(max_length=64)] | None
    quantity: Annotated[StrictStr, Field(max_length=32)] | None
    unit: Literal['kg', 'g', 'piece'] | None
    reason: Annotated[StrictStr, Field(max_length=300)] | None


class Suggestions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[Suggestion] = Field(max_length=50)


COUNT_WORDS = {
    1: ('one', 'ek', 'एक'), 2: ('two', 'do', 'दो'),
    3: ('three', 'teen', 'तीन'), 4: ('four', 'char', 'chaar', 'चार'),
    5: ('five', 'paanch', 'panch', 'पांच', 'पाँच'),
    6: ('six', 'chhe', 'छह'), 7: ('seven', 'saat', 'सात'),
    8: ('eight', 'aath', 'आठ'), 9: ('nine', 'nau', 'नौ'),
    10: ('ten', 'das', 'दस'), 12: ('dozen', 'दर्जन'),
}


def _explicit_piece_count(original, quantity):
    # Remove sizes before looking for a count: "Lux 100g" is not one piece.
    without_sizes = re.sub(
        r'\d+(?:\.\d+)?\s*(?:kilograms?|grams?|litres?|liters?|kg|gm|g|ml|l|ग्राम|किलो|लीटर)(?!\w)',
        ' ', original.casefold())
    wanted = Decimal(quantity)
    numbers = re.findall(r'(?<!\w)\d+(?:\.\d+)?(?!\w)', without_sizes)
    if any(Decimal(number) == wanted for number in numbers):
        return True
    return any(re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', without_sizes)
               for word in COUNT_WORDS.get(int(wanted), ()))


def _explicit_loose_quantity(original, kilograms):
    units = r'kilograms?|kilos?|kg|किलो|grams?|gm|g|ग्राम'
    def as_kg(number, unit):
        return number / Decimal('1000') if unit in ('g', 'gm', 'gram', 'grams', 'ग्राम') else number
    source = original.casefold()
    for number, unit in re.findall(r'(?<!\w)(\d+(?:\.\d+)?)\s*(' + units + r')(?!\w)', source):
        if as_kg(Decimal(number), unit) == kilograms:
            return True
    words = {str(count): names for count, names in COUNT_WORDS.items()}
    words.update({'0.5': ('half', 'aadha', 'adha', 'आधा', 'आधी'),
                  '0.25': ('quarter', 'paav', 'pav', 'पाव'),
                  '1.5': ('dedh', 'डेढ़'), '2.5': ('dhai', 'ढाई')})
    for value, names in words.items():
        for word in names:
            match = re.search(r'(?<!\w)' + re.escape(word) + r'\s+(' + units + r')(?!\w)', source)
            if match and as_kg(Decimal(value), match.group(1)) == kilograms:
                return True
    return False


def validate_draft(payload: dict, catalogue: dict, text: str) -> dict:
    try:
        suggestions = Suggestions.model_validate(payload)
    except ValidationError:
        raise ProviderError() from None
    rows = []
    for suggestion in suggestions.items:
        item = suggestion.model_dump()
        reason = item['reason'] or None
        product = catalogue.get(item['product_code'])
        if item['original'] not in text:
            reason = 'This phrase was not in the request. Check or remove this item.'
            item.update(product_code=None, quantity=None, unit=None)
        elif product is None:
            reason = reason or 'Choose the exact product and pack size.'
            item['product_code'] = None
        elif item['quantity'] is None or not re.fullmatch(r'\d+(?:\.\d+)?', item['quantity']):
            reason = reason or 'Enter the requested quantity.'
            item['quantity'] = None
        elif item['unit'] is None:
            reason = reason or 'Confirm the unit from the request.'
        else:
            try:
                kilograms = selling_quantity(product, Selection(product.code, item['quantity'], item['unit']))
                if product.unit == 'piece' and not _explicit_piece_count(item['original'], item['quantity']):
                    reason = 'Confirm the number of packets or pieces. Pack size does not supply a count.'
                    item['quantity'] = None
                elif product.unit == 'kg' and not _explicit_loose_quantity(item['original'], kilograms):
                    reason = 'Confirm the requested amount and unit for this loose product.'
                    item['quantity'] = None
            except (ValueError, InvalidOperation) as error:
                reason = str(error)
                item['quantity'] = None
        item['reason'] = reason
        rows.append(item)
    return {'rows': rows, 'requires_review': True,
            'warnings': ['Check every item against the original request before saving.']}


class ExtractionService:
    def __init__(self, store, provider=None, clock=None):
        self.store = store
        self.provider = provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _usage(self, connection, now):
        row = connection.execute("SELECT value FROM metadata WHERE key='ai_order_usage'").fetchone()
        usage = json.loads(row['value']) if row else {}
        day = now.astimezone(INDIA).date().isoformat()
        return {'day': day, 'attempts': usage.get('attempts', 0) if usage.get('day') == day else 0,
                'last': usage.get('last', 0)}

    @staticmethod
    def _catalogue(catalogue):
        return [{'code': p.code, 'name': p.name, 'unit': p.unit} for p in catalogue.values()]

    @staticmethod
    def _catalogue_reason(catalogue):
        if not catalogue:
            return 'Add products in Stock before extracting a shopping list.'
        if len(catalogue) > MAX_PRODUCTS or len(json.dumps(catalogue, ensure_ascii=False).encode()) > MAX_CATALOGUE_BYTES:
            return 'This catalogue is too large for free extraction. Save the note and select items when billing.'
        return None

    def status(self):
        now = self.clock()
        with self.store.database.lock:
            usage = self._usage(self.store.connection, now)
            catalogue = self._catalogue(self.store.catalogue())
        remaining = max(0, DAILY_LIMIT - usage['attempts'])
        cooldown = max(0, math.ceil(COOLDOWN - (now.timestamp() - usage['last'])))
        reason = ('Suggestions are not configured. You can still save an order note.' if self.provider is None
                  else self._catalogue_reason(catalogue))
        if not reason and remaining == 0:
            reason = 'Daily suggestion limit reached. Try tomorrow or save the note.'
        if not reason and cooldown:
            reason = f'Wait {cooldown} seconds before extracting again.'
        return {'enabled': self.provider is not None, 'available': reason is None,
                'reason': reason, 'remaining': remaining, 'daily_limit': DAILY_LIMIT,
                'max_text_length': MAX_TEXT, 'cooldown_seconds': cooldown}

    def extract(self, text: str):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise StoreError(f'Enter a shopping list of at most {MAX_TEXT} characters.')
        if self.provider is None:
            raise StoreError('Suggestions are not configured. You can still save an order note.', 503)
        catalogue = self.store.catalogue()
        context = self._catalogue(catalogue)
        reason = self._catalogue_reason(context)
        if reason:
            raise StoreError(reason)
        now = self.clock()
        with self.store.database.transaction() as connection:
            usage = self._usage(connection, now)
            if usage['attempts'] >= DAILY_LIMIT:
                raise StoreError('Daily suggestion limit reached. Try tomorrow or save the note.', 429)
            if now.timestamp() - usage['last'] < COOLDOWN:
                raise StoreError('Wait 10 seconds before extracting again.', 429)
            usage.update(attempts=usage['attempts'] + 1, last=now.timestamp())
            connection.execute("INSERT INTO metadata(key,value) VALUES('ai_order_usage',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (json.dumps(usage),))
        # Network work must never hold the financial transaction lock.
        payload = self.provider.extract(text, context)
        return validate_draft(payload, catalogue, text)
