"""
Feature panel for the fitted ensemble, at (household, category, target month)
grain.

    python3 -m scripts.build_panel        # writes data/panel.csv (gitignored)

Used by scripts/fit_model.py, which imports `build` rather than reading the
file back.

THE FEATURES ARE DEFINED IN app/features.py
-------------------------------------------
This script assembles the training panel; it does not compute a single
feature itself. Every feature comes from `app.features.feature_rows`, the same
function ExtraTreesForecaster calls per request, so the model is served the
features it was fitted on. Do not add feature code here.

`build` hands `feature_rows` only the household's months strictly before each
target month: the slicing happens before the call. That is the same rolling
origin `app.evaluate.evaluate` uses, so a forecaster trained on this panel is
scored on exactly the information the shipped blend gets. A category spent on
for the first time in the target month has no row, the blend's blind spot
too; `evaluate` scores it as a prediction of zero for both.

The `blend` feature is the shipped forecaster's per-category value, and
`check_blend` asserts it matches `BudgetBlendForecaster` itself.

Reads data/spending_records.csv and data/budget_categories.csv through
app.data. Never reads households.csv or dependants.csv. Synthetic data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.data import DATA_DIR, PUBLIC_DIR, load_budgets, load_monthly
from app.evaluate import _month_keys
from app.features import (
    BLEND_WEIGHT,
    CATEGORIES,
    FEATURES,
    budget_lookup,
    feature_rows,
    household_tables,
    one_hot,
    ym,
)
from app.forecaster import BudgetBlendForecaster
from scripts.minimise_extract import slice_alias


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
    lookup = budget_lookup(budgets)
    frames = []

    for user_id, rows in monthly.groupby("user_id"):
        amounts, seen = household_tables(rows)
        months = amounts.index.to_list()
        for i, mkey in enumerate(months):
            if i < min_history:
                continue
            feats = feature_rows(
                amounts.iloc[:i], seen.iloc[:i], lookup.get(str(user_id), {}), mkey
            )
            actual = amounts.loc[mkey]
            feats["target"] = feats["category"].map(actual).fillna(0.0).values
            feats["user_id"] = str(user_id)
            feats["mkey"] = int(mkey)
            feats["year"], feats["month"] = ym(mkey)
            frames.append(feats)

    panel = pd.concat(frames, ignore_index=True)
    first = int(monthly["mkey"].min())
    panel["month_index"] = panel["mkey"] - first + 1  # 1 = first month of data
    return one_hot(panel)


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
        year, month = ym(mkey)
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
