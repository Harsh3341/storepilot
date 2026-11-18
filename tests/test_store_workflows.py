"""Acceptance checks across billing, stock, credit, and order boundaries."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from storepilot.api import create_app


class StoreWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.catalogue = self.path / 'catalogue.json'
        self.catalogue.write_text(json.dumps([
            {'code': 'RICE', 'name': 'Rice', 'unit': 'kg', 'price': '40.00'},
            {'code': 'SOAP', 'name': 'Soap', 'unit': 'piece', 'price': '10.00'},
        ]), encoding='utf-8')
        self.database = self.path / 'store.sqlite3'
        self.client = self.enterContext(TestClient(create_app(self.catalogue, self.database)))

    def receive(self, code='RICE', quantity='2', request_id='receive'):
        return self.client.post('/api/stock', json={
            'product_code': code, 'quantity': quantity, 'kind': 'receive',
            'request_id': request_id,
        })

    def checkout(self, **changes):
        body = {'items': [{'product_code': 'RICE', 'quantity': '1'}],
                'paid_amount': '40.00', 'payment_method': 'cash', 'request_id': 'sale'}
        body.update(changes)
        return self.client.post('/api/sales', json=body)

    def stock(self, code='RICE'):
        return next(p['stock'] for p in self.client.get('/api/products').json() if p['code'] == code)

    def test_overpayment_rolls_back_every_record(self):
        self.receive()
        self.assertEqual(self.checkout(paid_amount='40.01').status_code, 422)
        self.assertEqual(self.stock(), '2')
        self.assertEqual(self.client.get('/api/sales').json(), [])
        self.assertEqual(len(self.client.get('/api/products/RICE/movements').json()), 1)

    def test_invalid_quantities_do_not_change_stock(self):
        self.receive()
        self.receive('SOAP', '5', 'soap-stock')
        for code, quantity, unit in [('RICE', '0.1', 'g'), ('SOAP', '0.5', 'piece'),
                                     ('RICE', '1e-999999', 'g'), ('RICE', 'Infinity', 'kg')]:
            with self.subTest(code=code, quantity=quantity):
                result = self.checkout(items=[{'product_code': code, 'quantity': quantity, 'unit': unit}])
                self.assertEqual(result.status_code, 422)
        self.assertEqual(self.stock(), '2')
        self.assertEqual(self.stock('SOAP'), '5')

    def test_adjustment_requires_explanation_and_cannot_make_stock_negative(self):
        self.receive()
        body = {'product_code': 'RICE', 'quantity': '-0.5', 'kind': 'adjust', 'request_id': 'adjust'}
        self.assertEqual(self.client.post('/api/stock', json=body).status_code, 422)
        body['reason'] = 'Damaged stock'
        self.assertEqual(self.client.post('/api/stock', json=body).json()['stock'], '1.5')
        body.update(quantity='-2', request_id='adjust-too-much')
        self.assertEqual(self.client.post('/api/stock', json=body).status_code, 422)
        self.assertEqual(self.stock(), '1.5')

    def test_idempotency_survives_new_app_and_price_changes(self):
        self.receive()
        original = self.checkout().json()
        self.client.put('/api/products/RICE', json={'name': 'New rice', 'price': '99.00', 'reorder_level': '0'})
        with TestClient(create_app(self.catalogue, self.database)) as other:
            repeat = other.post('/api/sales', json={
                'items': [{'product_code': 'RICE', 'quantity': '1'}],
                'paid_amount': '40.00', 'payment_method': 'cash', 'request_id': 'sale',
            })
            self.assertEqual(repeat.json(), original)
            self.assertEqual(len(other.get('/api/sales').json()), 1)
        self.assertEqual(self.stock(), '1')
        self.assertEqual(self.checkout(paid_amount='99.00').status_code, 409)

    def test_order_credit_and_final_repayment_flow(self):
        self.receive()
        customer = self.client.post('/api/customers', json={'name': 'Asha', 'phone': '9876543210'}).json()
        order = self.client.post('/api/orders', json={'customer_id': customer['id'],
            'source': 'whatsapp', 'note': 'Half kg rice',
            'items': [{'product_code': 'RICE', 'quantity': '500', 'unit': 'g'}]}).json()
        self.assertEqual(self.stock(), '2')
        sale = self.checkout(items=[{'product_code': 'RICE', 'quantity': '500', 'unit': 'g'}],
            customer_id=customer['id'], paid_amount='5.00', order_id=order['id']).json()
        self.assertEqual(sale['due_amount'], '15.00')
        self.assertEqual(self.stock(), '1.5')
        self.assertEqual(self.client.get('/api/orders?status=completed').json()[0]['sale_id'], sale['id'])
        payment = self.client.post(f"/api/customers/{customer['id']}/payments", json={
            'amount': '15.00', 'method': 'upi', 'request_id': 'repayment'}).json()
        self.assertEqual(payment['customer']['balance'], '0.00')
        summary = self.client.get('/api/summary').json()
        self.assertEqual(summary['today']['sales_total'], '20.00')
        self.assertEqual(summary['today']['paid_total'], '20.00')
        self.assertEqual(summary['outstanding_total'], '0.00')
        self.assertEqual(summary['pending_orders_count'], 0)

    def test_cancelled_order_does_not_allow_checkout(self):
        self.receive()
        order = self.client.post('/api/orders', json={'source': 'walk-in', 'note': 'Rice'}).json()
        self.client.patch(f"/api/orders/{order['id']}/status", json={'status': 'cancelled'})
        self.assertEqual(self.checkout(order_id=order['id']).status_code, 409)
        self.assertEqual(self.stock(), '2')
        self.assertEqual(self.client.get('/api/sales').json(), [])

    def test_financial_requests_reject_extra_totals_and_missing_retry_ids(self):
        self.receive()
        self.assertEqual(self.checkout(total='1.00').status_code, 422)
        self.assertEqual(self.checkout(request_id='').status_code, 422)
        self.assertEqual(self.checkout(paid_amount=40).status_code, 422)
        self.assertEqual(self.stock(), '2')
