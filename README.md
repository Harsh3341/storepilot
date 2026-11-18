# StorePilot

Billing, inventory, customer dues, and orders for a single general-store owner. The first MVP uses a mobile React interface and a Python/FastAPI backend backed by SQLite.

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
.\.venv\Scripts\python.exe -m uvicorn storepilot.api:create_app --factory --host 127.0.0.1 --port 8000
```

If pnpm is installed directly, use `pnpm` instead of `corepack pnpm`. Open **http://127.0.0.1:8000**. Keep the server terminal running. On macOS/Linux use `.venv/bin/python`.

For development, run the backend above and `pnpm dev` inside frontend in another terminal. Vite runs at http://127.0.0.1:5173 and proxies the store API to port 8000.

Frontend source is formatted TypeScript and JSX in `frontend/src`. Run `pnpm format` to format edits and `pnpm format:check` to verify style. Vite minifies only the generated production files in `frontend/dist`.

## First use and data

New databases contain 20 illustrative products with **zero stock**. In Stock, edit prices to match the store and receive the actual opening stock. Give each brand/pack size a separate product code. Editing seed JSON after database creation does not update stored products; use Stock.

Records persist in `data/storepilot.sqlite3`. For a separate database, set an absolute path before starting the server:

```powershell
$env:STOREPILOT_DB = 'E:\Projects\AI\data\my-store.sqlite3'
```

Stop the server before copying the SQLite database for a backup. Keep backups somewhere safe; database files are excluded from Git. Preserve the database when updating the code.

Save a bill after confirming quantities and amount received. A balance due requires a customer. Stock is deducted only when saved. Retrying the same request does not create another sale. Names and prices on saved receipts stay unchanged after catalogue edits. Cash/UPI records payments manually; it does not process bank transfers.

Paste a WhatsApp list into Orders, then select the actual products while billing. Automatic WhatsApp ingestion and AI extraction are later features. These are simple store receipts; GST/tax invoicing, returns, multi-user access, barcode scanning, and payment-provider integration are outside this MVP.

The server is a **local MVP with no login**. Public use requires production authentication, HTTPS, deployment, and backups. Android home-screen installation is supported by the PWA assets when hosted over HTTPS. The localhost address only works on the computer running the server.

## Checks and API

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m storepilot --demo
cd frontend
pnpm build
```

API documentation: http://127.0.0.1:8000/docs. Existing `/products`, `/bills/preview`, and the CLI remain available. CLI bills are unsaved drafts and do not affect the database.

Money uses Decimal calculations and integer paise in storage; stock uses integer grams or pieces. Sales, stock updates, and repayments require retry IDs and run in transactions.

| File | Responsibility |
|---|---|
| storepilot/catalogue.py, billing.py | Product validation, unit conversion, bill calculation |
| storepilot/database.py, store.py | Storage and transactional business rules |
| storepilot/api.py, store_api.py | HTTP routes and web asset serving |
| frontend/src/ | Mobile store interface |
| frontend/public/ | PWA manifest, icons, app-shell service worker |
| tests/ | Domain, transaction, API, and persistence checks |
