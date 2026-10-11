"""Tests for the forecaster interface and the two baselines."""

import pandas as pd
import pytest

from app.forecaster import (
    MIN_MONTHS_FOR_FORECAST,
    LastMonthForecaster,
    TrailingMedianForecaster,
)

HISTORY_COLUMNS = ["user_id", "year", "month", "category", "amount"]


def test_empty_history_declines(population):
    empty = pd.DataFrame(columns=HISTORY_COLUMNS)
    for forecaster in (LastMonthForecaster(), TrailingMedianForecaster(6)):
        fc = forecaster.forecast(empty, "anyone", 2026, 6)
        assert fc.risk_flag == "insufficient_history"
        assert fc.total == 0.0
        assert fc.confidence == 0.0


def test_short_history_declines_rather_than_guessing():
    history = pd.DataFrame(
        [("u", 2026, 1, "Food", 1000.0), ("u", 2026, 2, "Food", 1100.0)],
        columns=HISTORY_COLUMNS,
    )
    assert len(history["month"].unique()) < MIN_MONTHS_FOR_FORECAST
    fc = TrailingMedianForecaster(6).forecast(history, "u", 2026, 3)
    assert fc.risk_flag == "insufficient_history"
    assert fc.confidence == 0.0


def test_zero_months_are_real_zeros_not_missing():
    """
    A category spent on in one month and not the next is a real zero — the
    household genuinely spent nothing. Treating it as missing and taking a
    median over non-null months only would turn a one-off expense into a
    monthly obligation.
    """
    history = pd.DataFrame(
        [
            ("u", 2026, 1, "Food", 1000.0),
            ("u", 2026, 2, "Food", 1000.0),
            ("u", 2026, 3, "Food", 1000.0),
            ("u", 2026, 4, "Food", 1000.0),
            ("u", 2026, 1, "Other", 9000.0),  # once, in one month of four
        ],
        columns=HISTORY_COLUMNS,
    )
    fc = TrailingMedianForecaster(window=4).forecast(history, "u", 2026, 5)
    assert fc.breakdown.get("Food") == pytest.approx(1000.0)
    assert "Other" not in fc.breakdown, fc.breakdown
    assert fc.total == pytest.approx(1000.0)


def test_median_ignores_a_single_outlier():
    """Why the median and not the mean: one anomalous month must not move it."""
    rows = [("u", 2026, m, "Food", 1000.0) for m in range(1, 6)]
    rows.append(("u", 2026, 6, "Food", 41_000.0))
    history = pd.DataFrame(rows, columns=HISTORY_COLUMNS)

    median = TrailingMedianForecaster(window=6).forecast(history, "u", 2026, 7)
    naive = LastMonthForecaster().forecast(history, "u", 2026, 7)

    assert median.total == pytest.approx(1000.0)
    assert naive.total == pytest.approx(41_000.0)


def test_breakdown_sums_to_total(population):
    _records, _truth, monthly = population
    history = monthly[monthly["user_id"] == "steady_tenant-01"]
    fc = TrailingMedianForecaster(6).forecast(history, "steady_tenant-01", 2027, 1)
    assert fc.breakdown
    assert sum(fc.breakdown.values()) == pytest.approx(fc.total, abs=0.5)


def test_interval_brackets_the_point_forecast(population):
    _records, _truth, monthly = population
    for user_id in ("steady_tenant-01", "student-01", "volatile-01"):
        history = monthly[monthly["user_id"] == user_id]
        fc = TrailingMedianForecaster(6).forecast(history, user_id, 2027, 1)
        assert fc.low is not None and fc.high is not None
        assert fc.low >= 0
        assert fc.low <= fc.total <= fc.high, (user_id, fc.low, fc.total, fc.high)


def test_confidence_is_bounded_and_falls_with_volatility(population):
    _records, _truth, monthly = population
    steady = monthly[monthly["user_id"] == "steady_tenant-01"]
    volatile = monthly[monthly["user_id"] == "volatile-01"]

    a = TrailingMedianForecaster(6).forecast(steady, "steady_tenant-01", 2027, 1)
    b = TrailingMedianForecaster(6).forecast(volatile, "volatile-01", 2027, 1)

    for fc in (a, b):
        assert 0.0 <= fc.confidence <= 1.0
    assert a.confidence > b.confidence


def test_forecaster_cannot_see_the_future_by_construction(population):
    """
    The interface takes history as an argument rather than holding fitted
    state, so a forecaster given a truncated history has no route to the
    months removed from it. Asserted here by checking the result changes when
    history is truncated — if it did not, the forecaster would be reading data
    from somewhere other than its argument.
    """
    _records, _truth, monthly = population
    full = monthly[monthly["user_id"] == "steady_tenant-01"]
    truncated = full[(full["year"] * 12 + full["month"]) <= full["year"].min() * 12 + 6]

    a = TrailingMedianForecaster(6).forecast(full, "steady_tenant-01", 2027, 1)
    b = TrailingMedianForecaster(6).forecast(truncated, "steady_tenant-01", 2027, 1)
    assert a.total != b.total
