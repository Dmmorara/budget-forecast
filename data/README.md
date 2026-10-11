# data/

**Gitignored.** `.gitignore` excludes `data/*.csv`, so nothing placed here is committed —
only this file is.

## What goes here

The staging sandbox extract, downloaded from the platform API:

| File | Contents |
|---|---|
| `spending_records.csv` | the transactions the forecast is built from |
| `budget_categories.csv` | the category vocabulary |
| `households.csv` | household attributes |
| `dependants.csv` | dependants per household (consumed by U-CS 43) |

The moment `spending_records.csv` exists, `app/data.py` uses it instead of generated data
and every API response flips `isSynthetic` to `false`. Nothing else changes.

## Required columns

`app/data.py` maps the source columns onto four canonical ones: `user_id`, `occurred_on`,
`category`, `amount`. The candidate source names are a **guess** — the real schema has not
been read yet.

If the mapping fails, the loader raises `SchemaMismatch` listing the columns it actually
found, and the fix is to add the real names to `COLUMN_CANDIDATES` in `app/data.py`.
It deliberately does **not** fall back to synthetic data when a real file is present but
unmappable: a service quietly answering from generated data while a real file sat unread
here would emit numbers that look real, are labelled real, and are fiction.

## Rules

- **Staging only.** Never production, never live M-Pesa.
- Credentials live in `.env`, which is gitignored. See `.env.example`.
- Refunds and reversals arrive as negative amounts and are excluded, not netted off — a
  reversal left in a month hands the forecaster a total that never happened. The loader
  reports how many rows it dropped.
