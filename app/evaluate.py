"""
Time-based evaluation. Step 2 of the mandated order of work.

THE SPLIT IS BY TIME, NOT AT RANDOM
-----------------------------------
A random split over monthly rows would let a household's June sit in training
while its May and July sit in test. Since monthly spend is strongly
autocorrelated, the model could then reach a flattering score by interpolating
between two months it had already seen — and the production service never has
that luxury, because the future has not happened yet. Every number in this
module comes from a rolling origin: to forecast month M the forecaster is handed
history strictly before M, and nothing else.

This is a stricter test than Phase 1's grouped-payee holdout. That one answered
"does this generalise to a payee we have never seen", which is a cold-start
question. This one answers "does this generalise forward in time for a
household we know well", which is what the service is actually asked to do
every month.

WHAT IS MEASURED, AND WHY EACH ONE
----------------------------------
mae_total    Absolute error in KES on the monthly total. The headline. In KES
             because a household cares about shillings, not percentages.
mape_total   The same error as a share of what was actually spent, so that a
             2,000 KES miss on a 36,000 KES tenant and on a 12,000 KES student
             are not treated as equally bad.
mae_category Mean absolute error per category, over the union of categories
             predicted and observed. A forecaster can get the total right by
             accident while attributing rent to food, and U-CS 38 consumes the
             breakdown, not just the total.
coverage     Share of actual totals that landed inside the stated interval.
             This is the only check on whether "the confidence range is
             honest". An 80% interval that covers 40% of outcomes is a lie
             told in numbers; one that covers 99% is useless but not dishonest.
             Both failures need to be visible, so the nominal level is recorded
             alongside the achieved one.
declined     Months the forecaster refused with `insufficient_history`. Kept
             out of the error metrics and reported separately, because a
             service that answers nothing scores a perfect zero error and must
             not be allowed to look good for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from app.forecaster import Forecast, Forecaster

# Nominal coverage of the intervals the baselines emit (10th-90th percentile).
NOMINAL_COVERAGE = 0.80


@dataclass
class Result:
    name: str
    n_forecasts: int
    n_declined: int
    mae_total: float
    mape_total: float
    median_ape_total: float
    mae_category: float
    coverage: Optional[float]
    mean_confidence: Optional[float]
    rows: pd.DataFrame

    def line(self) -> str:
        cov = "     —" if self.coverage is None else f"{self.coverage * 100:5.1f}%"
        conf = "    —" if self.mean_confidence is None else f"{self.mean_confidence:5.3f}"
        return (
            f"{self.name:34s} "
            f"{self.mae_total:9.1f} "
            f"{self.mape_total * 100:7.2f}% "
            f"{self.median_ape_total * 100:7.2f}% "
            f"{self.mae_category:9.1f} "
            f"{cov} "
            f"{conf} "
            f"{self.n_forecasts:5d} "
            f"{self.n_declined:4d}"
        )


HEADER = (
    f"{'forecaster':34s} "
    f"{'MAE':>9s} "
    f"{'MAPE':>8s} "
    f"{'medAPE':>8s} "
    f"{'catMAE':>9s} "
    f"{'cover':>6s} "
    f"{'conf':>5s} "
    f"{'n':>5s} "
    f"{'decl':>4s}"
)


def _month_keys(monthly: pd.DataFrame) -> np.ndarray:
    return (monthly["year"] * 12 + monthly["month"]).to_numpy()


def holdout_months(monthly: pd.DataFrame, n: int = 3) -> list[int]:
    """
    The last `n` calendar months in the dataset, as sortable month keys.

    Held out globally rather than per household. If each household kept its own
    last three months, the test set would span different calendar periods for
    different households and a seasonal effect would be smeared across train
    and test at once. One shared wall-clock cutoff is the only version of this
    that corresponds to how the service is deployed: at a point in time, for
    everybody.
    """
    keys = sorted(set(_month_keys(monthly).tolist()))
    return keys[-n:]


def evaluate(
    forecaster: Forecaster,
    monthly: pd.DataFrame,
    n_holdout: int = 3,
    nominal_coverage: float = NOMINAL_COVERAGE,
) -> Result:
    """Roll the origin forward through the held-out months and score."""
    monthly = monthly.copy()
    monthly["mkey"] = _month_keys(monthly)
    test_keys = holdout_months(monthly, n_holdout)

    rows: list[dict] = []

    for mkey in test_keys:
        # Everything strictly before the target month. This is the only data
        # the forecaster is shown.
        history = monthly[monthly["mkey"] < mkey].drop(columns=["mkey"])
        target = monthly[monthly["mkey"] == mkey]
        year, month = divmod(mkey, 12)
        if month == 0:
            year, month = year - 1, 12

        for user_id, actual_rows in target.groupby("user_id"):
            actual_breakdown = (
                actual_rows.groupby("category")["amount"].sum().to_dict()
            )
            actual_total = float(sum(actual_breakdown.values()))

            fc: Forecast = forecaster.forecast(history, str(user_id), year, month)

            declined = fc.risk_flag == "insufficient_history"

            categories = set(actual_breakdown) | set(fc.breakdown)
            cat_errors = [
                abs(fc.breakdown.get(c, 0.0) - actual_breakdown.get(c, 0.0))
                for c in categories
            ]

            covered = None
            if fc.low is not None and fc.high is not None:
                covered = bool(fc.low <= actual_total <= fc.high)

            rows.append(
                {
                    "user_id": user_id,
                    "year": year,
                    "month": month,
                    "actual_total": round(actual_total, 2),
                    "predicted_total": round(fc.total, 2),
                    "abs_error": round(abs(fc.total - actual_total), 2),
                    "ape": (
                        abs(fc.total - actual_total) / actual_total
                        if actual_total > 0
                        else np.nan
                    ),
                    "cat_mae": float(np.mean(cat_errors)) if cat_errors else np.nan,
                    "confidence": fc.confidence,
                    "low": fc.low,
                    "high": fc.high,
                    "covered": covered,
                    "risk_flag": fc.risk_flag,
                    "declined": declined,
                    "n_history_months": int(
                        history[history["user_id"] == user_id]
                        .assign(k=lambda d: d["year"] * 12 + d["month"])["k"]
                        .nunique()
                    ),
                }
            )

    frame = pd.DataFrame(rows)
    scored = frame[~frame["declined"]]

    coverage = None
    if scored["covered"].notna().any():
        coverage = float(scored.loc[scored["covered"].notna(), "covered"].mean())

    mean_conf = (
        float(scored["confidence"].mean()) if len(scored) else None
    )

    return Result(
        name=forecaster.name,
        n_forecasts=int(len(scored)),
        n_declined=int(frame["declined"].sum()),
        mae_total=float(scored["abs_error"].mean()) if len(scored) else float("nan"),
        mape_total=float(scored["ape"].mean(skipna=True)) if len(scored) else float("nan"),
        median_ape_total=(
            float(scored["ape"].median(skipna=True)) if len(scored) else float("nan")
        ),
        mae_category=float(scored["cat_mae"].mean()) if len(scored) else float("nan"),
        coverage=coverage,
        mean_confidence=mean_conf,
        rows=frame,
    )


def noise_floor(truth: pd.DataFrame, n_holdout: int = 3) -> dict[str, float]:
    """
    The error no forecaster can remove, on the same held-out months.

    `truth` carries the latent monthly expectation each synthetic household was
    drawn from. A perfect forecaster would return exactly that expectation and
    still be wrong by whatever noise the process injected. Reporting a model's
    MAE without this number beside it invites the reader to believe the
    remaining error is a modelling failure, when part of it is arithmetic.

    Only meaningful for synthetic data. Real data has no published truth, which
    is itself worth stating in the report.
    """
    t = truth.copy()
    t["mkey"] = t["year"] * 12 + t["month"]
    keys = sorted(set(t["mkey"].tolist()))[-n_holdout:]
    t = t[t["mkey"].isin(keys)]

    per_month = t.groupby(["user_id", "mkey"])[["expected", "actual"]].sum()
    err = (per_month["actual"] - per_month["expected"]).abs()
    ape = err / per_month["actual"].replace(0, np.nan)

    return {
        "mae_total": float(err.mean()),
        "mape_total": float(ape.mean(skipna=True)),
        "median_ape_total": float(ape.median(skipna=True)),
    }


def compare(
    forecasters: list[Forecaster],
    monthly: pd.DataFrame,
    n_holdout: int = 3,
    truth: Optional[pd.DataFrame] = None,
) -> list[Result]:
    """Score several forecasters on identical held-out months and print a table."""
    results = [evaluate(f, monthly, n_holdout) for f in forecasters]

    print(HEADER)
    print("─" * len(HEADER))
    for r in results:
        print(r.line())

    if truth is not None:
        floor = noise_floor(truth, n_holdout)
        print("─" * len(HEADER))
        print(
            f"{'irreducible noise floor':34s} "
            f"{floor['mae_total']:9.1f} "
            f"{floor['mape_total'] * 100:7.2f}% "
            f"{floor['median_ape_total'] * 100:7.2f}% "
            f"{'—':>9s} {'—':>6s} {'—':>5s} {'—':>5s} {'—':>4s}"
        )
        print("\n(no forecaster can do better than the floor; it is process noise)")

    return results


def by_profile(result: Result) -> pd.DataFrame:
    """
    Break a result down by synthetic profile.

    A single headline MAE averaged over a population hides the thing that
    matters: a large fixed obligation makes percentage error look small, so a
    population with many salaried tenants flatters any forecaster. The per-
    profile split is where a model that only works on the easy case is caught.
    """
    rows = result.rows.copy()
    rows["profile"] = rows["user_id"].str.rsplit("-", n=1).str[0]
    scored = rows[~rows["declined"]]
    out = (
        scored.groupby("profile")
        .agg(
            n=("abs_error", "size"),
            mae=("abs_error", "mean"),
            mape=("ape", "mean"),
            cat_mae=("cat_mae", "mean"),
            coverage=("covered", "mean"),
            mean_actual=("actual_total", "mean"),
        )
        .round(4)
    )
    declined = rows[rows["declined"]].groupby("profile").size().rename("declined")
    return out.join(declined, how="left").fillna({"declined": 0})
