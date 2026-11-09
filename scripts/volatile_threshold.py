"""
Choose the volatile flag's threshold on months 13-15, and check it once on
16-18.

    python3 -m scripts.volatile_threshold choose     # months 13-15 only
    python3 -m scripts.volatile_threshold verify     # months 16-18

Needs the full sandbox extract in data/. Synthetic.

WHAT THE FLAG NOW CLAIMS
------------------------
FR-07, amended: `volatile` marks a household whose monthly spending has
varied by more than VOLATILE_CV (the coefficient of variation of its monthly
totals before the target month). It is a statement about the household. It
makes no claim that the forecast for that household is less accurate.

HOW THE THRESHOLD IS SET
------------------------
By a firing rate, not a round number. The rate is the one the blend's old
span-based flag had on the same household-months, months 13-15 for the 440
training households, so the change alters what the flag means and not how
often consumers see it. The threshold is whatever CV gives that rate.

`choose` also measures why the old rule had to go: whether a household's CV
tracks the blend's error, and whether it tracks the model's. `verify`
reports the firing rate on 16-18 for both household groups, and error where
the flag fires against where it does not, as a check on the new claim, not
as a requirement.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

from app.data import load_budgets, load_monthly, provenance
from app.evaluate import evaluate
from app.features import ym
from app.forecaster import (
    VOLATILE_CV,
    BudgetBlendForecaster,
    ExtraTreesForecaster,
    household_cv,
)
from scripts.build_panel import deployed_households
from scripts.calibrate_interval import calibration_set
from scripts.fit_model import restrict, through

CHOOSE_MONTHS = 15  # data through target month 15; evaluate holds out 13-15


def _cv_column(rows: pd.DataFrame, monthly: pd.DataFrame) -> np.ndarray:
    return np.array([
        household_cv(monthly, u, y, m)[0]
        for u, y, m in zip(rows["user_id"], rows["year"], rows["month"])
    ])


def choose() -> None:
    monthly, _ = load_monthly()
    budgets = load_budgets()
    served = set(deployed_households())
    trained = set(monthly["user_id"]) - served
    upto15 = through(monthly, CHOOSE_MONTHS)

    blend = restrict(
        evaluate(BudgetBlendForecaster(budgets), upto15, n_holdout=3), trained, "blend"
    ).rows
    blend = blend[~blend["declined"]].copy()
    old_fires = int((blend["risk_flag"] == "volatile").sum())
    rate = old_fires / len(blend)
    blend["cv"] = _cv_column(blend, upto15)

    cv = np.sort(blend["cv"].to_numpy())[::-1]
    # Halfway between the last CV that fires and the first that does not.
    threshold = float((cv[old_fires - 1] + cv[old_fires]) / 2)

    model = calibration_set()  # the 4-12 calibration model's 13-15 totals
    model[["year", "month"]] = [ym(k) for k in model["mkey"]]
    model["cv"] = _cv_column(model, upto15)

    print(
        "Months 13-15, the 440 training households. SYNTHETIC.\n"
        f"household-months scored: {len(blend)}\n"
        f"old span-based flag (blend) fires on {old_fires} = {rate:.1%}: the target rate\n"
        f"CV of prior monthly totals: p50 {np.median(cv):.3f}  p90 "
        f"{np.percentile(cv, 90):.3f}  p95 {np.percentile(cv, 95):.3f}  max {cv.max():.3f}\n"
        f"threshold for that rate: CV > {threshold:.4f} "
        f"(fires on {int((blend['cv'] > threshold).sum())})\n"
    )
    print("Why the old rule measured the blend, not the household:")
    rel_blend = blend["abs_error"] / blend["predicted_total"]
    rel_model = model["residual"].abs() / model["pred"]
    print(f"  Spearman(CV, blend |error| / point) = "
          f"{blend['cv'].corr(rel_blend, method='spearman'):+.3f}")
    print(f"  Spearman(CV, model |error| / point) = "
          f"{model['cv'].corr(rel_model, method='spearman'):+.3f}")
    fired = blend["risk_flag"] == "volatile"
    print(f"  blend MAE where the old flag fired {blend.loc[fired, 'abs_error'].mean():,.1f} "
          f"vs not {blend.loc[~fired, 'abs_error'].mean():,.1f}; MAPE "
          f"{blend.loc[fired, 'ape'].mean() * 100:.2f}% vs "
          f"{blend.loc[~fired, 'ape'].mean() * 100:.2f}%")
    print(f"\nVOLATILE_CV in app/forecaster.py is currently {VOLATILE_CV}")


def verify() -> None:
    monthly, _ = load_monthly()
    budgets = load_budgets()
    served = set(deployed_households())
    trained = set(monthly["user_id"]) - served
    results = {
        "blend": evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3),
        "extratrees-v2": evaluate(ExtraTreesForecaster(budgets=budgets), monthly, n_holdout=3),
    }
    print(f"Months 16-18, flag: household CV > {VOLATILE_CV}. SYNTHETIC.\n")
    for group, users in (("440 trained", trained), ("60 deployed", served)):
        print(f"── {group} ──")
        for name, result in results.items():
            rows = restrict(result, users, name).rows
            rows = rows[~rows["declined"]]
            fired = rows["risk_flag"] == "volatile"
            line = (f"  {name:14s} fires {int(fired.sum()):4d}/{len(rows)} = "
                    f"{fired.mean():5.1%}")
            if fired.any() and (~fired).any():
                e_f, e_c = rows.loc[fired, "abs_error"], rows.loc[~fired, "abs_error"]
                a_f, a_c = rows.loc[fired, "ape"], rows.loc[~fired, "ape"]
                line += (f"   MAE {e_f.mean():9,.1f} vs {e_c.mean():9,.1f} "
                         f"(t {stats.ttest_ind(e_f, e_c, equal_var=False).statistic:+.2f})"
                         f"   MAPE {a_f.mean() * 100:5.2f}% vs {a_c.mean() * 100:5.2f}% "
                         f"(t {stats.ttest_ind(a_f, a_c, equal_var=False).statistic:+.2f})")
            print(line)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=("choose", "verify"))
    args = parser.parse_args()
    if provenance() != "platform-sandbox":
        raise SystemExit("Needs the full sandbox extract in data/.")
    choose() if args.cmd == "choose" else verify()


if __name__ == "__main__":
    main()
