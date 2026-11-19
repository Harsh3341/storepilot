"""Owner provisioning, backup, and migration commands; passwords never use CLI arguments."""

import argparse
from getpass import getpass
import os
from pathlib import Path
import secrets

from dotenv import load_dotenv

from storepilot.auth import Auth, hash_password
from storepilot.backup import backup_database, migrate_database, restore_database
from storepilot.database import Database

ROOT = Path(__file__).resolve().parents[1]


def _database(argument):
    if argument:
        if str(argument).startswith(('postgres://', 'postgresql://')):
            raise ValueError('Keep connection credentials in STOREPILOT_DATABASE_URL, not command arguments.')
        return argument
    return os.environ.get('STOREPILOT_DATABASE_URL') or os.environ.get('STOREPILOT_DB') or ROOT / 'data' / 'storepilot.sqlite3'


def main(argv=None):
    load_dotenv(ROOT / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    owner = subparsers.add_parser('setup-owner', help='Create/reset the owner account.')
    owner.add_argument('--database', help='Local SQLite path; otherwise use configured database.')
    owner.add_argument('--username', default='owner')
    owner.add_argument('--reset', action='store_true', help='Explicitly replace existing owner credentials and revoke sessions.')
    owner.add_argument('--generate', action='store_true', help='Generate a password and save it only in a local credentials file.')
    owner.add_argument('--credentials-file', default=str(ROOT / 'data' / 'owner-login.txt'))
    backup = subparsers.add_parser('backup', help='Save a portable backup, omitting active sessions.')
    backup.add_argument('destination')
    backup.add_argument('--database')
    restore = subparsers.add_parser('restore', help='Restore into a new SQLite path or empty configured PostgreSQL database.')
    restore.add_argument('source')
    restore.add_argument('--database')
    migrate = subparsers.add_parser('migrate', help='Copy local SQLite records into empty configured PostgreSQL.')
    migrate.add_argument('--source', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'setup-owner':
            credentials = Path(args.credentials_file)
            if args.generate and credentials.exists():
                raise ValueError('Choose a new credentials filename; existing credentials are preserved.')
            database = Database(_database(args.database))
            try:
                auth = Auth(database)
                if auth.has_owner() and not args.reset:
                    raise ValueError('An owner already exists. Use --reset to explicitly replace credentials.')
                password = secrets.token_urlsafe(18) if args.generate else getpass('New owner password: ')
                if not args.generate and password != getpass('Confirm password: '):
                    raise ValueError('Passwords do not match.')
                encoded = hash_password(password)
                if args.generate:
                    credentials.parent.mkdir(parents=True, exist_ok=True)
                    with credentials.open('x', encoding='utf-8') as output:
                        credentials.chmod(0o600)
                        output.write(f'Username: {args.username}\nPassword: {password}\n\n'
                                     f"STOREPILOT_OWNER_USERNAME={args.username}\n"
                                     f"STOREPILOT_OWNER_PASSWORD_HASH='{encoded}'\n")
                auth.setup_owner_hash(args.username, encoded)
                if args.generate:
                    print(f'Owner configured. Local credentials saved to {credentials}.')
                else:
                    print('Owner configured. Existing sessions were revoked if credentials changed.')
            finally:
                database.close()
        elif args.command == 'backup':
            backup_database(_database(args.database), args.destination)
            print('Backup saved. Keep it private; it includes customer records and the owner password hash.')
        elif args.command == 'restore':
            restore_database(args.source, _database(args.database))
            print('Restore completed. Sign in again; active sessions were not restored.')
        else:
            target = os.environ.get('STOREPILOT_DATABASE_URL', '')
            if not target.startswith(('postgres://', 'postgresql://')):
                raise ValueError('Set STOREPILOT_DATABASE_URL for the cloud destination before migration.')
            migrate_database(args.source, target)
            print('Migration completed. Historical bills, stock, balances, and retry IDs were preserved.')
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
