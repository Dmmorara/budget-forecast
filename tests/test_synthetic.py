"""Tests for the synthetic generator.

The generator is the ground against which everything else is measured, so its
properties are asserted rather than assumed — above all that it is
non-stationary, because a stationary generator silently makes the baseline
unbeatable and the whole evaluation meaningless.
"""

import pandas as pd
import pytest

from app.synthetic import RECORD_COLUMNS, generate, monthly_totals


def test_shape_and_synthetic_flag(population):
    records, _truth, _monthly = population
    assert list(records.columns) == RECORD_COLUMNS
    assert records["is_synthetic"].all(), "every generated row must declare itself"
    assert (records["amount"] > 0).all()
    assert records["user_id"].nunique() == 28


def test_reproducible_for_a_given_seed():
    a, _ = generate(seed=37)
    b, _ = generate(seed=37)
    pd.testing.assert_frame_equal(a, b)


def test_different_seeds_give_different_data():
    a, _ = generate(seed=37)
    b, _ = generate(seed=38)
    assert not a.equals(b)


def test_generator_is_non_stationary(population):
    """
    Guard against regression to the stationary version.

    The first version of this generator drew every household from fixed
    parameters. The 6-month trailing median then scored 10.16% MAPE against an
    irreducible floor of 10.20% — it had saturated the data completely, because
    a trailing median is the optimal estimator of a stationary process, and no
    model could ever have beaten it. December must actually be more expensive
    than November for the seasonal categories, or there is nothing to learn.
    """
    _records, _truth, monthly = population
    festive = monthly[monthly["category"].isin(["Food", "Personal"])]
    by_month = festive.groupby("month")["amount"].mean()
    assert by_month[12] > by_month[11] * 1.15, by_month.to_dict()


def test_rent_escalates_over_time(population):
    """A step change a trailing window structurally cannot track."""
    _records, _truth, monthly = population
    rent = monthly[monthly["category"] == "Rent"].copy()
    rent["mkey"] = rent["year"] * 12 + rent["month"]
    first_half = rent[rent["mkey"] <= rent["mkey"].median()]["amount"].mean()
    second_half = rent[rent["mkey"] > rent["mkey"].median()]["amount"].mean()
    assert second_half > first_half


def test_monthly_totals_conserve_money(population):
    records, _truth, monthly = population
    assert monthly["amount"].sum() == pytest.approx(records["amount"].sum(), rel=1e-6)


def test_truth_records_an_expectation_for_every_household_month(population):
    _records, truth, monthly = population
    observed = set(zip(monthly["user_id"], monthly["year"], monthly["month"]))
    claimed = set(zip(truth["user_id"], truth["year"], truth["month"]))
    assert observed <= claimed


def test_new_user_profile_has_short_history(population):
    """The insufficient-history path needs households that trigger it."""
    _records, _truth, monthly = population
    months = (
        monthly.assign(k=monthly["year"] * 12 + monthly["month"])
        .groupby("user_id")["k"]
        .nunique()
    )
    short = months[months < 3]
    assert len(short) > 0
    assert all(u.startswith("new_user") for u in short.index)
