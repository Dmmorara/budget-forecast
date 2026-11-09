"""
Feature panel for the fitted ensemble, at (household, category, target month)
grain.

    python3 -m scripts.build_panel        # writes data/panel.csv (gitignored)

Used by scripts/fit_model.py, which imports `build` rather than reading the
file back.

NO FEATURE SEES ITS TARGET MONTH
--------------------------------
Every feature for target month M is computed by `_features`, and `_features`
is handed only the household's months strictly before M: the slicing happens
before the call, not inside it. That is the same rolling origin
`app.evaluate.evaluate` uses, so a forecaster trained on this panel is scored
on exactly the information the shipped blend gets.

The declared budget is the one input not sliced by month. It is constant per
household-category across the whole extract (see `app.data.load_budgets`), so
it reveals nothing about any particular month.

WHICH CATEGORIES GET A ROW
--------------------------
The categories `BudgetBlendForecaster` would forecast: any category with a
record in a prior month, plus any category the household declared a budget
for. A category spent on for the first time in the target month has no row,
which is the same blind spot the blend has; `evaluate` scores it as a
prediction of zero for both.

The `blend` feature is the shipped forecaster's per-category value, and
`check_blend` asserts it matches `BudgetBlendForecaster` itself.

Reads data/spending_records.csv and data/budget_categories.csv through
app.data. Never reads households.csv or dependants.csv. Synthetic data.
"""

from __future__ import annotations

import calendar
from pathlib import Path

import numpy as np
import pandas as pd

from app.data import DATA_DIR, PUBLIC_DIR, load_budgets, load_monthly
from app.evaluate import _month_keys
from app.forecaster import BudgetBlendForecaster
from scripts.minimise_extract import slice_alias

BLEND_WEIGHT = 0.8  # the shipped blend's share for history

# Fixed across runs so the one-hot columns, and so the model's feature list,
# do not depend on which categories happen to appear in a given extract.
CATEGORIES = [
    "Airtime and Data", "Cash Advance", "Crypto Purchase", "Electronics Upgrade",
    "Entertainment", "Foreign Transfer", "Gambling", "Groceries",
    "Household Help", "Jewellery", "Luxury Goods", "Medical", "Rent", "Savings",
    "School Fees", "Transport", "Utilities",
]

NUMERIC_FEATURES = [
    "mean_all",            # trailing mean over all prior months
    "mean_3",              # ... over the last 3 prior months
    "mean_6",              # ... over the last 6 prior months
    "median_all",          # trailing median over all prior months
    "presence_rate",       # share of prior months with any record
    "budget",              # declared allocation, 0 when none
    "has_budget",          # 1 when a budget row exists
    "blend",               # the shipped forecaster's value
    "n_history",           # prior months
    "cv",                  # std / mean of prior monthly amounts, 0 if undefined
    "last_amount",         # the previous month's amount
    "target_month",        # calendar month, 1-12
    "days_in_month",
    "household_mean_total",  # household's trailing mean monthly total
]
FEATURES = NUMERIC_FEATURES + [f"cat={c}" for c in CATEGORIES]

KEYS = ["user_id", "category", "mkey", "year", "month"]


def _ym(mkey: int) -> tuple[int, int]:
    year, month = divmod(int(mkey), 12)
    return (year - 1, 12) if month == 0 else (year, month)


