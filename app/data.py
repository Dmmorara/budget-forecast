"""
Where spending history comes from.

Two sources, one shape. Sandbox CSVs if they are present in `data/`, locally
generated data otherwise. Everything downstream — baseline, evaluation, model,
service — works on the canonical columns in `app.synthetic.RECORD_COLUMNS`.

BOTH SOURCES ARE SYNTHETIC, AND THE FLAG SAYS SO FOR BOTH
----------------------------------------------------------
The staging sandbox does not contain real household spending. The Webmasters
supervisor confirmed on 14 October 2026: "All synthetic, say so in the report."

An earlier version of this module set `is_synthetic = False` as soon as a CSV
appeared in `data/`, on the assumption that a real file meant real data. That
would have made the service start asserting its forecasts described real
households the moment the extract was loaded — while the underlying numbers
were still generated. The project rule is stated three separate ways in the
partner's README, and this is the one place in the codebase where breaking it
would be invisible: everything would look more credible, not less.

`PROVENANCE` records WHICH synthetic source is in use, because that does matter
for the report — a figure from the platform's sandbox is evidence about the
platform's data model, while one from `app/synthetic.py` is evidence only about
a generator written for this project. Neither is evidence about a real person.

If the platform ever supplies genuinely real data, `SANDBOX_IS_SYNTHETIC` is
the single line to change, and it should be changed only on written
confirmation.

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
BUDGET_CATEGORIES = DATA_DIR / "budget_categories.csv"

# Candidate source column names for each canonical column, in priority order.
# Extend as the real schema becomes known rather than renaming columns by hand.
COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    # user_profile_id comes first deliberately. households.csv carries BOTH
    # user_profile_id and user_id, and spending_records joins on the profile
    # id — so matching "user_id" first would silently key the two files on
    # different columns and produce households with no spending history.
    "user_id": (
        "user_profile_id", "userProfileId",
        "user_id", "userId", "household_id", "householdId", "user",
    ),
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
    "amount": ("amount_kes", "amount", "value", "total"),
}


# The staging sandbox is generated data, per the supervisor. Changing this to
# False is an assertion that the extract describes real households.
SANDBOX_IS_SYNTHETIC = True


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

    df["is_synthetic"] = SANDBOX_IS_SYNTHETIC
    return df[RECORD_COLUMNS].reset_index(drop=True)


def provenance() -> str:
    """Which synthetic source is in use. For the report, not for the contract."""
    return "platform-sandbox" if SPENDING_RECORDS.exists() else "local-generator"


def load_records() -> tuple[pd.DataFrame, bool]:
    """
    Returns `(records, is_synthetic)`.

    `is_synthetic` is True for both sources — see the module docstring. Use
    `provenance()` when the distinction between them matters.
    """
    if SPENDING_RECORDS.exists():
        raw = pd.read_csv(SPENDING_RECORDS)
        return _adapt(raw, SPENDING_RECORDS.name), SANDBOX_IS_SYNTHETIC

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


# ── household budgets ──
#
# `budget_categories.csv` carries `allocated_kes`: what the household budgeted
# for a category. In this extract it is CONSTANT per (household, category)
# across all 18 months — 100% of pairs have a single distinct value — so using
# it to forecast any month involves no look-ahead. It correlates 0.80 with
# actual spend.
#
# That constancy is the condition that makes this safe. If budgets ever become
# time-varying, only rows dated strictly before the target month may be used,
# and this loader must start filtering by month.


@functools.lru_cache(maxsize=1)
def load_budgets() -> pd.DataFrame:
    """
    `(user_id, category) -> allocated`, or an empty frame when unavailable.

    Returns empty rather than raising when the file is missing, because the
    service must still answer from history alone — the budget is an additional
    signal, not a dependency.
    """
    if not BUDGET_CATEGORIES.exists():
        return pd.DataFrame(columns=["user_id", "category", "allocated"])

    raw = pd.read_csv(BUDGET_CATEGORIES)
    lowered = {c.lower(): c for c in raw.columns}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in raw.columns:
                return n
            if n.lower() in lowered:
                return lowered[n.lower()]
        return None

    user = pick("user_profile_id", "userProfileId", "user_id")
    category = pick("category", "category_name")
    allocated = pick("allocated_kes", "allocated", "budget_kes")
    if not (user and category and allocated):
        print(f"[data] {BUDGET_CATEGORIES.name}: no budget columns found in {sorted(raw.columns)}")
        return pd.DataFrame(columns=["user_id", "category", "allocated"])

    per_pair = raw.groupby([user, category])[allocated].median().reset_index()
    per_pair.columns = ["user_id", "category", "allocated"]
    per_pair["user_id"] = per_pair["user_id"].astype(str)
    per_pair["category"] = per_pair["category"].astype(str).str.strip()
    return per_pair
