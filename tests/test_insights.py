"""
GET /insights: usual spend, spending calendar and discretionary trend.

What matters most is the same guarantee the forecaster gives: nothing from
the requested month or later reaches an insight. After that, that the
calendar does not report noise as a habit, which on the synthetic slice is
the easy mistake: its generator spreads every category evenly.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.insights import DISCRETIONARY, insights_for
from app.main import app


def _records(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": [r[0] for r in rows],
            "occurred_on": pd.to_datetime([r[1] for r in rows]),
            "category": [r[2] for r in rows],
            "amount": [r[3] for r in rows],
        }
    )


def _monthly(user: str, months: list[str], spend: dict[str, float], day: int = 10):
    return [(user, f"{m}-{day:02d} 09:00", c, a) for m in months for c, a in spend.items()]


SIX = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]


# ── the guarantee ──


def test_nothing_from_the_target_month_or_later_is_used():
    past = _records(_monthly("h1", SIX, {"Rent": 20000.0, "Groceries": 8000.0}))
    future = _records(
        _monthly("h1", ["2026-10", "2026-11"], {"Rent": 99999.0, "Gambling": 50000.0}, day=1)
    )
    alone = insights_for(past, "h1", 2026, 10)
    with_future = insights_for(pd.concat([past, future]), "h1", 2026, 10)
    assert with_future == alone


def test_other_households_are_not_mixed_in():
    mine = _records(_monthly("h1", SIX, {"Rent": 20000.0}))
    theirs = _records(_monthly("h2", SIX, {"Rent": 1.0, "Gambling": 5000.0}))
    assert insights_for(pd.concat([mine, theirs]), "h1", 2026, 10) == insights_for(
        mine, "h1", 2026, 10
    )


# ── usual spend ──


def test_usual_is_the_median_of_the_last_three_months_with_absent_months_as_zero():
    rows = _monthly("h1", SIX[:3], {"Rent": 99000.0})  # outside the three
    rows += [("h1", "2026-07-10 09:00", "Rent", 19000.0)]
    rows += [("h1", "2026-08-10 09:00", "Rent", 20000.0)]
    rows += [("h1", "2026-09-10 09:00", "Rent", 23000.0)]
    rows += [("h1", f"{m}-12 09:00", "Groceries", 8000.0) for m in SIX[3:5]]  # two of three
    usual = insights_for(_records(rows), "h1", 2026, 10).usual

    assert usual.months == ["2026-07", "2026-08", "2026-09"]
    assert usual.breakdown == {"Rent": 20000.0, "Groceries": 8000.0}
    assert usual.total == 28000.0


def test_a_one_off_purchase_is_not_usual():
    rows = _monthly("h1", SIX, {"Rent": 20000.0})
    rows += [("h1", "2026-07-20 21:00", "Crypto Purchase", 18000.0)]
    usual = insights_for(_records(rows), "h1", 2026, 10).usual
    assert "Crypto Purchase" not in usual.breakdown


# ── insufficient history ──


@pytest.mark.parametrize("months", [[], ["2026-08"], ["2026-08", "2026-09"]])
def test_fewer_than_three_months_leaves_every_section_empty(months):
    out = insights_for(_records(_monthly("h1", months, {"Rent": 1.0})), "h1", 2026, 10)
    assert out.historyMonths == len(months)
    assert out.usual is None and out.calendar is None and out.discretionary is None


# ── the calendar ──


def test_shares_sum_to_one_and_even_shares_follow_the_calendar():
    rows = [("h1", f"{m}-{d:02d} 12:00", "Groceries", 100.0) for m in SIX for d in range(1, 29)]
    calendar = insights_for(_records(rows), "h1", 2026, 10).calendar

    assert sum(p.share for p in calendar.monthParts) == pytest.approx(1.0, abs=1e-3)
    assert sum(w.share for w in calendar.weekdays) == pytest.approx(1.0, abs=1e-3)
    assert sum(p.evenShare for p in calendar.monthParts) == pytest.approx(1.0, abs=1e-3)
    # Days 22-31 cover 9 or 10 days of a 30- or 31-day month: more than a quarter.
    assert calendar.monthParts[-1].evenShare > 0.29


def test_evenly_spread_spending_is_not_reported_as_a_habit():
    rng = np.random.default_rng(7)
    months = [f"2025-{m:02d}" for m in range(10, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]
    # Every calendar day equally likely, including the 29th to the 31st.
    rows = [
        ("h1", f"{m}-{int(d):02d} 12:00", "Groceries", float(a))
        for m in months
        for d, a in zip(
            rng.integers(1, pd.Period(m).days_in_month + 1, 30), rng.uniform(500, 3000, 30)
        )
    ]
    calendar = insights_for(_records(rows), "h1", 2026, 10).calendar
    assert not any(p.standsOut for p in calendar.monthParts)
    assert not any(w.standsOut for w in calendar.weekdays)


def test_rent_paid_on_the_first_every_month_stands_out():
    rows = _monthly("h1", SIX, {"Rent": 30000.0}, day=1)
    rows += [("h1", f"{m}-{d:02d} 12:00", "Groceries", 500.0) for m in SIX for d in range(1, 29)]
    parts = insights_for(_records(rows), "h1", 2026, 10).calendar.monthParts
    assert [p.standsOut for p in parts] == [True, False, False, False]


# ── the discretionary trend ──


def test_discretionary_share_is_the_four_categories_over_the_month_total():
    rows = _monthly("h1", SIX, {"Rent": 9000.0})
    rows += [("h1", "2026-07-03 22:00", "Gambling", 500.0)]
    rows += [("h1", "2026-07-04 22:00", "Cash Advance", 500.0)]
    trend = insights_for(_records(rows), "h1", 2026, 10).discretionary

    assert trend.categories == list(DISCRETIONARY)
    assert [m.month for m in trend.months] == SIX
    july = trend.months[3]
    assert (july.total, july.amount, july.share) == (10000.0, 1000.0, 0.1)
    assert july.byCategory == {
        "Gambling": 500.0,
        "Crypto Purchase": 0.0,
        "Cash Advance": 500.0,
        "Luxury Goods": 0.0,
    }
    assert all(m.share == 0.0 for i, m in enumerate(trend.months) if i != 3)


def test_the_window_is_the_last_twelve_months_with_spending():
    months = [f"2025-{m:02d}" for m in range(4, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]
    out = insights_for(_records(_monthly("h1", months, {"Rent": 1.0})), "h1", 2026, 10)
    assert out.historyMonths == 18
    assert out.calendar.months == months[-12:]
    assert [m.month for m in out.discretionary.months] == months[-12:]


# ── the endpoint ──


client = TestClient(app)


def test_endpoint_answers_an_unknown_household_with_200_and_empty_sections():
    response = client.get("/insights", params={"userId": "nobody", "month": 10, "year": 2026})
    assert response.status_code == 200
    body = response.json()
    assert body["historyMonths"] == 0
    assert body["usual"] is None and body["calendar"] is None and body["discretionary"] is None
    assert body["isSynthetic"] is True


@pytest.mark.parametrize(
    "params",
    [
        {"month": 10, "year": 2026},
        {"userId": "", "month": 10, "year": 2026},
        {"userId": "h1", "month": 13, "year": 2026},
        {"userId": "h1", "month": 10},
    ],
)
def test_endpoint_rejects_a_bad_request_with_422(params):
    assert client.get("/insights", params=params).status_code == 422
