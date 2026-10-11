"""
Tests for the evaluation harness.

`test_harness_never_shows_the_target_month` is the most important test in this
repository. Every accuracy number the project reports rests on the claim that
no forecaster saw the month it was predicting, and that claim is asserted here
mechanically rather than trusted.
"""

from app.evaluate import evaluate, holdout_months, noise_floor
from app.forecaster import (
    MIN_MONTHS_FOR_FORECAST,
    LastMonthForecaster,
    TrailingMedianForecaster,
)


def test_holdout_is_the_last_months(population):
    _records, _truth, monthly = population
    keys = holdout_months(monthly, 3)
    all_keys = sorted(set((monthly["year"] * 12 + monthly["month"]).tolist()))
    assert keys == all_keys[-3:]
    assert len(keys) == 3


def test_harness_never_shows_the_target_month(population):
    """
    A spy forecaster records every history it is handed. If any row falls in or
    after the month being predicted, the evaluation is leaking and every number
    this project reports is inflated.
    """
    _records, _truth, monthly = population
    violations = []

    class Spy:
        name = "spy"

        def forecast(self, history, user_id, year, month):
            target = year * 12 + month
            if not history.empty:
                keys = history["year"] * 12 + history["month"]
                if (keys >= target).any():
                    violations.append((user_id, year, month, int(keys.max())))
            return TrailingMedianForecaster(6).forecast(history, user_id, year, month)

    evaluate(Spy(), monthly, n_holdout=3)
    assert not violations, violations


def test_declined_months_are_reported_not_scored(population):
    """
    A service that answers nothing records a perfect zero error. Declined
    months must therefore sit outside every error metric and be counted
    separately.
    """
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)

    declined = result.rows[result.rows["declined"]]
    assert len(declined) > 0, "the new_user profile should trigger this path"
    assert (declined["n_history_months"] < MIN_MONTHS_FOR_FORECAST).all()
    assert result.n_forecasts + result.n_declined == len(result.rows)


def test_trailing_median_beats_same_as_last_month(population):
    """The bar the project README actually sets."""
    _records, _truth, monthly = population
    naive = evaluate(LastMonthForecaster(), monthly, n_holdout=3)
    median = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    assert median.mae_total < naive.mae_total
    assert median.mape_total < naive.mape_total
    assert median.mae_category < naive.mae_category


def test_no_forecaster_beats_the_noise_floor(population):
    """
    A sanity check on the floor itself. A forecaster scoring below it means
    either the floor is computed wrongly or the harness is leaking — both worth
    catching loudly, because a result that is too good is the easiest kind to
    publish by accident.
    """
    _records, truth, monthly = population
    floor = noise_floor(truth, 3)
    for forecaster in (LastMonthForecaster(), TrailingMedianForecaster(6)):
        result = evaluate(forecaster, monthly, n_holdout=3)
        assert result.mae_total > floor["mae_total"], forecaster.name


def test_baseline_matches_the_recorded_numbers(population):
    """
    BASELINE.md states MAE 5137.9 / MAPE 13.79% for trailing_median_6m. If this
    test fails, either the numbers in the report are stale or something changed
    that should have been noticed — a model is only "better" against a figure
    that still reproduces.
    """
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    assert round(result.mae_total, 1) == 5137.9, result.mae_total
    assert round(result.mape_total * 100, 2) == 13.79, result.mape_total


def test_interval_coverage_is_in_the_honest_range(population):
    """
    The intervals claim roughly 80%. Coverage far below that is a lie; far above
    it is uninformative padding. Both are failures, so the assertion is
    two-sided.
    """
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    assert result.coverage is not None
    assert 0.70 <= result.coverage <= 0.92, result.coverage


def test_volatile_flag_predicts_larger_error(population):
    """
    The flag earns its place only if it is right: months carrying `volatile`
    must really have worse percentage error than months that do not.

    An earlier version asserted that the flag recovered the generator's own
    profile labels, which is a different and much weaker claim — a flag could
    match those labels perfectly and still tell a consumer nothing about
    whether to trust a given number.
    """
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    rows = result.rows[~result.rows["declined"]]

    flagged = rows[rows["risk_flag"] == "volatile"]["ape"].dropna()
    clean = rows[rows["risk_flag"].isna()]["ape"].dropna()

    assert len(flagged) > 0, "the flag never fires — it cannot be doing any work"
    assert len(clean) > 0
    assert flagged.mean() > clean.mean(), (flagged.mean(), clean.mean())


def test_confidence_separates_steady_from_volatile(population):
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    rows = result.rows[~result.rows["declined"]].copy()
    rows["profile"] = rows["user_id"].str.rsplit("-", n=1).str[0]
    means = rows.groupby("profile")["confidence"].mean()
    assert means["volatile"] < means["steady_tenant"], means.to_dict()