def _features(
    prior: pd.DataFrame,
    prior_seen: pd.DataFrame,
    budget: dict[str, float],
    mkey: int,
) -> pd.DataFrame:
    """
    One row per candidate category for target month `mkey`.

    `prior` is the household's amounts for months strictly before `mkey`
    (rows = months, columns = categories, gaps 0). `prior_seen` is the same
    shape and is True where a record exists. Nothing else about the household
    is visible here.
    """
    seen = prior_seen.any(axis=0)
    candidates = sorted(set(seen[seen].index) | set(budget))
    if not candidates:
        return pd.DataFrame(columns=["category", *NUMERIC_FEATURES])

    table = prior.reindex(columns=candidates, fill_value=0.0)
    present = prior_seen.reindex(columns=candidates, fill_value=False)
    n = len(table)

    mean_all = table.mean()
    std = table.std(ddof=1) if n > 1 else pd.Series(0.0, index=candidates)
    alloc = pd.Series({c: budget.get(c, np.nan) for c in candidates})
    has_budget = alloc.notna()
    year, month = _ym(mkey)

    return pd.DataFrame(
        {
            "category": candidates,
            "mean_all": mean_all.values,
            "mean_3": table.tail(3).mean().values,
            "mean_6": table.tail(6).mean().values,
            "median_all": table.median().values,
            "presence_rate": present.mean().values,
            "budget": alloc.fillna(0.0).values,
            "has_budget": has_budget.astype(float).values,
            "blend": np.where(
                has_budget,
                BLEND_WEIGHT * mean_all + (1 - BLEND_WEIGHT) * alloc.fillna(0.0),
                mean_all,
            ),
            "n_history": float(n),
            "cv": np.where(mean_all > 0, std / mean_all.where(mean_all > 0, 1.0), 0.0),
            "last_amount": table.iloc[-1].values,
            "target_month": float(month),
            "days_in_month": float(calendar.monthrange(year, month)[1]),
            "household_mean_total": float(table.sum(axis=1).mean())
            if n
            else 0.0,
        }
    )


def _one_hot(frame: pd.DataFrame) -> pd.DataFrame:
    for c in CATEGORIES:
        frame[f"cat={c}"] = (frame["category"] == c).astype(float)
    return frame


def _budget_lookup(budgets: pd.DataFrame) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in budgets.itertuples():
        out.setdefault(str(r.user_id), {})[str(r.category)] = float(r.allocated)
    return out


