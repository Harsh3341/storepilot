# StorePilot

Billing, inventory, customer dues, and orders for a single general-store owner. StorePilot uses a mobile React PWA and Python/FastAPI, with SQLite locally and PostgreSQL for cloud hosting.

- Sell loose goods in grams/kg and packaged goods in whole pieces, with catalogue prices and saved receipts.
- Receive stock, record explained adjustments, and inspect movements and low-stock alerts.
- Track customer credit, partial payments, and cash/UPI repayments.
- Keep walk-in orders or pasted WhatsApp lists, and complete them through billing.
- Reopen, print, copy, or share receipts from sales history.

## Run on Windows

Install Python 3.12+ and Node.js 22.12+ (or 24+). From this repository in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm build
cd ..
.\.venv\Scripts\python.exe -m storepilot.manage setup-owner --username owner --generate
.\.venv\Scripts\python.exe -m uvicorn storepilot.api:create_app --factory --host 127.0.0.1 --port 8000
```

If pnpm is installed directly, use `pnpm` instead of `corepack pnpm`. Open **http://127.0.0.1:8000**. Keep the server terminal running. On macOS/Linux use `.venv/bin/python`.

Sign in with the credentials in `data/owner-login.txt`. Keep that file private; it is excluded from Git and Docker. Run setup only once. To choose your own password, omit `--generate`; the command prompts without echoing it. Passwords must contain at least 12 characters.

For development, copy `.env.example` to `.env` and set `STOREPILOT_ORIGIN=http://127.0.0.1:5173` before starting the backend. Run `pnpm dev` inside frontend in another terminal. Vite runs at http://127.0.0.1:5173 and proxies the store API to port 8000. Remove this origin override when using the backend's built frontend on port 8000.

Frontend source is formatted TypeScript and JSX in `frontend/src`. Run `pnpm format` to format edits and `pnpm format:check` to verify style. Vite minifies only the generated production files in `frontend/dist`.

## First use and data

New databases contain 20 illustrative products with **zero stock**. In Stock, edit prices to match the store and receive the actual opening stock. Give each brand/pack size a separate product code. Editing seed JSON after database creation does not update stored products; use Stock.

Records persist in `data/storepilot.sqlite3`. For a separate database, set an absolute path before starting the server:

```powershell
$env:STOREPILOT_DB = 'E:\Projects\AI\data\my-store.sqlite3'
```

Preserve the database when updating the code. Use the backup command below to take a consistent snapshot while the app is running.

Save a bill after confirming quantities and amount received. A balance due requires a customer. Stock is deducted only when saved. Retrying the same request does not create another sale. Names and prices on saved receipts stay unchanged after catalogue edits. Cash/UPI records payments manually; it does not process bank transfers.

Paste a WhatsApp list into Orders, then select the actual products while billing. Automatic WhatsApp ingestion and AI extraction are later features. These are simple store receipts; GST/tax invoicing, returns, multi-user access, barcode scanning, and payment-provider integration are outside this MVP.

The owner account protects store APIs and API documentation. Sessions use HttpOnly cookies and expire after seven days. A password reset revokes existing sessions. Unconfigured development databases allow local use without login; production refuses startup without an owner and an HTTPS origin.

## Free cloud testing with Render and Neon

