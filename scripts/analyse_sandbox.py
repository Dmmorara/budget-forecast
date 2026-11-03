"""
Reproduce the sandbox figures SANDBOX_RESULTS.md quotes outside its tables.

    python3 -m scripts.analyse_sandbox

Three measurements explain why no temporal model beats a constant on the
sandbox, and until this script existed they lived only in that document's
history:

    lag-1 autocorrelation of monthly spend per household-category   -0.07
    best constant fitted on the test months   MAE 7163.9   catMAE 1482.8
    corr(n_dependants, monthly spend)                                -0.0088
    corr(n_dependants, declared budget)                              -0.0117

Each is printed beside the documented value. A figure that does not reproduce
is reported as such and left for a person to explain; this script does not
decide which of the two is right.

NEEDS THE FULL EXTRACT
----------------------
The figures describe all 500 households, so the script refuses to run on the
committed 60-household slice in data/public/, which would give different
numbers that look just as authoritative. Fetch the extract first with
`python -m scripts.fetch_data` (needs .env; data/ is gitignored).

dependants.csv is read for its household id column only. The names in it are
never loaded.

The sandbox is synthetic (see app/data.py). No figure here describes a real
household.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from app.data import DATA_DIR, load_budgets, load_monthly, provenance
from app.evaluate import _month_keys, evaluate, holdout_months
from app.forecaster import Forecast

N_HOLDOUT = 3

# As quoted in SANDBOX_RESULTS.md.
DOCUMENTED = {
    "autocorrelation": -0.07,
    "oracle_mae": 7163.9,
    "oracle_mape": 8.85,
    "oracle_cat_mae": 1482.8,
    "dependants_vs_spend": -0.0088,
    "dependants_vs_budget": -0.0117,
}


class BestConstantOracle:
    """
    Each household-category's mean over the held-out months, forecast for all
    of them: the category's holdout total divided by the number of held-out
    months.

    The breakdown covers the household's full category set, every category in
    its history and its holdout. A category with no holdout spend is forecast
    as 0.0, not dropped. That matters for catMAE, which averages over the
    union of predicted and observed categories: dropping the zeros removes
    categories the oracle gets exactly right and gives 1627.8 instead.

    It reads the months it is scored on, so it is unreachable by any real
    forecaster. It is the floor for a constant-mean model: what is left above
    it is month-to-month noise that no constant can remove.
    """

    name = "oracle:best_constant"

    def __init__(self, monthly: pd.DataFrame, n_holdout: int):
        in_holdout = np.isin(_month_keys(monthly), holdout_months(monthly, n_holdout))
        holdout_total = (
            monthly[in_holdout].groupby(["user_id", "category"])["amount"].sum()
        )
        self._breakdown: dict[str, dict[str, float]] = {}
        for user, categories in monthly.groupby("user_id")["category"]:
            self._breakdown[str(user)] = {
                c: float(holdout_total.get((user, c), 0.0)) / n_holdout
                for c in sorted(categories.unique())
            }

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        breakdown = self._breakdown.get(user_id, {})
        return Forecast(
            total=sum(breakdown.values()), breakdown=breakdown, method=self.name
        )


def lag1_autocorrelation(monthly: pd.DataFrame) -> float:
    """
    Mean over household-category pairs of the correlation between each
    month's spend and the previous calendar month's. A month with no spend in
    the category has no value, so only consecutive months that both have one
    are paired.
    """
    series = monthly.assign(mkey=_month_keys(monthly)).pivot_table(
        index=["user_id", "category"], columns="mkey", values="amount", aggfunc="sum"
    )
    every_month = range(series.columns.min(), series.columns.max() + 1)
    series = series.reindex(columns=every_month)
    # A pair with fewer than two consecutive months, or a constant amount, has
    # no defined correlation. It comes back NaN and is skipped; numpy warns
    # about each one on the way.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        per_pair = series.apply(lambda row: row.autocorr(lag=1), axis=1)
    return float(per_pair.mean(skipna=True))


def dependants_correlations(monthly: pd.DataFrame) -> tuple[float, float, int, int]:
    """
    Correlation of a household's dependant count with its mean monthly spend
    and with its declared monthly budget. Households with no dependants count
    as zero rather than being dropped.
    """
    households = pd.Index(sorted(monthly["user_id"].unique()), name="user_id")
    dependants = pd.read_csv(DATA_DIR / "dependants.csv", usecols=["user_profile_id"])
    count = (
        dependants.groupby("user_profile_id").size().reindex(households).fillna(0)
    )

    spend = (
        monthly.groupby(["user_id", "year", "month"])["amount"]
        .sum()
        .groupby("user_id")
        .mean()
        .reindex(households)
    )
    budget = load_budgets().groupby("user_id")["allocated"].sum().reindex(households)

    return (
        float(count.corr(spend)),
        float(count.corr(budget)),
        int((count > 0).sum()),
        int(count.sum()),
    )


def _row(label: str, got: float, documented: float, fmt: str) -> None:
    shown = format(got, fmt)
    verdict = "reproduces" if shown == format(documented, fmt) else "DIFFERS"
    print(
        f"  {label:38s} {shown:>10s}   documented {format(documented, fmt):>10s}"
        f"   {verdict}"
    )


def main() -> None:
    if provenance() != "platform-sandbox":
        raise SystemExit(
            "The full sandbox extract is not in data/. These figures describe all "
            "500 households, and the committed slice in data/public/ would give "
            "different ones. Run `python -m scripts.fetch_data` first."
        )
    if not (DATA_DIR / "dependants.csv").exists():
        raise SystemExit("data/dependants.csv is missing. Run scripts.fetch_data.")

    monthly, _ = load_monthly()
    months = int(pd.Series(_month_keys(monthly)).nunique())
    print(
        f"SYNTHETIC — platform sandbox, {monthly['user_id'].nunique()} households, "
        f"{months} months, last {N_HOLDOUT} held out\n"
    )

    print("Temporal structure")
    _row(
        "lag-1 autocorrelation (mean of pairs)",
        lag1_autocorrelation(monthly),
        DOCUMENTED["autocorrelation"],
        ".2f",
    )

    print("\nBest constant fitted on the test months (unreachable)")
    oracle = evaluate(BestConstantOracle(monthly, N_HOLDOUT), monthly, N_HOLDOUT)
    _row("MAE", oracle.mae_total, DOCUMENTED["oracle_mae"], ".1f")
    _row("MAPE %", oracle.mape_total * 100, DOCUMENTED["oracle_mape"], ".2f")
    _row("catMAE", oracle.mae_category, DOCUMENTED["oracle_cat_mae"], ".1f")

    vs_spend, vs_budget, with_dependants, total = dependants_correlations(monthly)
    print(
        f"\nDependants ({total:,} across {with_dependants} households; "
        "the rest count as zero)"
    )
    _row("corr(n_dependants, monthly spend)", vs_spend, DOCUMENTED["dependants_vs_spend"], ".4f")
    _row("corr(n_dependants, declared budget)", vs_budget, DOCUMENTED["dependants_vs_budget"], ".4f")


if __name__ == "__main__":
    main()