def _household_tables(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    amounts = rows.pivot_table(
        index="mkey", columns="category", values="amount", aggfunc="sum"
    ).sort_index()
    seen = amounts.notna()
    return amounts.fillna(0.0), seen


def build(
    monthly: pd.DataFrame,
    budgets: pd.DataFrame,
    min_history: int = 3,
) -> pd.DataFrame:
    """
    The panel for every household-month with at least `min_history` prior
    months, with `target` (the actual amount, 0 when nothing was spent).
    """
    monthly = monthly.assign(mkey=_month_keys(monthly))
    lookup = _budget_lookup(budgets)
    frames = []

    for user_id, rows in monthly.groupby("user_id"):
        amounts, seen = _household_tables(rows)
        months = amounts.index.to_list()
        for i, mkey in enumerate(months):
            if i < min_history:
                continue
            feats = _features(
                amounts.iloc[:i], seen.iloc[:i], lookup.get(str(user_id), {}), mkey
            )
            actual = amounts.loc[mkey]
            feats["target"] = feats["category"].map(actual).fillna(0.0).values
            feats["user_id"] = str(user_id)
            feats["mkey"] = int(mkey)
            feats["year"], feats["month"] = _ym(mkey)
            frames.append(feats)

    panel = pd.concat(frames, ignore_index=True)
    first = int(monthly["mkey"].min())
    panel["month_index"] = panel["mkey"] - first + 1  # 1 = first month of data
    return _one_hot(panel)


def features_for(
    history: pd.DataFrame, budgets: pd.DataFrame, user_id: str, year: int, month: int
) -> pd.DataFrame:
    """Serving-time features: one household, months strictly before the target."""
    mkey = year * 12 + month
    rows = history[history["user_id"] == user_id]
    rows = rows.assign(mkey=_month_keys(rows))
    rows = rows[rows["mkey"] < mkey]
    if rows.empty:
        return _one_hot(pd.DataFrame(columns=["category", *NUMERIC_FEATURES]))
    amounts, seen = _household_tables(rows)
    return _one_hot(
        _features(amounts, seen, _budget_lookup(budgets).get(user_id, {}), mkey)
    )


def deployed_households(
    data_dir: Path = DATA_DIR, public_dir: Path = PUBLIC_DIR
) -> dict[str, str]:
    """
    `{platform id: local id}` for the households the deployment serves, from
    scripts.minimise_extract's own selection, then checked record for record
    against the committed slice so that a change to either side cannot
    silently pick different households.
    """
    cols = ["user_id", "transaction_date", "category", "amount_kes"]
    raw = pd.read_csv(
        data_dir / "spending_records.csv",
        usecols=["user_profile_id", "transaction_date", "category", "amount_kes"],
    )
    public = pd.read_csv(public_dir / "spending_records.csv")[cols]
    # The slice's size is read from the slice, not assumed: a slice cut with
    # --households 40 must map back to 40.
    alias = slice_alias(
        raw["user_profile_id"].astype(str).unique(), n=public["user_id"].nunique()
    )
    mine = (
        raw[raw["user_profile_id"].astype(str).isin(alias)]
        .assign(user_id=lambda d: d["user_profile_id"].astype(str).map(alias))[cols]
        .sort_values(cols).reset_index(drop=True)
    )
    public = public.sort_values(cols).reset_index(drop=True)
    if not mine.equals(public):
        raise SystemExit("slice_alias does not reproduce data/public/; refusing to fit.")
    return alias


def training_panel(
    panel: pd.DataFrame, deployed, first: int, last: int
) -> pd.DataFrame:
    """
    Panel rows for target months `first`-`last`, with every deployed
    household removed. This is the only way the shipped model's training
    rows are chosen; tests/test_disjoint.py holds it to that.
    """
    served = {str(h) for h in deployed}
    rows = panel[panel["month_index"].between(first, last)]
    rows = rows[~rows["user_id"].astype(str).isin(served)]
    assert not set(rows["user_id"].astype(str)) & served
    return rows


def check_blend(
    panel: pd.DataFrame,
    monthly: pd.DataFrame,
    budgets: pd.DataFrame,
    sample: int = 40,
    seed: int = 37,
) -> int:
    """
    Assert the `blend` feature reproduces BudgetBlendForecaster's breakdown on
    a sample of household-months. Returns the number checked.
    """
    blend = BudgetBlendForecaster(budgets, weight=BLEND_WEIGHT)
    keys = panel[["user_id", "mkey"]].drop_duplicates()
    picked = keys.sample(n=min(sample, len(keys)), random_state=seed)
    monthly = monthly.assign(mkey=_month_keys(monthly))
    for user_id, mkey in picked.itertuples(index=False):
        history = monthly[monthly["mkey"] < mkey].drop(columns="mkey")
        year, month = _ym(mkey)
        expected = blend.forecast(history, user_id, year, month).breakdown
        rows = panel[(panel["user_id"] == user_id) & (panel["mkey"] == mkey)]
        got = {
            c: round(v, 2) for c, v in zip(rows["category"], rows["blend"]) if v > 0.005
        }
        assert set(got) == set(expected), (user_id, mkey, set(got) ^ set(expected))
        for c, v in expected.items():
            assert abs(got[c] - v) <= 0.01, (user_id, mkey, c, got[c], v)
    return len(picked)


def main() -> None:
    monthly, _ = load_monthly()
    budgets = load_budgets()
    unknown = set(monthly["category"]) - set(CATEGORIES)
    if unknown:
        raise SystemExit(f"categories not in CATEGORIES: {sorted(unknown)}")

    panel = build(monthly, budgets)
    checked = check_blend(panel, monthly, budgets)
    out = DATA_DIR / "panel.csv"
    panel.to_csv(out, index=False)
    print(
        f"SYNTHETIC — {panel['user_id'].nunique()} households, "
        f"{len(panel):,} rows, target months "
        f"{panel['month_index'].min()}-{panel['month_index'].max()}, "
        f"{len(FEATURES)} features\n"
        f"blend feature matches BudgetBlendForecaster on {checked} household-months\n"
        f"wrote {out.relative_to(DATA_DIR.parent)}"
    )


if __name__ == "__main__":
    main()
