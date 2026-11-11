"""
U-CS 37 — the figures behind GET /insights.

Three descriptions of a household's past spending, for the client's Insights
screen. None of them is a forecast and none of them is a judgement:

  usual          the median per category over the three most recent months
                 with spending (a typical month), which the client sets the
                 forecast against
                 ("School Fees +KSh 6,000 vs usual")
  calendar       when in the month, and on which day of the week, the money
                 went out over the last twelve months, against an even spread
  discretionary  the monthly share of a fixed set of categories, over the same
                 twelve months

Every figure comes from transactions dated strictly before the first day of
the requested month. That is the forecaster's rule (FR-05), applied here so an
insight never quotes spending the forecast beside it could not see.

Only aggregates leave this module. No individual transaction, timestamp or
amount is returned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.forecaster import MIN_MONTHS_FOR_FORECAST
from app.schemas import (
    DiscretionaryMonth,
    DiscretionaryTrend,
    InsightsResponse,
    MonthPart,
    SpendingCalendar,
    UsualSpend,
    WeekdayShare,
)

# "Usual" is a typical month of the last three: recent enough to be what the
# household is used to, and the shortest span the forecaster accepts as
# history at all.
USUAL_MONTHS = 3

# The calendar and the discretionary trend share one window, so the screen
# can state it once.
WINDOW_MONTHS = 12

# Stretches of the month, by day. The last runs to the month's end.
MONTH_PARTS = ((1, 7), (8, 14), (15, 21), (22, 31))

# How far above an even spread, in standard errors, a stretch of days must be
# before the screen calls it a pattern. See _stands_out.
STANDS_OUT_SE = 3.0

# The categories the discretionary trend follows. This is the project's own
# grouping, chosen because spending on them is optional and can move quickly;
# it is not a classification the platform makes, and the screen says which
# categories are in it rather than labelling the household.
DISCRETIONARY = ("Gambling", "Crypto Purchase", "Cash Advance", "Luxury Goods")


def _month_text(period: pd.Period) -> str:
    return f"{period.year:04d}-{period.month:02d}"


def _money(value: float) -> float:
    return round(float(value), 2)


def _share(part: float, whole: float) -> float:
    return round(float(part) / float(whole), 4) if whole > 0 else 0.0


def _stands_out(per_month: np.ndarray, even: float) -> bool:
    """
    True when a stretch's monthly share beats an even spread by more than
    three standard errors and by at least 15% of the even share.

    Twelve months of shares from a household that spends evenly still wander:
    in the synthetic slice, whose generator spreads every category evenly, the
    busiest quarter of the month averages 31% against an even 23% by chance
    alone. Each household is tested on eleven stretches (four parts of the
    month, seven weekdays), so the bar is three standard errors rather than
    two: at two, one household in six showed a "habit" that was only noise.
    A real habit, such as rent always paid on the 1st, clears three easily.
    """
    if len(per_month) < MIN_MONTHS_FOR_FORECAST:
        return False
    mean = float(per_month.mean())
    se = float(per_month.std(ddof=1)) / np.sqrt(len(per_month))
    return bool(mean - even > STANDS_OUT_SE * se and mean >= even * 1.15)


def insights_for(
    records: pd.DataFrame,
    user_id: str,
    year: int,
    month: int,
    *,
    is_synthetic: bool = True,
) -> InsightsResponse:
    """
    The Insights for one household, from its transactions before (year, month).

    `records` carries the canonical columns `user_id`, `occurred_on`,
    `category` and `amount`, as `app.data.load_records` returns them.
    """
    target = pd.Timestamp(year=year, month=month, day=1)
    rows = records[(records["user_id"] == user_id) & (records["occurred_on"] < target)]
    rows = rows.assign(period=rows["occurred_on"].dt.to_period("M"))

    months = sorted(rows["period"].unique())
    answer = InsightsResponse(
        userId=user_id,
        month=month,
        year=year,
        historyMonths=len(months),
        isSynthetic=is_synthetic,
    )
    if len(months) < MIN_MONTHS_FOR_FORECAST:
        return answer

    # Month x category totals, a category absent from a month counting as 0.
    table = rows.pivot_table(
        index="period", columns="category", values="amount", aggfunc="sum", fill_value=0.0
    )

    # The median, not the mean: a one-off in one of the three months (a phone,
    # a crypto purchase) is not what the household usually spends, and a mean
    # would report the next month as "below usual" by a third of it.
    usual = table.loc[months[-USUAL_MONTHS:]].median()
    usual = usual[usual > 0].sort_values(ascending=False)
    answer.usual = UsualSpend(
        months=[_month_text(p) for p in months[-USUAL_MONTHS:]],
        total=_money(usual.sum()),
        breakdown={category: _money(value) for category, value in usual.items()},
    )

    window = months[-WINDOW_MONTHS:]
    recent = rows[rows["period"].isin(window)]
    total = float(recent["amount"].sum())
    n = len(window)
    monthly_total = recent.groupby("period")["amount"].sum()
    days = {p: pd.date_range(p.start_time, p.end_time.normalize()) for p in window}

    def slot(mask: pd.Series, in_slot) -> dict:
        """Share, even share and whether it stands out, for one stretch of days."""
        amount = float(recent.loc[mask, "amount"].sum())
        per_month = (
            recent.loc[mask].groupby("period")["amount"].sum().reindex(window, fill_value=0.0)
            / monthly_total.reindex(window)
        )
        even = [sum(in_slot(d) for d in days[p]) / len(days[p]) for p in window]
        return {
            "share": _share(amount, total),
            "evenShare": round(sum(even) / n, 4),
            "standsOut": _stands_out(per_month.to_numpy(), sum(even) / n),
            "averageAmount": _money(amount / n),
        }

    day = recent["occurred_on"].dt.day
    parts = [
        MonthPart(
            firstDay=first,
            lastDay=last,
            **slot((day >= first) & (day <= last), lambda d, a=first, b=last: a <= d.day <= b),
        )
        for first, last in MONTH_PARTS
    ]

    weekday = recent["occurred_on"].dt.weekday + 1
    weekdays = [
        WeekdayShare(weekday=w, **slot(weekday == w, lambda d, w=w: d.weekday() + 1 == w))
        for w in range(1, 8)
    ]
    answer.calendar = SpendingCalendar(
        months=[_month_text(p) for p in window], monthParts=parts, weekdays=weekdays
    )

    trend = []
    for period in window:
        row = table.loc[period]
        by_category = {c: _money(row.get(c, 0.0)) for c in DISCRETIONARY}
        amount = sum(by_category.values())
        trend.append(
            DiscretionaryMonth(
                month=_month_text(period),
                total=_money(row.sum()),
                amount=_money(amount),
                share=_share(amount, row.sum()),
                byCategory=by_category,
            )
        )
    answer.discretionary = DiscretionaryTrend(categories=list(DISCRETIONARY), months=trend)
    return answer
