"""
U-CS 37 — the logic behind POST /forecast.

`FORECASTER` below is the single swap point, and the contract in
app/schemas.py did not change when it moved. That is the point of keeping the
swap to one name: the inside can be replaced completely while every consumer
sees the same shape.

It has moved once, from the baseline to the model, and only after the model was
shown to beat the baseline across 12 independent populations:

    baseline:trailing_median_6m    MAE 5137.9    MAPE 13.79%   (BASELINE.md)
    model:two_shape                MAE -97.7 / -37.1 paired     (MODEL.md)
    irreducible noise floor        MAE 4389.7    MAPE 12.74%

The margins are modest and honestly so. Against the bar the project README
actually sets — "beats same as last month" — the margin is roughly 1,400 KES
and holds on every population tested.

If the model ever needs backing out, `FORECASTER = TrailingMedianForecaster(6)`
restores the measured baseline and no consumer notices.

Because the forecaster is a stateless function of history, the only thing this
module does is pick the history, call it, and shape the result into the
contract. There is no fitted state to go stale between requests.
"""

from __future__ import annotations

from app.data import load_monthly
from app.forecaster import Forecast
from app.model import TwoShapeForecaster
from app.schemas import Request, Response

# The single swap point. See MODEL.md for the evidence that this beats the
# baseline, and the three components that were measured and rejected.
FORECASTER = TwoShapeForecaster()


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
