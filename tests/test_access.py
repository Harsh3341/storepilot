import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from storepilot.api import create_app
from storepilot.auth import Auth
from storepilot.catalogue import load_catalogue
from storepilot.settings import Settings
from storepilot.store import Store


class ProtectedAppTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.catalogue = self.directory / 'catalogue.json'
        self.catalogue.write_text(json.dumps([
            {'code': 'RICE', 'name': 'Rice', 'unit': 'kg', 'price': '40.00'},
        ]), encoding='utf-8')
        self.database = self.directory / 'store.sqlite3'
        store = Store(self.database, load_catalogue(self.catalogue))
        Auth(store.database).setup_owner('owner', 'testing-password-123')
        store.close()
        self.settings = Settings(environment='development', origin='http://testserver')
        self.app = create_app(self.catalogue, self.database, settings=self.settings)
        self.client = self.enterContext(TestClient(self.app))

    def login(self):
        response = self.client.post('/api/auth/login', json={
            'username': 'owner', 'password': 'testing-password-123',
        }, headers={'Origin': 'http://testserver'})
        self.assertEqual(response.status_code, 200)
        return response.json()['csrf_token']

    def test_every_business_and_documentation_route_requires_login(self):
        for url in ['/api/products', '/api/summary', '/api/customers', '/api/orders',
                    '/api/sales', '/products', '/docs', '/openapi.json', '/redoc']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(self.client.post('/bills/preview', json={
            'items': [{'product_code': 'RICE', 'quantity': '1'}],
        }).status_code, 401)
        self.assertEqual(self.client.get('/health').status_code, 200)

    def test_authenticated_read_and_mutation_with_csrf(self):
        csrf = self.login()
        self.assertEqual(self.client.get('/api/products').status_code, 200)
        response = self.client.post('/api/customers', json={'name': 'Asha'},
            headers={'Origin': 'http://testserver', 'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 201)

    def test_missing_or_wrong_csrf_rejects_financial_write(self):
        self.login()
        for headers in [{}, {'X-CSRF-Token': 'invalid'}]:
            with self.subTest(headers=headers):
                response = self.client.post('/api/stock', json={
                    'product_code': 'RICE', 'quantity': '1', 'kind': 'receive',
                    'request_id': 'stock',
                }, headers=headers)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/products').json()[0]['stock'], '0')

    def test_non_ascii_csrf_is_rejected_without_a_server_error(self):
        self.login()
        response = self.client.post('/api/customers', json={'name': 'Asha'},
            headers=[(b'x-csrf-token', b'\xff')])
        self.assertEqual(response.status_code, 403)

    def test_cross_origin_login_and_writes_are_rejected(self):
        body = {'username': 'owner', 'password': 'testing-password-123'}
        self.assertEqual(self.client.post('/api/auth/login', json=body,
            headers={'Origin': 'https://another.example'}).status_code, 403)
        csrf = self.login()
        self.assertEqual(self.client.post('/api/customers', json={'name': 'Asha'},
            headers={'Origin': 'https://another.example', 'X-CSRF-Token': csrf}).status_code, 403)
        self.assertEqual(self.client.get('/api/customers').json(), [])

    def test_logout_revokes_copied_cookie(self):
        csrf = self.login()
        token = self.client.cookies.get('storepilot_session')
        self.assertEqual(self.client.post('/api/auth/logout',
            headers={'X-CSRF-Token': csrf}).status_code, 200)
        self.assertEqual(self.client.get('/api/products',
            headers={'Cookie': f'storepilot_session={token}'}).status_code, 401)

    def test_existing_session_survives_app_restart(self):
        self.login()
        cookie = self.client.cookies.get('storepilot_session')
        with TestClient(create_app(self.catalogue, self.database, settings=self.settings)) as other:
            response = other.get('/api/auth/session', headers={'Cookie': f'storepilot_session={cookie}'})
            self.assertTrue(response.json()['authenticated'])

    def test_production_cookie_is_secure_and_http_only(self):
        config = Settings(environment='production', origin='https://shop.example')
        with TestClient(create_app(self.catalogue, self.database, settings=config),
                        base_url='https://shop.example') as client:
            response = client.post('/api/auth/login', json={
                'username': 'owner', 'password': 'testing-password-123',
            }, headers={'Origin': 'https://shop.example'})
            self.assertEqual(response.status_code, 200)
            cookie = response.headers['set-cookie'].lower()
            for attribute in ['httponly', 'secure', 'samesite=lax', 'path=/']:
                self.assertIn(attribute, cookie)


class ProductionSettingsTests(unittest.TestCase):
    def test_production_requires_https_origin(self):
        for origin in ['', 'http://shop.example', 'https://shop.example/path',
                       'https://user:password@shop.example', 'https://shop.example?x=1']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                Settings(environment='production', origin=origin)

    def test_production_cannot_start_without_an_owner(self):
        with self.assertRaisesRegex(ValueError, 'owner'):
            create_app(database_path=':memory:',
                settings=Settings(environment='production', origin='https://shop.example'))
