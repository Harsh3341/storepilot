# StorePilot

A general-store application for one shopkeeper. The intended Android app will manage billing, stock, orders, and customer dues.

Milestone 1 is a Python command-line catalogue and **draft-bill calculator**. It includes 20 illustrative products, loose goods in grams/kilograms, packaged goods in whole pieces, search, and precise decimal calculations. Drafts are not saved sales or tax invoices; stock and payments are not recorded yet.

## Run on Windows

Open PowerShell at the repository root. If `.venv` already exists, run:

```powershell
.\.venv\Scripts\python.exe -m storepilot --demo
.\.venv\Scripts\python.exe -m storepilot
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For a fresh checkout, first install Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/), then create the environment:

```powershell
python -m venv .venv
```

The current milestone has no third-party packages to install. Using the environment executable directly avoids PowerShell activation-policy changes. On macOS/Linux, use `.venv/bin/python` instead.

## Try a bill

Enter these commands in the interactive app:

```text
search sugar
SUGAR-LOOSE 250 g
SUGAR-PACK-1KG 2
OIL-1L 2
done
```

The illustrative total is **INR 422.00**. `list` shows the catalogue; `search NAME` finds matching codes or names; `quit` discards a draft. Loose quantities default to kg; packaged quantities default to piece. Specify `g` explicitly when entering grams.

The supplied prices are examples. Replace them with actual store prices in [data/catalogue.json](data/catalogue.json). Prices are JSON strings, such as `"48.00"`, to preserve decimal values. Reload the app after saving changes. Each product needs a unique uppercase code, name, unit (`kg` or `piece`), and positive price. Different brands and pack sizes need distinct codes.

You can also load a separate file:

```powershell
.\.venv\Scripts\python.exe -m storepilot --catalogue data\catalogue.json
```

Prices have at most two decimal places. Loose quantities must represent whole grams; packaged quantities must be whole numbers. Input prices and quantities are positive and at most 1,000,000. Round each line to the nearest paisa with halves rounded up, then sum those lines. Names and prices are copied into a draft so later catalogue edits do not alter it.

## Find the code

| File | Responsibility |
|---|---|
| `storepilot/catalogue.py` | Product validation, JSON loading, search |
| `storepilot/billing.py` | Unit conversion, bill snapshots, totals |
| `storepilot/__main__.py` | Terminal commands and display |
| `data/catalogue.json` | Editable sample products |
| `tests/` | Financial behavior and command-line acceptance cases |
| `AGENTS.md` | Repository conventions and development commands |

The intended next milestone adds a FastAPI interface and saved products/bills. Stock movements, payment ledgers, digital orders, AI extraction, and the mobile interface follow in separately designed milestones.
