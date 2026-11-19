"""Portable, consistent store backups and restore into an empty database."""

import json
from pathlib import Path
import sqlite3
import tempfile

from storepilot.auth import Auth
from storepilot.database import Database

TABLES = ('products', 'customers', 'sales', 'sale_lines', 'movements',
          'payments', 'ledger', 'orders', 'requests', 'auth_owner', 'metadata')
IDENTITY_TABLES = ('customers', 'sales', 'sale_lines', 'movements', 'payments', 'ledger', 'orders')
FORMAT = 'storepilot-backup-v1'


def _postgres(location) -> bool:
    return str(location).startswith(('postgres://', 'postgresql://'))


def backup_database(source, destination: Path | str):
    destination = Path(destination)
    if not _postgres(source) and not Path(source).is_file():
        raise ValueError('The source database does not exist.')
    if destination.exists():
        raise FileExistsError('Choose a new backup filename; existing backups are preserved.')
    database = Database(source)
    try:
        Auth(database)
        with database.transaction() as connection:
            tables = {}
            for table in TABLES:
                query = f'SELECT * FROM {table}' + (' ORDER BY rowid' if table == 'products' else '')
                tables[table] = [{key: value for key, value in dict(row).items()
                                  if not (table == 'products' and key == 'rowid')}
                                 for row in connection.execute(query).fetchall()]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as output:
            destination.chmod(0o600)
            json.dump({'format': FORMAT, 'tables': tables}, output, ensure_ascii=False, indent=2)
            output.write('\n')
    finally:
        database.close()


def restore_database(source: Path | str, destination):
    data = json.loads(Path(source).read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('format') != FORMAT
            or not isinstance(data.get('tables'), dict) or set(data['tables']) != set(TABLES)):
        raise ValueError('This is not a supported StorePilot backup.')
    if not _postgres(destination) and Path(destination).exists():
        raise ValueError('Restore to a new database path; existing databases are preserved.')
    database = Database(destination)
    try:
        Auth(database)
        with database.transaction() as connection:
            if any(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in TABLES):
                raise ValueError('The destination database must be empty.')
            for table in TABLES:
                rows = data['tables'][table]
                if not isinstance(rows, list):
                    raise ValueError(f'Invalid records in backup table {table}.')
                cursor = connection.execute(f'SELECT * FROM {table} LIMIT 0')
                columns = [column[0] for column in cursor.description
                           if not (table == 'products' and column[0] == 'rowid')]
                for row in rows:
                    if not isinstance(row, dict) or set(row) != set(columns):
                        raise ValueError(f'Invalid columns in backup table {table}.')
                    placeholders = ','.join('?' for _ in columns)
                    connection.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
                                       tuple(row[column] for column in columns))
            if _postgres(destination):
                for table in IDENTITY_TABLES:
                    connection.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"COALESCE(MAX(id), 1), COUNT(*) > 0) FROM {table}")
    except sqlite3.Error as error:
        raise ValueError('Backup records are invalid; the restore was rolled back.') from error
    finally:
        database.close()


def migrate_database(source, destination):
    """Transfer a consistent snapshot, including historical receipts and retry IDs."""
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / 'migration.json'
        backup_database(source, snapshot)
        restore_database(snapshot, destination)
