"""Model suggestions must remain bounded, reviewable, and financially inert."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest

import httpx

from storepilot.catalogue import Product
from storepilot.store import Store, StoreError
from storepilot.groq import GroqProvider, ProviderError
from storepilot.order_extraction import ExtractionService, validate_draft


CATALOGUE = {
    'SUGAR': Product('SUGAR', 'Loose sugar', 'kg', Decimal('48.00')),
    'SOAP': Product('SOAP', 'Lux soap', 'piece', Decimal('20.00')),
}


def row(original='500 g sugar', code='SUGAR', quantity='500', unit='g', reason=None):
    return {'original': original, 'product_code': code, 'quantity': quantity,
            'unit': unit, 'reason': reason}


class DraftTests(unittest.TestCase):
    def test_numeric_brand_and_price_do_not_supply_packet_counts(self):
        catalogue = {**CATALOGUE, 'FIVE-STAR': Product('FIVE-STAR', '5 Star chocolate', 'piece', Decimal('10.00'))}
        for original, code, quantity in (
                ('5 Star chocolate', 'FIVE-STAR', '5'), ('soap ₹5', 'SOAP', '5'),
                ('soap Rs 5', 'SOAP', '5')):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, code, quantity, 'piece')]}, catalogue, original)
                self.assertIsNone(draft['rows'][0]['quantity'])
        for original, quantity in (('2 5 Star chocolate', '2'), ('5 pieces 5 Star chocolate', '5')):
            draft = validate_draft({'items': [row(original, 'FIVE-STAR', quantity, 'piece')]}, catalogue, original)
            self.assertIsNone(draft['rows'][0]['reason'])

    def test_loose_quantity_evidence_never_matches_a_numeric_suffix(self):
        for original, quantity in (('.5kg sugar', '5'), ('-1kg sugar', '1'), ('1.5kg sugar', '5')):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, 'SUGAR', quantity, 'kg')]}, CATALOGUE, original)
                self.assertIsNone(draft['rows'][0]['quantity'])
        draft = validate_draft({'items': [row('.5kg sugar', 'SUGAR', '0.5', 'kg')]}, CATALOGUE, '.5kg sugar')
        self.assertIsNone(draft['rows'][0]['reason'])

    def test_loose_goods_do_not_invent_amount_or_unit_from_a_product_name(self):
        for original in ('sugar', 'sugar please', '1 sugar'):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, 'SUGAR', '1', 'kg')]}, CATALOGUE, original)
                self.assertIsNone(draft['rows'][0]['quantity'])
                self.assertTrue(draft['rows'][0]['reason'])

    def test_explicit_loose_quantities_allow_exact_conversion_and_language_words(self):
        for original, quantity, unit in (
                ('500 g sugar', '0.5', 'kg'), ('half kg sugar', '0.5', 'kg'),
                ('आधा किलो चीनी', '0.5', 'kg'), ('aadha kilo chini', '500', 'g'),
                ('दो किलो चीनी', '2', 'kg'), ('250 grams sugar', '250', 'g')):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, 'SUGAR', quantity, unit)]}, CATALOGUE, original)
                self.assertIsNone(draft['rows'][0]['reason'])

    def test_pack_weight_never_supplies_a_missing_piece_count(self):
        for original in ('Lux soap 100 g', 'Lux soap 100g', 'Lux साबुन 100 ग्राम'):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, 'SOAP', '1', 'piece')]}, CATALOGUE, original)
                self.assertIsNone(draft['rows'][0]['quantity'])
                self.assertTrue(draft['rows'][0]['reason'])

    def test_explicit_packet_counts_in_three_languages_are_accepted(self):
        for original in ('2 Lux soap 100 g', 'two Lux soap 100 g', 'दो Lux साबुन 100 ग्राम', 'do Lux sabun 100g'):
            with self.subTest(original=original):
                draft = validate_draft({'items': [row(original, 'SOAP', '2', 'piece')]}, CATALOGUE, original)
                self.assertIsNone(draft['rows'][0]['reason'])

    def test_exact_grams_remain_text_and_require_review(self):
        draft = validate_draft({'items': [row()]}, CATALOGUE, '500 g sugar')
        self.assertTrue(draft['requires_review'])
        self.assertEqual(draft['rows'][0]['quantity'], '500')
        self.assertIsNone(draft['rows'][0]['reason'])

    def test_uncertain_or_invalid_suggestions_are_unresolved(self):
        for item in (row(code='UNKNOWN'), row(quantity=None), row(unit=None),
                     row(quantity='NaN'), row(quantity='0'), row(quantity='1e100'),
                     row(quantity=500), row(quantity='0.5', unit='piece', code='SOAP'),
                     row(quantity='0.5', unit='g'), row(original='invented'),
                     row(reason='Choose a pack size')):
            with self.subTest(item=item):
                # Invalid types fail the whole provider envelope; valid types
                # with uncertain business meaning remain editable.
                if isinstance(item['quantity'], int):
                    with self.assertRaises(ProviderError):
                        validate_draft({'items': [item]}, CATALOGUE, '500 g sugar')
                else:
                    draft = validate_draft({'items': [item]}, CATALOGUE, '500 g sugar')
                    self.assertTrue(draft['rows'][0]['reason'])

    def test_extra_financial_fields_and_oversized_output_are_rejected(self):
        for payload in ({'items': [{**row(), 'price': '1'}]},
                        {'items': [row()] * 51}, {'items': [], 'total': 1}):
            with self.subTest(payload=payload):
                with self.assertRaises(ProviderError):
                    validate_draft(payload, CATALOGUE, '500 g sugar')


class ProviderTests(unittest.TestCase):
    def test_malformed_provider_envelopes_fail_as_safe_errors(self):
        for envelope in ({'choices': [{'finish_reason': 'stop', 'message': 'bad'}]},
                         {'choices': [{'finish_reason': 'stop', 'message': None}]},
                         {'choices': []}, {'choices': 'bad'}, None):
            with self.subTest(envelope=envelope):
                provider = self.provider(lambda request: httpx.Response(200, json=envelope))
                with self.assertRaises(ProviderError):
                    provider.extract('500 g sugar', [])

    def provider(self, handler):
        client = self.enterContext(httpx.Client(transport=httpx.MockTransport(handler)))
        return GroqProvider('private-test-key', client=client)

    def test_request_is_strict_and_contains_no_catalogue_prices(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(str(request.url), 'https://api.groq.com/openai/v1/chat/completions')
            self.assertEqual(payload['model'], 'openai/gpt-oss-120b')
            self.assertTrue(payload['response_format']['json_schema']['strict'])
            self.assertNotIn('tools', payload)
            catalogue = json.loads(payload['messages'][1]['content'])['catalogue']
            self.assertEqual(set(catalogue[0]), {'code', 'name', 'unit'})
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps({'items': [row()]})}}]})
        self.assertEqual(self.provider(handler).extract('500 g sugar',
            [{'code': p.code, 'name': p.name, 'unit': p.unit} for p in CATALOGUE.values()])['items'][0], row())

    def test_failures_are_redacted_and_never_retried(self):
        for kind in ('rate', 'auth', 'server', 'timeout', 'json', 'truncated', 'large'):
            calls = []
            def handler(request):
                calls.append(request)
                if kind == 'timeout':
                    raise httpx.ReadTimeout('private-test-key', request=request)
                if kind in ('rate', 'auth', 'server'):
                    return httpx.Response({'rate': 429, 'auth': 401, 'server': 500}[kind], text='private-test-key')
                content = 'not json' if kind == 'json' else json.dumps({'items': [row()]})
                if kind == 'large':
                    return httpx.Response(200, text='x' * 40000)
                return httpx.Response(200, json={'choices': [{'finish_reason': 'length' if kind == 'truncated' else 'stop',
                    'message': {'content': content}}]})
            with self.subTest(kind=kind):
                with self.assertRaises(ProviderError) as caught:
                    self.provider(handler).extract('500 g sugar', [])
                self.assertNotIn('private-test-key', str(caught.exception))
                self.assertEqual(len(calls), 1)


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:', CATALOGUE)
        self.addCleanup(self.store.close)
        self.now = datetime(2026, 11, 19, 17, 0, 0, tzinfo=timezone.utc)
        self.calls = 0
        owner = self
        class Provider:
            def extract(self, text, catalogue):
                # A transaction may not be held while the model responds.
                owner.assertFalse(owner.store.connection.in_transaction)
                owner.calls += 1
                return {'items': [row()]}
        self.service = ExtractionService(self.store, Provider(), clock=lambda: self.now)

    def test_cooldown_and_india_daily_quota_survive_service_recreation(self):
        self.service.extract('500 g sugar')
        with self.assertRaises(StoreError) as caught:
            self.service.extract('500 g sugar')
        self.assertEqual(caught.exception.status_code, 429)
        recreated = ExtractionService(self.store, self.service.provider, clock=lambda: self.now)
        self.assertEqual(recreated.status()['remaining'], 24)
        for _ in range(24):
            self.now += timedelta(seconds=10)
            recreated.extract('500 g sugar')
        with self.assertRaises(StoreError):
            self.now += timedelta(seconds=10)
            recreated.extract('500 g sugar')
        self.now = datetime(2026, 11, 19, 18, 30, 1, tzinfo=timezone.utc)
        self.assertEqual(recreated.status()['remaining'], 25)

    def test_invalid_input_and_empty_catalogue_do_not_spend_quota(self):
        for text in (' ', 'x' * 2001):
            with self.assertRaises(StoreError):
                self.service.extract(text)
        with self.store.database.transaction() as connection:
            connection.execute('DELETE FROM products')
        with self.assertRaises(StoreError):
            self.service.extract('500 g sugar')
        self.assertEqual(self.service.status()['remaining'], 25)
        self.assertEqual(self.calls, 0)

    def test_failed_provider_attempt_is_reserved_without_store_writes(self):
        class Broken:
            def extract(self, text, catalogue):
                raise ProviderError('Unavailable', 503)
        service = ExtractionService(self.store, Broken(), clock=lambda: self.now)
        with self.assertRaises(ProviderError):
            service.extract('500 g sugar')
        self.assertEqual(service.status()['remaining'], 24)
        self.assertEqual(self.store.orders(), [])
        self.assertEqual(self.store.sales(), [])
        self.assertEqual(self.store.customers(), [])
        self.assertTrue(all(p['stock'] == '0' for p in self.store.products()))
