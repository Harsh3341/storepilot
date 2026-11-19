"""Observable order extraction and retry behavior with isolated store data."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from storepilot.api import create_app
from storepilot.settings import Settings


class ExtractionApiTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.catalogue = self.root / 'catalogue.json'
        self.catalogue.write_text(json.dumps([
            {'code': 'SUGAR', 'name': 'Loose sugar', 'unit': 'kg', 'price': '48.00'},
            {'code': 'SOAP', 'name': 'Lux soap', 'unit': 'piece', 'price': '20.00'},
        ]), encoding='utf-8')
        self.database = self.root / 'store.sqlite3'
        self.client = self.enterContext(TestClient(create_app(self.catalogue, self.database)))

    def test_unconfigured_extraction_is_reported_without_exposing_credentials(self):
        response = self.client.get('/api/orders/extraction-status')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['enabled'])
        self.assertNotIn('key', response.json())

    def test_missing_key_does_not_prevent_note_only_orders(self):
        response = self.client.post('/api/orders/extract', json={'text': '500 g sugar'})
        self.assertEqual(response.status_code, 503)
        saved = self.client.post('/api/orders', json={'note': '500 g sugar'})
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()['items'], [])
        self.assertEqual(self.client.get('/api/sales').json(), [])

    def test_retried_reviewed_order_is_saved_once(self):
        body = {'note': '500 g sugar', 'source': 'whatsapp', 'request_id': 'reviewed-order',
                'items': [{'product_code': 'SUGAR', 'quantity': '500', 'unit': 'g'}]}
        first = self.client.post('/api/orders', json=body)
        self.assertEqual(first.status_code, 201)
        repeated = self.client.post('/api/orders', json=body)
        self.assertEqual(repeated.json(), first.json())
        self.assertEqual(len(self.client.get('/api/orders').json()), 1)
        self.assertEqual(first.json()['estimated_total'], '24.00')
        self.assertEqual(self.client.get('/api/products').json()[1]['stock'], '0')
        self.assertEqual(self.client.get('/api/sales').json(), [])

    def test_changed_order_body_cannot_reuse_a_request_id(self):
        body = {'note': 'one soap', 'request_id': 'same-order'}
        self.assertEqual(self.client.post('/api/orders', json=body).status_code, 201)
        body['note'] = 'two soap'
        self.assertEqual(self.client.post('/api/orders', json=body).status_code, 409)

    def test_extraction_preview_changes_no_business_records(self):
        class Provider:
            def extract(self, text, catalogue):
                return {'items': [{'original': '500 g sugar', 'product_code': 'SUGAR',
                    'quantity': '500', 'unit': 'g', 'reason': None}]}
        app = create_app(self.catalogue, ':memory:', settings=Settings(), extraction_provider=Provider())
        with TestClient(app) as client:
            before = {path: client.get('/api/' + path).json() for path in ('products', 'customers', 'orders', 'sales', 'summary')}
            result = client.post('/api/orders/extract', json={'text': '500 g sugar'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['rows'][0]['product_code'], 'SUGAR')
            self.assertEqual(result.headers['cache-control'], 'no-store')
            self.assertEqual({path: client.get('/api/' + path).json() for path in before}, before)

    def test_extraction_requires_owner_and_valid_csrf_before_spending_quota(self):
        class Provider:
            def extract(self, text, catalogue):
                return {'items': []}
        app = create_app(self.catalogue, ':memory:', settings=Settings(), extraction_provider=Provider())
        app.state.auth.setup_owner('owner', 'correct horse store battery')
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/orders/extraction-status').status_code, 401)
            self.assertEqual(client.post('/api/orders/extract', json={'text': 'sugar'}).status_code, 401)
            login = client.post('/api/auth/login', json={'username': 'owner', 'password': 'correct horse store battery'}).json()
            self.assertEqual(client.post('/api/orders/extract', json={'text': 'sugar'}).status_code, 403)
            headers = {'X-CSRF-Token': login['csrf_token'], 'Origin': 'https://other.example'}
            self.assertEqual(client.post('/api/orders/extract', json={'text': 'sugar'}, headers=headers).status_code, 403)
            self.assertEqual(client.get('/api/orders/extraction-status').json()['remaining'], 25)
            headers['Origin'] = 'http://testserver'
            self.assertEqual(client.post('/api/orders/extract', json={'text': 'sugar'}, headers=headers).status_code, 200)

    def test_invalid_ai_input_preserves_full_length_note_only_workflow(self):
        for body in ({'text': 'x' * 2001}, {'text': 12}, {'text': 'sugar', 'price': '1'}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post('/api/orders/extract', json=body).status_code, 422)
        self.assertEqual(self.client.post('/api/orders', json={'note': 'x' * 5000}).status_code, 201)
