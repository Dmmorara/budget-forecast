"""
U-CS 37 — the logic behind POST /forecast.

`FORECASTER` below is the single swap point, and the contract in
app/schemas.py did not change when it moved. That is the point of keeping the
swap to one name: the inside can be replaced completely while every consumer
sees the same shape.

It has moved twice. First from the trailing median to the two-shape model,
which beat it across 12 synthetic populations. Then back off the model when the
sandbox extract arrived and the model turned out to be significantly worse on
real sandbox data — and on to the trailing mean, which beats both.

    on the SANDBOX extract, 500 households, last 3 months held out:
      baseline:trailing_median_6m   MAE 9413.5   catMAE 2102.4
      model:two_shape               MAE 9352.2   catMAE 2121.6   (worse, t +5.25)
      baseline:trailing_mean_all    MAE 9011.6   catMAE 1948.6   (t -2.25 / -9.62)
      best constant fitted on the test months (unreachable)
                                    MAE 7163.9   catMAE 1482.8

Roughly 79% of the remaining error is irreducible under any constant-mean
model, and the sandbox contains no temporal structure to do better with.

That the swap point survived two reversals without the contract changing is
the argument for having one.

Because the forecaster is a stateless function of history, the only thing this
module does is pick the history, call it, and shape the result into the
contract. There is no fitted state to go stale between requests.
"""

from __future__ import annotations

from app.data import load_budgets, load_monthly
from app.forecaster import BudgetBlendForecaster, Forecast
from app.schemas import Request, Response

# The single swap point. SANDBOX_RESULTS.md has the evidence.
#
# 80% the household's own spending history, 20% the budget it declared.
#
# The sandbox has no temporal structure to model — lag-1 autocorrelation of
# monthly spend is about -0.07 — so the gains here come from using a BETTER
# ESTIMATOR and a SECOND SOURCE, not from forecasting. `allocated_kes` is an
# independent estimate of the same quantity the history mean estimates, and
# combining two noisy estimates beats either.
FORECASTER = BudgetBlendForecaster(load_budgets(), weight=0.8)


def _history_before(monthly, year: int, month: int):
    """
    Only months strictly before the one being forecast.

    The service must honour the same rule the evaluation harness enforces. If
    the API were allowed to see the target month when the staging extract
    happens to contain it, every number it returned in testing would be
    partially a lookup, and the measured accuracy would not survive contact
    with a real future month.
    """
    target = year * 12 + month
    keys = monthly["year"] * 12 + monthly["month"]
    return monthly[keys < target]


def handle(body: Request) -> Response:
    monthly, is_synthetic = load_monthly()

    known_users = set(monthly["user_id"].unique())
    if body.userId not in known_users:
        # An unknown household is not an error — it is a new signup. Saying so
        # with a flag is more useful to U-CS 38 than a 404, which would force
        # every consumer to special-case it.
        return Response(
            estimatedTotal=0.0,
            breakdown={},
            confidence=0.0,
            riskFlag="insufficient_history",
            isSynthetic=is_synthetic,
            method=f"{FORECASTER.name} (no history for user)",
        )

    history = _history_before(monthly, body.year, body.month)
    fc: Forecast = FORECASTER.forecast(history, body.userId, body.year, body.month)

    return Response(
        estimatedTotal=round(fc.total, 2),
        breakdown={k: round(v, 2) for k, v in fc.breakdown.items()},
        confidence=fc.confidence,
        riskFlag=fc.risk_flag,
        estimatedTotalLow=fc.low,
        estimatedTotalHigh=fc.high,
        isSynthetic=is_synthetic,
        method=fc.method,
    )