Use a **Render Free web service** and a **Neon Free PostgreSQL database**. The database stays separate from Render's temporary filesystem. Render's free service sleeps after inactivity, so the first visit may take about a minute to load. Free usage limits apply; this setup is for testing. See [Render's free-service limits](https://render.com/docs/free) and [Neon's plans](https://neon.com/docs/introduction/plans).

1. Push this repository to your private GitHub repository. Connect that repository to Render when prompted.
2. Create a Neon project on the **Free** plan. Choose a region close to your store and, where available, the same region in Render. Copy the PostgreSQL connection string from Neon's Connect dialog, including `sslmode=require`.
3. Copy `.env.example` to `.env` locally. Set `STOREPILOT_DATABASE_URL` to the Neon connection string, enclosed in single quotes. Keep `.env` out of Git and never paste credentials into an issue or chat.
4. If preserving an existing local store, run the migration command below **before the first cloud app startup**. It requires an empty destination and preserves stock, receipts, balances, and retry IDs. For a fresh test store, skip migration; the first startup seeds products with zero stock.
5. In Render choose **New > Blueprint**, select this repository and the `feat/store-mvp` branch, and use `render.yaml`. Confirm the service plan is **Free**. The blueprint creates only a web service, with no Render database or paid disk. If using **New > Web Service** instead, select Docker, Free, and `/health` as the health-check path.
6. Set the following Render environment values. Read the username and password hash from your private `data/owner-login.txt`. Copy the hash value without the surrounding quotes; do not use the raw password as the hash.

| Variable | Value |
|---|---|
| `STOREPILOT_ENV` | `production` |
| `STOREPILOT_DATABASE_URL` | Neon connection string with SSL enabled |
| `STOREPILOT_OWNER_USERNAME` | Your configured username, normally `owner` |
| `STOREPILOT_OWNER_PASSWORD_HASH` | The complete `pbkdf2_sha256$...` value |

Render supplies the HTTPS origin through `RENDER_EXTERNAL_URL`. No custom domain is needed. When using another host or a custom domain, explicitly set `STOREPILOT_ORIGIN` to the exact HTTPS origin without a path. Keep owner environment values consistent across redeployments; changing them resets the account and revokes sessions.

After deployment, open the Render HTTPS URL and sign in. Check stock, save a small test sale, reload the receipt, then redeploy and confirm the sale remains. On Android, open that URL in Chrome and choose **Install app** or **Add to Home screen**. The app needs internet for store data and billing; financial writes are never queued offline.

## Backups, migration, and password reset

These commands use `STOREPILOT_DATABASE_URL` from your local `.env` when set, otherwise `STOREPILOT_DB` or the default SQLite database. Cloud connection credentials belong in `.env`, not command arguments.

```powershell
# Save a consistent portable snapshot. Choose a new filename for each backup.
.\.venv\Scripts\python.exe -m storepilot.manage backup backups\store-2026-11-19.json

# Restore to a NEW local SQLite file.
.\.venv\Scripts\python.exe -m storepilot.manage restore backups\store-2026-11-19.json --database data\restored.sqlite3

# Copy the existing local store into an EMPTY Neon database configured in .env.
.\.venv\Scripts\python.exe -m storepilot.manage migrate --source data\storepilot.sqlite3

# Reset the configured database's owner; use a new private credentials filename.
.\.venv\Scripts\python.exe -m storepilot.manage setup-owner --username owner --reset --generate --credentials-file data\reset-login.txt
```

Backups include customer records and the owner password hash, and exclude active sessions. Store a private copy outside this computer before relying on the app. Restore refuses an existing SQLite file or a populated PostgreSQL destination. To restore directly to an empty cloud database configured in `.env`, omit `--database`.

For a cloud password reset, also replace `STOREPILOT_OWNER_PASSWORD_HASH` in Render with the newly generated hash before redeploying. Otherwise the old environment hash will restore the old password on the next startup.

## Checks and API

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m storepilot --demo
cd frontend
pnpm build
pnpm format:check
```

API documentation: http://127.0.0.1:8000/docs after signing in on the same origin. Existing `/products`, `/bills/preview`, and the CLI remain available. CLI bills are unsaved drafts and do not affect the database. To include real PostgreSQL integration checks, set `STOREPILOT_TEST_DATABASE_URL` to a dedicated test database before running the suite; tests create and drop their own schemas.

Money uses Decimal calculations and integer paise in storage; stock uses integer grams or pieces. Sales, stock updates, and repayments require retry IDs and run in transactions.

| File | Responsibility |
|---|---|
| storepilot/catalogue.py, billing.py | Product validation, unit conversion, bill calculation |
| storepilot/database.py, postgres.py, store.py | SQLite/PostgreSQL storage and transactional business rules |
| storepilot/api.py, store_api.py | HTTP routes and web asset serving |
| storepilot/auth.py, auth_api.py, settings.py | Owner sessions and deployment configuration |
| storepilot/backup.py, manage.py | Portable backups, restore, migration, and owner setup |
| Dockerfile, render.yaml | Container build and free Render deployment |
| frontend/src/ | Mobile store interface |
| frontend/public/ | PWA manifest, icons, app-shell service worker |
| tests/ | Domain, transaction, API, and persistence checks |
