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

import logging
from pathlib import Path

import pandas as pd

from app.data import SANDBOX_IS_SYNTHETIC, load_budgets, load_monthly, load_transactions
from app.forecaster import (
    MIN_MONTHS_FOR_FORECAST,
    SHIPPED_ARTEFACT,
    BudgetBlendForecaster,
    ExtraTreesForecaster,
    Forecast,
)
from app.insights import insights_for
from app.schemas import BudgetResponse, InsightsResponse, Request, Response

log = logging.getLogger("budget_forecast")
if not log.handlers:
    # Uvicorn configures only its own loggers, so without this an INFO line
    # from here would be dropped. Formatted like uvicorn's own lines.
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False


class ServedForecaster:
    """
    What POST /forecast calls: the fitted model when it loaded, the blend
    otherwise, and the blend for every request the model must not answer.

    The service must never return a 500 because of a model file, so the blend
    answers whenever:

      - the model did not load at startup (missing artefact, corrupt manifest,
        SHA-256 mismatch, wrong feature list, missing calibration);
      - the household has fewer than MIN_MONTHS_FOR_FORECAST months of
        history, so the insufficient-history answer is exactly the blend's, as
        it was before the model, and the model is never touched;
      - the target month is inside the model's training period, which its
        leakage guard refuses (MODEL_ENSEMBLE.md);
      - the model raises for any other reason on a request.

    Both are stateless functions of the history they are handed, so choosing
    between them per request keeps no state either. `method` in the response
    names whichever answered.
    """

    def __init__(self, model: ExtraTreesForecaster | None,
                 blend: BudgetBlendForecaster, reason: str | None = None):
        self.model = model
        self.blend = blend
        self.fallback_reason = reason
        self.name = model.name if model is not None else blend.name

    def _model_may_answer(self, history: pd.DataFrame, user_id: str,
                          year: int, month: int) -> bool:
        if self.model is None:
            return False
        if year * 12 + month <= self.model.last_trained_key:
            return False
        own = history[history["user_id"] == user_id]
        months = (own["year"] * 12 + own["month"]).nunique()
        return months >= MIN_MONTHS_FOR_FORECAST

    def forecast(self, history: pd.DataFrame, user_id: str, year: int, month: int) -> Forecast:
        if self._model_may_answer(history, user_id, year, month):
            try:
                return self.model.forecast(history, user_id, year, month)
            except Exception:  # never a 500 because of the model
                log.exception("model forecast failed for %s %04d-%02d; the blend "
                              "answered", user_id, year, month)
        return self.blend.forecast(history, user_id, year, month)


def select_forecaster(
    artefact: Path = SHIPPED_ARTEFACT, budgets: pd.DataFrame | None = None
) -> ServedForecaster:
    """
    Load the model once, falling back to the blend if anything about the
    model files is wrong. Logs which forecaster is active, once, at INFO.
    """
    budgets = load_budgets() if budgets is None else budgets
    # 80% the household's own spending history, 20% the budget it declared:
    # SANDBOX_RESULTS.md has the evidence. It answers alone when the model
    # cannot, and always for households with too little history.
    blend = BudgetBlendForecaster(budgets, weight=0.8)
    try:
        model = ExtraTreesForecaster(artefact, budgets=budgets)
    except Exception as exc:  # any model-file failure means the blend
        reason = f"{type(exc).__name__}: {exc}"
        log.warning("model not loaded (%s); serving the fallback %s", reason, blend.name)
        served = ServedForecaster(None, blend, reason)
    else:
        served = ServedForecaster(model, blend)
    log.info("forecaster active: %s", served.name)
    return served


# The single swap point. Chosen once, at startup.
FORECASTER = select_forecaster()


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


def handle(body: Request, forecaster: ServedForecaster | None = None) -> Response:
    forecaster = forecaster or FORECASTER
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
            # The blend's name, as before the model: this answer involves no
            # forecaster, and it must not change with which one is active.
            method=f"{forecaster.blend.name} (no history for user)",
        )

    history = _history_before(monthly, body.year, body.month)
    fc: Forecast = forecaster.forecast(history, body.userId, body.year, body.month)

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


def budget_for(user_id: str) -> BudgetResponse:
    """
    The household's declared budget per category, for GET /budget (FR-09).

    The same table the forecaster blends in, so the client shows the budget
    the forecast was actually built from. An unknown household gets an empty
    mapping rather than an error — see BudgetResponse in app/schemas.py.

    Budgets only ever come from the sandbox file, so the flag is the sandbox's.
    """
    budgets = load_budgets()
    rows = budgets[budgets["user_id"] == user_id]
    return BudgetResponse(
        userId=user_id,
        allocated={row.category: round(float(row.allocated), 2) for row in rows.itertuples()},
        isSynthetic=SANDBOX_IS_SYNTHETIC,
    )


def insights(user_id: str, month: int, year: int) -> InsightsResponse:
    """GET /insights: see app/insights.py for what each section means."""
    records, is_synthetic = load_transactions()
    return insights_for(records, user_id, year, month, is_synthetic=is_synthetic)
