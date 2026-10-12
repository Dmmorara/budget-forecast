"""
U-CS 37 — the logic behind POST /forecast.

STEP 1 IS THE BASELINE, and this is it: a per-category trailing median over the
household's last six months, with an empirical interval.

Measured on held-out months before being wired in, as the order of work
requires. The numbers are recorded in BASELINE.md at the repo root, and the
short version is:

    baseline:trailing_median_6m    MAE 5137.9    MAPE 13.79%    coverage 80.0%
    irreducible noise floor        MAE 4389.7    MAPE 12.74%

A model replaces `FORECASTER` below only once it has beaten those numbers on
the same held-out months, and the contract in app/schemas.py does not change
when it does. That is the point of keeping the swap to a single name: the
inside can be replaced completely while every consumer sees the same shape.

Because the forecaster is a stateless function of history, the only thing this
module does is pick the history, call it, and shape the result into the
contract. There is no fitted state to go stale between requests.
"""

from __future__ import annotations

from app.data import load_monthly
from app.forecaster import Forecast, TrailingMedianForecaster
from app.schemas import Request, Response

# The single swap point. Replace with the model once it beats BASELINE.md.
FORECASTER = TrailingMedianForecaster(window=6)


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
