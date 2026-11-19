import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from storepilot.auth import Auth
from storepilot.backup import backup_database, restore_database
from storepilot.catalogue import Product
from storepilot.store import Store


class BackupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.source = self.directory / 'store.sqlite3'
        self.backup = self.directory / 'backup.json'
        self.target = self.directory / 'restored.sqlite3'
        self.catalogue = {'RICE': Product('RICE', 'Rice', 'kg', Decimal('40.00'))}
        self.store = Store(self.source, self.catalogue)
        self.addCleanup(self.store.close)
        self.store.change_stock({'product_code': 'RICE', 'quantity': '2',
                                'kind': 'receive', 'request_id': 'stock'})
        self.customer = self.store.create_customer({'name': 'Asha'})
        self.sale = self.store.create_sale({'items': [{'product_code': 'RICE', 'quantity': '0.5'}],
            'customer_id': self.customer['id'], 'paid_amount': '5.00',
            'payment_method': 'cash', 'request_id': 'sale'})

    def test_live_backup_restores_financial_records_and_owner(self):
        auth = Auth(self.store.database)
        auth.setup_owner('owner', 'testing-password-123')
        session = auth.login('owner', 'testing-password-123', '127.0.0.1')
        backup_database(self.source, self.backup)
        restore_database(self.backup, self.target)
        restored = Store(self.target, self.catalogue)
        self.addCleanup(restored.close)
        self.assertEqual(restored.product('RICE')['stock'], '1.5')
        self.assertEqual(restored.sale(self.sale['id']), self.sale)
        self.assertEqual(restored.ledger(self.customer['id'])['customer']['balance'], '15.00')
        restored_auth = Auth(restored.database)
        self.assertTrue(restored_auth.has_owner())
        self.assertIsNone(restored_auth.session(session['token']))
        self.assertTrue(restored_auth.login('owner', 'testing-password-123', '127.0.0.1')['token'])
        new = restored.create_customer({'name': 'Bina'})
        self.assertGreater(new['id'], self.customer['id'])

    def test_restore_refuses_existing_database(self):
        backup_database(self.source, self.backup)
        with self.assertRaises(ValueError):
            restore_database(self.backup, self.source)
        self.assertEqual(self.store.product('RICE')['stock'], '1.5')

    def test_backup_refuses_overwriting_an_existing_file(self):
        backup_database(self.source, self.backup)
        original = self.backup.read_bytes()
        with self.assertRaises(FileExistsError):
            backup_database(self.source, self.backup)
        self.assertEqual(self.backup.read_bytes(), original)

    def test_unknown_table_is_rejected_before_restore(self):
        self.backup.write_text(json.dumps({'format': 'storepilot-backup-v1',
            'tables': {'products; DROP TABLE customers': []}}), encoding='utf-8')
        with self.assertRaises(ValueError):
            restore_database(self.backup, self.target)
        self.assertFalse(self.target.exists())

    def test_invalid_financial_data_rolls_back_restore(self):
        backup_database(self.source, self.backup)
        body = json.loads(self.backup.read_text(encoding='utf-8'))
        body['tables']['products'][0]['stock'] = -1
        self.backup.write_text(json.dumps(body), encoding='utf-8')
        with self.assertRaises(ValueError):
            restore_database(self.backup, self.target)
        restored = Store(self.target, self.catalogue)
        self.addCleanup(restored.close)
        self.assertEqual(restored.customers(), [])
        self.assertEqual(restored.sales(), [])
