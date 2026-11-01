"""
Compare the model against the baselines. Reproduces every number in MODEL.md.

    python3 -m scripts.compare_model              # 12 seeds, both holdouts
    python3 -m scripts.compare_model --seeds 4    # quicker, less reliable

WHY THIS SCRIPT SWEEPS SEEDS
----------------------------
The first version of this script ablated components on ONE synthetic
population and printed a tidy table in which every component appeared to earn
its place. Three of the four were noise. Measured across 12 populations as a
paired difference, the seasonal correction turned out to be significantly
*worse* than doing nothing, and the drift correction changed sign from one
population to the next.

The reason is sample size. One population is 28 households; over a 12-month
holdout that is 300 forecasts, and the standard deviation of the MAE
difference between two forecasters on a single population is around 50-110
KES. The component effects being measured are around 40 KES. They are not
detectable on one population, so a single-population table cannot distinguish
a real improvement from a lucky draw — and it will always produce a story,
because something has to come out on top.

So every figure here is a PAIRED difference: for each seed, both forecasters
see the identical population, and the difference is recorded. Pairing removes
between-population variance, which is far larger than the effects in
question. `t` is a one-sample t statistic on those differences; with 12 seeds,
|t| > 2.2 is significant at the 5% level. `better` counts seeds where the
model won, which is a sign test and makes no distributional assumption at all.

This script is NOT run in CI — it takes minutes. CI reproduces BASELINE.md on
one seed, and `tests/test_model.py` asserts the model still beats the baseline
on a small paired sweep.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from app.evaluate import evaluate, noise_floor
from app.forecaster import LastMonthForecaster, TrailingMedianForecaster
from app.model import Components, TwoShapeForecaster
from app.synthetic import REFERENCE_LAST_MONTH, generate, monthly_totals

FIRST_SEED = 37
DEFAULT_SEEDS = 12
HOLDOUTS = (3, 12)

SHIPPED = Components()  # day_count + fixed_split

# Each variant is compared against the trailing-median baseline on the same
# population. The three rejected components are kept here deliberately: the
# evidence for excluding them is part of the deliverable.
VARIANTS: list[tuple[str, Components]] = [
    ("day only", Components(day_count=True, fixed_split=False, seasonality=False, drift=False, step=False)),
    ("fixed only", Components(day_count=False, fixed_split=True, seasonality=False, drift=False, step=False)),
    ("day+fixed  <-- SHIPPED", SHIPPED),
    ("+seasonality (rejected)", Components(day_count=True, fixed_split=True, seasonality=True, drift=False, step=False)),
    ("+drift (rejected)", Components(day_count=True, fixed_split=True, seasonality=False, drift=True, step=False)),
    ("+step (rejected)", Components(day_count=True, fixed_split=True, seasonality=False, drift=False, step=True)),
]


def _stats(deltas: list[float]) -> tuple[float, float, float, int]:
    arr = np.array(deltas, dtype=float)
    n = len(arr)
    sd = float(arr.std(ddof=1)) if n > 1 else 0.0
    t = float(arr.mean() / (sd / np.sqrt(n))) if sd > 0 else 0.0
    return float(arr.mean()), sd, t, int((arr < 0).sum())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    args = parser.parse_args()

    seeds = list(range(FIRST_SEED, FIRST_SEED + args.seeds))
    pd.set_option("display.width", 220)

    print(
        f"SYNTHETIC DATA — {len(seeds)} populations, seeds "
        f"{seeds[0]}-{seeds[-1]}, 28 households each.\n"
        "All differences are PAIRED against baseline:trailing_median_6m on the\n"
        "same population. Negative = model better.\n"
    )

    for holdout in HOLDOUTS:
        mae: dict[str, list[float]] = {name: [] for name, _ in VARIANTS}
        cat: dict[str, list[float]] = {name: [] for name, _ in VARIANTS}
        naive_gap: list[float] = []
        captured: list[float] = []
        coverage: list[float] = []
        base_coverage: list[float] = []

        for seed in seeds:
            records, truth = generate(seed=seed, last_month=REFERENCE_LAST_MONTH)
            monthly = monthly_totals(records)

            base = evaluate(TrailingMedianForecaster(6), monthly, holdout)
            naive = evaluate(LastMonthForecaster(), monthly, holdout)
            floor = noise_floor(truth, holdout)
            base_coverage.append((base.coverage or 0) * 100)

            for name, components in VARIANTS:
                # Intervals off for the sweep: the interval replays the model
                # per origin per category, which is quadratic here and
                # irrelevant to point accuracy.
                result = evaluate(
                    TwoShapeForecaster(components, intervals=False), monthly, holdout
                )
                mae[name].append(result.mae_total - base.mae_total)
                cat[name].append(result.mae_category - base.mae_category)

                if components == SHIPPED:
                    naive_gap.append(result.mae_total - naive.mae_total)
                    removable = base.mae_total - floor["mae_total"]
                    captured.append(
                        (base.mae_total - result.mae_total) / removable * 100
                        if removable > 0
                        else float("nan")
                    )

            # Coverage needs the intervals, so the shipped config is run once
            # more with them enabled.
            shipped = evaluate(TwoShapeForecaster(SHIPPED), monthly, holdout)
            coverage.append((shipped.coverage or 0) * 100)

        print(f"════════ holdout = {holdout} months ════════")
        header = (
            f"{'variant':26s} {'MAE Δ':>9s} {'sd':>8s} {'t':>7s} {'wins':>7s} "
            f"| {'catMAE Δ':>9s} {'t':>7s} {'wins':>7s}"
        )
        print(header)
        print("─" * len(header))
        for name, _ in VARIANTS:
            m_mean, m_sd, m_t, m_win = _stats(mae[name])
            c_mean, c_sd, c_t, c_win = _stats(cat[name])
            print(
                f"{name:26s} {m_mean:9.1f} {m_sd:8.1f} {m_t:7.2f} "
                f"{m_win:4d}/{len(seeds):<2d} "
                f"| {c_mean:9.1f} {c_t:7.2f} {c_win:4d}/{len(seeds):<2d}"
            )

        print()
        print(f"  shipped vs baseline:last_month   {np.mean(naive_gap):9.1f} KES MAE "
              f"({int(sum(1 for x in naive_gap if x < 0))}/{len(seeds)} seeds) "
              f"— the bar the project README sets")
        print(f"  share of REMOVABLE error captured {np.nanmean(captured):8.1f}%"
              "   (baseline - model) / (baseline - noise floor)")
        print(f"  interval coverage, model {np.mean(coverage):.1f}%  "
              f"baseline {np.mean(base_coverage):.1f}%  nominal 80%")
        print()

    print(
        "|t| > 2.2 is significant at 12 seeds. `wins` is a sign test and\n"
        "assumes nothing about the error distribution.\n\n"
        "Note the asymmetry worth reporting: the model's margin over the\n"
        "trailing median is modest, while its margin over 'same as last\n"
        "month' is roughly 1,400 KES and holds on every seed. The project's\n"
        "stated bar is cleared comfortably; the stricter baseline introduced\n"
        "in BASELINE.md is cleared narrowly."
    )


if __name__ == "__main__":
    main()
