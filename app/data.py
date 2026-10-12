"""
Where spending history comes from.

Two sources, one shape. Real sandbox CSVs if they are present in `data/`,
generated data otherwise. Everything downstream — baseline, evaluation, model,
service — works on the canonical columns in `app.synthetic.RECORD_COLUMNS` and
cannot tell the two apart except through the `is_synthetic` flag, which is
carried on every row and surfaced on every API response.

ON THE COLUMN MAPPING
---------------------
The sandbox `spending_records` schema has not been read yet, so the candidate
names below are a guess. The adapter deliberately does NOT silently fall back
to synthetic data when a real CSV is present but unmappable: it raises, listing
the columns it actually found. A service that quietly answered from generated
data while a real file sat unread in `data/` would produce numbers that look
real, are labelled real, and are fiction — which is the single worst failure
mode available to this project.

Staging data only, per project rules. Never production, never live M-Pesa.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

from app.synthetic import RECORD_COLUMNS, generate, monthly_totals

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SPENDING_RECORDS = DATA_DIR / "spending_records.csv"

# Candidate source column names for each canonical column, in priority order.
# Extend as the real schema becomes known rather than renaming columns by hand.
COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "user_id": ("user_id", "userId", "household_id", "householdId", "user"),
    "occurred_on": (
        "occurred_on",
        "occurredAt",
        "transaction_date",
        "date",
        "created_at",
        "createdAt",
        "spent_at",
    ),
    "category": ("category", "category_name", "budget_category", "categoryName"),
    "amount": ("amount", "value", "total", "amount_kes"),
}


class SchemaMismatch(RuntimeError):
    """A real CSV was found but could not be mapped onto the canonical shape."""


def _adapt(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    resolved: dict[str, str] = {}
    missing: list[str] = []

    lowered = {c.lower(): c for c in raw.columns}
    for canonical, candidates in COLUMN_CANDIDATES.items():
        for candidate in candidates:
            if candidate in raw.columns:
                resolved[canonical] = candidate
                break
            if candidate.lower() in lowered:
                resolved[canonical] = lowered[candidate.lower()]
                break
        else:
            missing.append(canonical)

    if missing:
        raise SchemaMismatch(
            f"{source}: could not map {missing}. "
            f"Columns present: {sorted(raw.columns)}. "
            f"Add the real names to COLUMN_CANDIDATES in app/data.py."
        )

    df = pd.DataFrame(
        {
            "user_id": raw[resolved["user_id"]].astype(str),
            "occurred_on": pd.to_datetime(raw[resolved["occurred_on"]], errors="coerce"),
            "category": raw[resolved["category"]].astype(str).str.strip(),
            "amount": pd.to_numeric(raw[resolved["amount"]], errors="coerce"),
        }
    )

    dropped = int(df["occurred_on"].isna().sum() + df["amount"].isna().sum())
    df = df.dropna(subset=["occurred_on", "amount"])
    if dropped:
        print(f"[data] {source}: dropped {dropped} rows with unparseable date or amount")

    # Refunds and reversals arrive as negatives in most ledgers. They are not
    # spend and must not be netted off silently — a -5,000 reversal sitting in
    # a month would hand the forecaster a total that never happened.
    negatives = int((df["amount"] < 0).sum())
    if negatives:
        print(f"[data] {source}: excluded {negatives} non-positive rows (refunds/reversals)")
    df = df[df["amount"] > 0]

    df["is_synthetic"] = False
    return df[RECORD_COLUMNS].reset_index(drop=True)


def load_records() -> tuple[pd.DataFrame, bool]:
    """Returns `(records, is_synthetic)`."""
    if SPENDING_RECORDS.exists():
        raw = pd.read_csv(SPENDING_RECORDS)
        return _adapt(raw, SPENDING_RECORDS.name), False

    records, _truth = generate()
    return records, True


@functools.lru_cache(maxsize=1)
def load_monthly() -> tuple[pd.DataFrame, bool]:
    """
    Monthly totals per (user, month, category), plus the synthetic flag.

    Cached for the process lifetime. The service is read-only over a static
    staging extract, so re-reading and re-aggregating on every request would
    buy nothing. When the sandbox becomes a live feed this becomes a scheduled
    refresh, not a per-request read.
    """
    records, is_synthetic = load_records()
    return monthly_totals(records), is_synthetic
