# StorePilot repository guidance

## Project

StorePilot will help a single general-store owner manage products, loose and packaged sales, inventory, customer orders, and credit balances on an Android phone. The current milestone is a Python command-line product catalogue and draft-bill calculator. The intended later architecture is an online PWA, FastAPI, and PostgreSQL.

## Commands

Run from the repository root with Python 3.12 or newer:

```powershell
python -m unittest discover -s tests -v
python -m storepilot --demo
python -m storepilot
```

There are no third-party dependencies in the first milestone. See README.md for Windows setup.

## Code conventions

- Keep modules small: catalogue data, billing calculations, and terminal interaction have separate responsibilities.
- Use Decimal constructed from text for prices and quantities. Never introduce binary float calculations for money.
- Loose goods use kilograms as the catalogue unit and allow input in grams. Packaged goods use whole pieces; each brand and pack size has its own code.
- Round each line to two decimal places with ROUND_HALF_UP, then sum rounded lines.
- Keep historical bill names and prices independent of later catalogue edits.
- Test observable financial behavior and invalid-input recovery before adding behavior.
- Sample prices are illustrative. Draft bills must say that no sale, stock, or payment has been saved.
- Add stock, credit, external integrations, and the mobile interface only in their approved milestones.

## Learning workflow

The learner has three years of C#/.NET experience and is new to Python. Explain unfamiliar Python concepts with useful C# comparisons. Prefer small runnable changes and concrete exercises. Keep the learner's independent practice separate from the working reference application.

## Git workflow

- Commit each completed feature separately, with its relevant tests.
- Use concise messages such as `feat: add product catalogue` or `fix: reject fractional packet quantities`.
- Do not add generated-by attribution, assistant signatures, or optional co-author trailers.
- Run the checks appropriate to a feature before committing. Do not commit a known failing feature or temporary execution output.
- Keep credentials, virtual environments, caches, and local configuration out of commits.
