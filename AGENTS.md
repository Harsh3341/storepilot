# StorePilot repository guidance

## Project

StorePilot helps a single general-store owner manage products, sales, inventory, orders, and credit balances. The current milestone is a React PWA interface, FastAPI, and SQLite. Public deployment requires HTTPS and production authentication; PostgreSQL and AI list extraction are later milestones.

## Commands

Run from the repository root with Python 3.12 or newer:

```powershell
python -m unittest discover -s tests -v
python -m storepilot --demo
python -m storepilot
python -m uvicorn storepilot.api:create_app --factory --host 127.0.0.1 --port 8000
cd frontend
pnpm build
```

Install Python dependencies from requirements-dev.txt and frontend dependencies from the committed pnpm lockfile. See README.md for Windows setup.

## Code conventions

- Keep modules small: catalogue data, billing calculations, and terminal interaction have separate responsibilities.
- Use Decimal constructed from text for prices and quantities. Never introduce binary float calculations for money.
- Loose goods use kilograms as the catalogue unit and allow input in grams. Packaged goods use whole pieces; each brand and pack size has its own code.
- Round each line to two decimal places with ROUND_HALF_UP, then sum rounded lines.
- Keep historical bill names and prices independent of later catalogue edits.
- Test observable financial behavior and invalid-input recovery before adding behavior.
- Sample prices are illustrative; new stores start with zero stock. Draft bills are unsaved; receipts describe saved sales.
- Persist money as integer paise and stock as integer grams or pieces. Checkout must atomically deduct aggregate stock, save receipt snapshots, record credit, and complete any linked order.
- Preserve idempotency for sale, stock, and repayment retries. Never cache financial API responses or silently queue writes offline.

## Git workflow

- Commit each completed feature separately, with its relevant tests.
- Use concise messages such as `feat: add product catalogue` or `fix: reject fractional packet quantities`.
- Do not add generated-by attribution, assistant signatures, or optional co-author trailers.
- Run the checks appropriate to a feature before committing. Do not commit a known failing feature or temporary execution output.
- Keep credentials, virtual environments, caches, and local configuration out of commits.
- Keep learning notes, plans, QA artifacts, and practice local, excluded through .git/info/exclude.
