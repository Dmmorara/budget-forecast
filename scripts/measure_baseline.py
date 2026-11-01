"""
Reproduce every number in BASELINE.md.

    python3 -m scripts.measure_baseline

Run this before claiming a model beats the baseline, and run it again after,
on the same seed and the same held-out months. A model compared against a
remembered number is not compared against anything.
"""

from __future__ import annotations

import pandas as pd

from app.evaluate import by_profile, compare, evaluate, noise_floor
from app.forecaster import LastMonthForecaster, TrailingMedianForecaster
from app.synthetic import REFERENCE_LAST_MONTH, generate, monthly_totals

N_HOLDOUT = 3
SEED = 37


def per_profile_floor(truth: pd.DataFrame, n_holdout: int) -> pd.DataFrame:
    t = truth.copy()
    t["mkey"] = t["year"] * 12 + t["month"]
    keys = sorted(set(t["mkey"].tolist()))[-n_holdout:]
    t = t[t["mkey"].isin(keys)]
    per_month = t.groupby(["user_id", "mkey"])[["expected", "actual"]].sum().reset_index()
    per_month["profile"] = per_month["user_id"].str.rsplit("-", n=1).str[0]
    per_month["err"] = (per_month["actual"] - per_month["expected"]).abs()
    per_month["ape"] = per_month["err"] / per_month["actual"]
    return per_month.groupby("profile").agg(
        floor_mae=("err", "mean"), floor_mape=("ape", "mean")
    )


def main() -> None:
    pd.set_option("display.width", 220)

    records, truth = generate(seed=SEED, last_month=REFERENCE_LAST_MONTH)
    monthly = monthly_totals(records)

    months = (monthly["year"] * 12 + monthly["month"]).nunique()
    print(
        f"SYNTHETIC DATA — seed {SEED} — "
        f"{len(records):,} transactions, {records['user_id'].nunique()} households, "
        f"{months} months, last {N_HOLDOUT} months held out\n"
    )

    forecasters = [
        LastMonthForecaster(),
        TrailingMedianForecaster(3),
        TrailingMedianForecaster(6),
        TrailingMedianForecaster(0),
    ]
    results = compare(forecasters, monthly, N_HOLDOUT, truth=truth)

    chosen = evaluate(TrailingMedianForecaster(6), monthly, N_HOLDOUT)
    print(f"\n\n=== {chosen.name} by profile ===")
    profile_table = by_profile(chosen).join(per_profile_floor(truth, N_HOLDOUT))
    profile_table["removable_mae"] = profile_table["mae"] - profile_table["floor_mae"]
    profile_table["removable_pct"] = (
        profile_table["removable_mae"] / profile_table["mae"] * 100
    )
    print(profile_table.round(3).to_string())

    rows = chosen.rows[~chosen.rows["declined"]]
    flagged = rows[rows["risk_flag"] == "volatile"]
    clean = rows[rows["risk_flag"].isna()]
    print(
        f"\nvolatile flag:  fires on {len(flagged)}/{len(rows)} months  "
        f"MAPE {flagged['ape'].mean() * 100:.2f}% flagged "
        f"vs {clean['ape'].mean() * 100:.2f}% clean"
    )
    print(
        f"declined (insufficient history): {chosen.n_declined} household-months"
    )

    floor = noise_floor(truth, N_HOLDOUT)
    gap = chosen.mae_total - floor["mae_total"]
    print(
        f"\nheadroom against the floor: {gap:.1f} KES MAE "
        f"({gap / chosen.mae_total * 100:.1f}% of baseline error is removable)"
    )


if __name__ == "__main__":
    main()
