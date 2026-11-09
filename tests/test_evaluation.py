"""
Tests for the evaluation harness.

`test_harness_never_shows_the_target_month` is the most important test in this
repository. Every accuracy number the project reports rests on the claim that
no forecaster saw the month it was predicting, and that claim is asserted here
mechanically rather than trusted.
"""

import pytest

from app.data import provenance
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


# FR-07, amended. These replace test_volatile_flag_predicts_larger_error,
# which asserted that months flagged `volatile` had larger percentage error.
# The flag no longer claims that. It marks households whose monthly spending
# has varied by more than VOLATILE_CV, and for the fitted model no link
# between that and forecast error holds (MODEL_ENSEMBLE.md, "The volatile
# flag"). So the tests assert what is claimed now: the flag fires exactly when
# the household's prior monthly totals vary by more than the threshold, both
# served forecasters agree, and it fires about as often as the rate the
# threshold was chosen for.

VOLATILE_RATE_ON_13_15 = 63 / 1320  # scripts/volatile_threshold.py choose
# Fixed before months 16-18 were read: about three standard errors with the
# 440 households, not the 1,320 household-months, as the independent units,
# because a household's CV barely moves from one month to the next.
VOLATILE_RATE_TOLERANCE = 0.03


def _public_slice():
    import pandas as pd

    from app.data import PUBLIC_DIR, _adapt
    from app.synthetic import monthly_totals

    raw = pd.read_csv(PUBLIC_DIR / "spending_records.csv")
    monthly = monthly_totals(_adapt(raw, "data/public/spending_records.csv"))
    budgets = pd.read_csv(PUBLIC_DIR / "budget_categories.csv").rename(
        columns={"allocated_kes": "allocated"}
    )
    return monthly, budgets


def test_volatile_flag_marks_households_whose_spending_varies():
    """Fires exactly when the prior monthly totals' CV exceeds VOLATILE_CV,
    identically for the blend and the fitted model."""
    from app.forecaster import (
        VOLATILE_CV,
        BudgetBlendForecaster,
        ExtraTreesForecaster,
        household_cv,
    )

    monthly, budgets = _public_slice()
    results = [
        evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3),
        evaluate(ExtraTreesForecaster(budgets=budgets), monthly, n_holdout=3),
    ]
    flags = []
    for result in results:
        rows = result.rows[~result.rows["declined"]]
        expected = [
            household_cv(monthly, u, y, m)[0] > VOLATILE_CV
            for u, y, m in zip(rows["user_id"], rows["year"], rows["month"])
        ]
        assert list(rows["risk_flag"] == "volatile") == expected
        flags.append(list(rows["risk_flag"]))
    assert flags[0] == flags[1], "the two forecasters must flag identically"
    assert any(f == "volatile" for f in flags[0]), "never fires on the slice"
    assert not all(f == "volatile" for f in flags[0])


def test_volatile_flag_is_about_the_household_not_the_interval():
    """A steady household is not flagged and an unsteady one is, whatever
    either forecaster's interval looks like."""
    import pandas as pd

    from app.forecaster import BudgetBlendForecaster, ExtraTreesForecaster

    rows = []
    for i, (y, m) in enumerate([(2025, 10 + k) if k < 3 else (2026, k - 2)
                                for k in range(12)]):
        rows.append(("steady", y, m, "Groceries", 50_000.0))
        rows.append(("unsteady", y, m, "Groceries", 20_000.0 if i % 2 else 100_000.0))
    history = pd.DataFrame(rows, columns=["user_id", "year", "month", "category", "amount"])

    for forecaster in (BudgetBlendForecaster(), ExtraTreesForecaster()):
        assert forecaster.forecast(history, "steady", 2026, 10).risk_flag is None
        assert forecaster.forecast(history, "unsteady", 2026, 10).risk_flag == "volatile"


@pytest.mark.skipif(
    provenance() != "platform-sandbox",
    reason="needs the full sandbox extract in data/ (gitignored)",
)
def test_volatile_flag_fires_on_16_18_at_about_the_rate_chosen_on_13_15():
    from app.data import load_budgets, load_monthly
    from app.forecaster import BudgetBlendForecaster
    from scripts.build_panel import deployed_households

    monthly, _ = load_monthly()
    trained = set(monthly["user_id"]) - set(deployed_households())
    result = evaluate(BudgetBlendForecaster(load_budgets()), monthly, n_holdout=3)
    rows = result.rows[~result.rows["declined"] & result.rows["user_id"].isin(trained)]
    rate = float((rows["risk_flag"] == "volatile").mean())
    assert abs(rate - VOLATILE_RATE_ON_13_15) <= VOLATILE_RATE_TOLERANCE, rate


def test_confidence_separates_steady_from_volatile(population):
    _records, _truth, monthly = population
    result = evaluate(TrailingMedianForecaster(6), monthly, n_holdout=3)
    rows = result.rows[~result.rows["declined"]].copy()
    rows["profile"] = rows["user_id"].str.rsplit("-", n=1).str[0]
    means = rows.groupby("profile")["confidence"].mean()
    assert means["volatile"] < means["steady_tenant"], means.to_dict()
