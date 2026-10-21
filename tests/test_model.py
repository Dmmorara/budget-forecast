"""
Tests for the forecast model.

`test_model_beats_the_baseline_across_populations` is the one that matters. It
is a paired sweep over four populations rather than a single assertion on one,
because a single-population comparison is what led to three components being
adopted on noise and then removed again. A test that could pass on a lucky
draw is not a test of a forecasting improvement.
"""

import numpy as np
import pandas as pd
import pytest

from app.evaluate import evaluate
from app.forecaster import TrailingMedianForecaster
from app.model import (
    Components,
    TwoShapeForecaster,
    _composition,
    _is_constant,
    _is_recurring,
)
from app.synthetic import generate, monthly_totals

HISTORY_COLUMNS = ["user_id", "year", "month", "category", "amount"]


def _history(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


# ── the headline claim ──


def test_model_beats_the_baseline_across_populations():
    """
    Paired against the trailing median on four independent populations.

    Asserted on the category breakdown rather than the total, because that is
    the robust effect: across 12 seeds it improves on 12 of 12 with t = -7.22,
    while the total improves on 10 of 12 with t = -2.58. A test on the total
    alone would be flaky by construction.
    """
    model_deltas: list[float] = []
    for seed in range(37, 41):
        monthly = monthly_totals(generate(seed=seed)[0])
        base = evaluate(TrailingMedianForecaster(6), monthly, 12)
        model = evaluate(TwoShapeForecaster(intervals=False), monthly, 12)
        model_deltas.append(model.mae_category - base.mae_category)

    assert all(d < 0 for d in model_deltas), model_deltas
    assert np.mean(model_deltas) < -5.0, np.mean(model_deltas)


def test_model_clears_the_projects_stated_bar():
    """
    "Your forecast beats 'same as last month' on held-out months."

    This is the bar the project README actually sets, and the margin is large
    (around 1,400 KES) and holds on every population tested.
    """
    monthly = monthly_totals(generate(seed=37)[0])
    naive = evaluate(
        __import__("app.forecaster", fromlist=["x"]).LastMonthForecaster(), monthly, 12
    )
    model = evaluate(TwoShapeForecaster(intervals=False), monthly, 12)
    assert model.mae_total < naive.mae_total - 500


# ── the rejected components stay rejected ──


def test_rejected_components_are_off_by_default():
    """
    Seasonality, drift and step detection were each measured across 12
    populations and found to be noise or harm. This test exists so that
    re-enabling one is a deliberate act with a failing test attached, rather
    than a quiet default change.
    """
    default = Components()
    assert default.day_count is True
    assert default.fixed_split is True
    assert default.seasonality is False, "rejected: +112.9 KES MAE, t = +3.38"
    assert default.drift is False, "rejected: sign flips across populations"
    assert default.step is False, "rejected: +184 KES MAE"


def test_seasonality_is_not_silently_an_improvement():
    """
    Guards the finding itself. If a future change made seasonality genuinely
    helpful, this test should fail and be rewritten with new evidence — rather
    than the project carrying a claim nobody has re-measured.
    """
    monthly = monthly_totals(generate(seed=37)[0])
    without = evaluate(TwoShapeForecaster(Components(), intervals=False), monthly, 12)
    with_seasonal = evaluate(
        TwoShapeForecaster(
            Components(day_count=True, fixed_split=True, seasonality=True),
            intervals=False,
        ),
        monthly,
        12,
    )
    assert with_seasonal.mae_category >= without.mae_category - 1.0


# ── fixed-obligation detection ──


def test_detects_a_steady_charge_as_constant():
    assert _is_constant(np.array([18_000.0] * 8))
    assert _is_constant(np.array([2_500, 2_480, 2_520, 2_495, 2_510, 2_505], dtype=float))


def test_does_not_treat_erratic_spend_as_constant():
    assert not _is_constant(np.array([900, 4_200, 150, 2_700, 80, 3_300], dtype=float))
    assert not _is_constant(np.array([18_000, 0, 0, 18_000, 0, 18_000], dtype=float))
    assert not _is_constant(np.array([18_000.0, 18_000.0]))


def test_recurrence_is_about_presence_not_amount():
    """
    The distinction the sandbox forced. A recurring obligation may have a wildly
    variable amount and still be perfectly predictable in its timing, and an
    amount-based test finds 8.5% of real recurring categories.
    """
    variable_but_monthly = np.array([900, 4_200, 1_150, 2_700, 3_080, 1_300], dtype=float)
    assert _is_recurring(variable_but_monthly)
    assert not _is_constant(variable_but_monthly), "amount test must disagree here"

    steady_but_occasional = np.array([5_000, 0, 0, 5_000, 0, 0], dtype=float)
    assert not _is_recurring(steady_but_occasional)


def test_recurrence_needs_enough_history():
    assert not _is_recurring(np.array([1_000.0, 1_000.0]))


def test_fixed_charge_absorbs_a_step_quickly():
    """
    A rent increase must show up in the next forecast, not be averaged with
    six months of the old rent. This is the gap the trailing median cannot
    close: it lags a step by about half its window.
    """
    rows = [("u", 2026, m, "Rent", 18_000.0) for m in range(1, 8)]
    rows += [("u", 2026, m, "Rent", 20_000.0) for m in (8, 9, 10)]
    history = _history(rows)

    model = TwoShapeForecaster(intervals=False).forecast(history, "u", 2026, 11)
    base = TrailingMedianForecaster(6).forecast(history, "u", 2026, 11)

    assert model.breakdown["Rent"] == pytest.approx(20_000.0, abs=1.0)
    assert base.breakdown["Rent"] < 19_500, "baseline is expected to lag the step"


def test_fixed_charges_are_not_scaled_by_month_length():
    """
    Rent does not depend on how many Tuesdays a month has. Day-count
    normalisation applied to a fixed charge is simply wrong, and that is why
    `day_count` alone makes the breakdown worse on every population while
    `day+fixed` improves it on every population.
    """
    rows = [("u", 2026, m, "Rent", 18_000.0) for m in range(1, 10)]
    history = _history(rows)
    forecaster = TwoShapeForecaster(intervals=False)

    february = forecaster.forecast(history, "u", 2027, 2)   # 28 days
    march = forecaster.forecast(history, "u", 2027, 3)      # 31 days
    assert february.breakdown["Rent"] == pytest.approx(march.breakdown["Rent"])


# ── day-count normalisation ──


def test_habitual_spend_scales_with_the_target_month():
    """
    A month with more billable days should forecast proportionally more.

    The spend has to be genuinely variable for this to be a test of the
    habitual path. A first version of this fixture put exactly 12 transactions
    of ~60 KES in every month, which gave a coefficient of variation of 0.024
    — so `_is_constant` classified it as a steady charge and correctly refused to
    scale it by month length. A near-constant monthly total is
    indistinguishable from a fixed charge, and treating it as one is right;
    the fixture was simply not describing habitual spend.
    """
    rng = np.random.default_rng(0)
    rows = []
    for m in range(1, 13):
        n_days = _composition(2026 * 12 + m)
        daily_total = 30.0 * (n_days[0] + n_days[1])
        monthly = daily_total * (1.0 + rng.normal(0, 0.22))
        rows.append(("u", 2026, m, "Transport", max(50.0, float(monthly))))
    history = _history(rows)

    values = history["amount"].to_numpy()
    assert not _is_constant(values), "fixture must look habitual, not constant"

    forecaster = TwoShapeForecaster(intervals=False)
    feb = forecaster.forecast(history, "u", 2027, 2).breakdown["Transport"]
    mar = forecaster.forecast(history, "u", 2027, 3).breakdown["Transport"]
    assert mar > feb, (feb, mar)
    # 31 days against 28, so roughly 31/28 — allowing for the weekday weight.
    assert 1.02 < mar / feb < 1.20, mar / feb


def test_composition_counts_days_correctly():
    # January 2027: 31 days, starts on a Friday — 21 weekdays, 10 weekend days.
    weekdays, weekend = _composition(2027 * 12 + 1)
    assert weekdays + weekend == 31
    assert weekend == 10


# ── contract-facing behaviour ──


def test_breakdown_sums_to_total(population):
    _records, _truth, monthly = population
    history = monthly[monthly["user_id"] == "steady_tenant-01"]
    fc = TwoShapeForecaster().forecast(history, "steady_tenant-01", 2027, 1)
    assert fc.breakdown
    assert sum(fc.breakdown.values()) == pytest.approx(fc.total, abs=0.5)


def test_interval_brackets_the_point_forecast(population):
    _records, _truth, monthly = population
    for user_id in ("steady_tenant-01", "student-01", "volatile-01"):
        history = monthly[monthly["user_id"] == user_id]
        fc = TwoShapeForecaster().forecast(history, user_id, 2027, 1)
        assert fc.low is not None and fc.high is not None
        assert fc.low >= 0
        assert fc.low <= fc.total <= fc.high, (user_id, fc.low, fc.total, fc.high)


def test_interval_coverage_is_honest(population):
    """
    The interval claims 80%. A conformal quantile guarantees AT LEAST that, so
    landing a little above is the guarantee working rather than a
    miscalibration — but far above is uninformative padding, so the assertion
    is two-sided.

    An earlier version used the empirical 10th and 90th percentiles and
    achieved 66.7%, which is the worst kind of wrong: confidently too narrow.
    """
    _records, _truth, monthly = population
    result = evaluate(TwoShapeForecaster(), monthly, 12)
    assert result.coverage is not None
    assert 0.78 <= result.coverage <= 0.93, result.coverage


def test_declines_on_short_history():
    history = _history(
        [("u", 2026, 1, "Food", 1000.0), ("u", 2026, 2, "Food", 1100.0)]
    )
    fc = TwoShapeForecaster().forecast(history, "u", 2026, 3)
    assert fc.risk_flag == "insufficient_history"
    assert fc.confidence == 0.0


def test_empty_history_declines():
    empty = pd.DataFrame(columns=HISTORY_COLUMNS)
    fc = TwoShapeForecaster().forecast(empty, "nobody", 2026, 6)
    assert fc.risk_flag == "insufficient_history"
    assert fc.total == 0.0


def test_forecaster_is_stateless(population):
    """
    Two forecasters given the same history must agree, and one given less
    history must differ. The interface takes history as an argument precisely
    so that leakage is impossible; this asserts there is no hidden state
    making that untrue.
    """
    _records, _truth, monthly = population
    full = monthly[monthly["user_id"] == "steady_tenant-01"]
    keys = full["year"] * 12 + full["month"]
    truncated = full[keys <= keys.min() + 8]

    a = TwoShapeForecaster(intervals=False)
    b = TwoShapeForecaster(intervals=False)
    assert a.forecast(full, "steady_tenant-01", 2027, 1).total == pytest.approx(
        b.forecast(full, "steady_tenant-01", 2027, 1).total
    )
    assert a.forecast(truncated, "steady_tenant-01", 2027, 1).total != pytest.approx(
        a.forecast(full, "steady_tenant-01", 2027, 1).total
    )
