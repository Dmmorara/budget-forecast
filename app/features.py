"""
Features for the fitted model, at (household, category, target month) grain.

THE ONE DEFINITION
------------------
scripts/build_panel.py builds the training panel from these functions, and
ExtraTreesForecaster builds each request's features from them. There is no
second copy. A model fed features computed differently from the ones it was
fitted on still returns a number, a wrong one, and nothing fails. One
definition is what prevents that, and FEATURES is the order the artefact's
manifest is checked against at load.

NO FEATURE SEES ITS TARGET MONTH
--------------------------------
Every feature for target month M is computed by `feature_rows`, which is
handed only the household's months strictly before M: callers slice before the
call. `household_features` does that slicing itself, so even history that
includes month M, or later, cannot reach a feature.

The declared budget is the one input not sliced by month. It is constant per
household-category across the whole extract (see `app.data.load_budgets`), so
it reveals nothing about any particular month.

WHICH CATEGORIES GET A ROW
--------------------------
The categories `BudgetBlendForecaster` would forecast: any category with a
record in a prior month, plus any category the household declared a budget
for. A category spent on for the first time in the target month has no row,
the same blind spot the blend has.
"""

from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

BLEND_WEIGHT = 0.8  # the shipped blend's share for history

# Fixed, so the one-hot columns, and so the model's feature list, do not depend
# on which categories happen to appear in a given extract.
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
    "blend",               # the shipped blend's value
    "n_history",           # prior months
    "cv",                  # std / mean of prior monthly amounts, 0 if undefined
    "last_amount",         # the previous month's amount
    "target_month",        # calendar month, 1-12
    "days_in_month",
    "household_mean_total",  # household's trailing mean monthly total
]
FEATURES = NUMERIC_FEATURES + [f"cat={c}" for c in CATEGORIES]


def month_keys(monthly: pd.DataFrame) -> np.ndarray:
    """Sortable month keys, the same arithmetic as app.evaluate."""
    return (monthly["year"] * 12 + monthly["month"]).to_numpy()


def ym(mkey: int) -> tuple[int, int]:
    year, month = divmod(int(mkey), 12)
    return (year - 1, 12) if month == 0 else (year, month)


def feature_rows(
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
    year, month = ym(mkey)

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


def one_hot(frame: pd.DataFrame) -> pd.DataFrame:
    for c in CATEGORIES:
        frame[f"cat={c}"] = (frame["category"] == c).astype(float)
    return frame


def budget_lookup(budgets: pd.DataFrame) -> dict[str, dict[str, float]]:
    """`{user_id: {category: allocated}}` from load_budgets()'s frame."""
    out: dict[str, dict[str, float]] = {}
    for r in budgets.itertuples():
        out.setdefault(str(r.user_id), {})[str(r.category)] = float(r.allocated)
    return out


def household_tables(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One household's amounts and record-present flags, months by categories."""
    amounts = rows.pivot_table(
        index="mkey", columns="category", values="amount", aggfunc="sum"
    ).sort_index()
    seen = amounts.notna()
    return amounts.fillna(0.0), seen


def household_features(
    history: pd.DataFrame,
    budget: dict[str, float],
    user_id: str,
    year: int,
    month: int,
) -> pd.DataFrame:
    """
    Serving-time features for one household and target month, from months
    strictly before the target. `budget` is that household's
    `{category: allocated}`.
    """
    mkey = year * 12 + month
    rows = history[history["user_id"] == user_id]
    rows = rows.assign(mkey=month_keys(rows))
    rows = rows[rows["mkey"] < mkey]
    if rows.empty:
        return one_hot(pd.DataFrame(columns=["category", *NUMERIC_FEATURES]))
    amounts, seen = household_tables(rows)
    return one_hot(feature_rows(amounts, seen, budget, mkey))


def features_for(
    history: pd.DataFrame, budgets: pd.DataFrame, user_id: str, year: int, month: int
) -> pd.DataFrame:
    """`household_features` with the budget taken from load_budgets()'s frame."""
    return household_features(
        history, budget_lookup(budgets).get(user_id, {}), user_id, year, month
    )
