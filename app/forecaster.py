"""
The forecaster interface, and the baselines that every model must beat.

THE INTERFACE IS DELIBERATELY STATELESS
---------------------------------------
A forecaster is a function of `(history, user_id, year, month)`, where
`history` holds only months strictly before the target. It is not an object
that is fitted once and then asked about arbitrary months.

That is the whole anti-leakage design. In Phase 1 leakage had to be prevented
by remembering to hold out the right rows; here the evaluation harness slices
the history and a forecaster physically cannot see the month it is predicting,
or any month after it. The discipline is enforced by the type signature rather
than by care.

THE TWO BASELINES
-----------------
`LastMonthForecaster` is the bar the project README actually sets: "beats
'same as last month' on held-out months". It is the number to beat.

`TrailingMedianForecaster` is the baseline the supervisor asked for. The median
rather than the mean because a single 40,000 KES outlier — a deposit, a
one-off purchase — drags a three-month mean far enough to make the next
forecast useless, whereas the median ignores it. This is the baseline wired
into the service first, per the mandated order of work.

Neither baseline corrects for month length, and that is intentional: a
28-day February and a 31-day March contain different numbers of commuting
days, so a trailing average over raw monthly totals carries a systematic error
the model can later remove. Leaving it in the baseline means that improvement
shows up as measured lift rather than being quietly absorbed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

import numpy as np
import pandas as pd

# Below this many months of history we do not pretend to forecast.
MIN_MONTHS_FOR_FORECAST = 3

# A household is called volatile when its honest interval is wide relative to
# its own point forecast — the interval spans more than this share of the
# forecast.
#
# The first version of this used a coefficient-of-variation threshold on the
# monthly total, carried over from Phase 1's recurrence gating. It did not
# work, for two reasons worth recording.
#
# First, no threshold separated the groups: the most variable "student"
# household scored CV 0.284 against 0.204 for the steadiest "volatile" one, so
# any cut-off either missed real volatility or flagged half the students. CV of
# the TOTAL is diluted by a large constant — a 18,000 KES rent makes an
# erratic spender look calm.
#
# Second, and more basic: recovering the generator's own profile labels is not
# what the flag is for. A consumer reading `riskFlag` wants to know whether to
# trust the number in front of it. So the flag is defined on the width of the
# interval relative to the forecast, which is a statement about this specific
# prediction, needs no population labels, and is testable against whether
# error is in fact larger on the months it fires.
VOLATILE_REL_WIDTH = 0.60


@dataclass
class Forecast:
    """What a forecaster returns, before it is shaped into the API contract."""

    total: float
    breakdown: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    low: Optional[float] = None
    high: Optional[float] = None
    risk_flag: Optional[str] = None
    method: str = "unknown"


class Forecaster(Protocol):
    name: str

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        """
        `history` is monthly totals — columns user_id, year, month, category,
        amount — containing ONLY months strictly before (year, month).
        """
        ...


# ───────────────────────── shared helpers ─────────────────────────


def _user_history(history: pd.DataFrame, user_id: str) -> pd.DataFrame:
    return history[history["user_id"] == user_id]


def _month_index(df: pd.DataFrame) -> pd.Series:
    """A sortable integer month key. Avoids string sorting bugs at year ends."""
    return df["year"] * 12 + df["month"]


def _recent_months(df: pd.DataFrame, window: int) -> list[int]:
    keys = sorted(_month_index(df).unique())
    return keys[-window:] if window else keys


def _pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Rows = month key, columns = category, values = total. Gaps become 0.

    A category a household spent on in January and not in February is a real
    zero, not a missing value: they genuinely spent nothing. Filling with NaN
    and taking a median over non-null months would quietly turn an occasional
    expense into a monthly one.
    """
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["mkey"] = _month_index(work)
    out = work.pivot_table(
        index="mkey", columns="category", values="amount", aggfunc="sum"
    ).fillna(0.0)
    return out.sort_index()


def _insufficient(method: str) -> Forecast:
    return Forecast(
        total=0.0,
        breakdown={},
        confidence=0.0,
        risk_flag="insufficient_history",
        method=method,
    )


def _confidence_from_cv(cv: float) -> float:
    """
    Map volatility onto a 0-1 confidence.

    Confidence has to mean something or it is decoration, so it is defined
    here as "how tight is this household's monthly total historically",
    1 / (1 + cv), which is 1.0 for a perfectly constant spender and decays
    smoothly. It is NOT a probability and is not presented as one.

    Sample size is folded in separately, by the caller, using the same
    shrinkage term as Phase 1's recurrence detector: three months of data
    should not buy the same confidence as eighteen.
    """
    if not np.isfinite(cv) or cv < 0:
        return 0.0
    return float(1.0 / (1.0 + cv))


def _evidence(n_months: int, shrinkage: float = 3.0) -> float:
    """n / (n + k). Same shrinkage idea as Phase 1, applied to months."""
    return float(n_months / (n_months + shrinkage))


# ───────────────────────── baselines ─────────────────────────


class LastMonthForecaster:
    """
    "Same as last month." The bar set by the project README.

    No interval, no category modelling, no month-length correction. If a model
    cannot beat this it has earned nothing.
    """

    name = "baseline:last_month"

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        hist = _user_history(history, user_id)
        table = _pivot(hist)
        if table.empty:
            return _insufficient(self.name)

        last = table.iloc[-1]
        breakdown = {c: round(float(v), 2) for c, v in last.items() if v > 0}
        total = round(float(last.sum()), 2)

        n_months = len(table)
        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total,
                breakdown=breakdown,
                confidence=0.0,
                risk_flag="insufficient_history",
                method=self.name,
            )

        return Forecast(
            total=total, breakdown=breakdown, confidence=0.0, method=self.name
        )


class TrailingMedianForecaster:
    """
    Per-category trailing median over the last `window` months.

    This is step 1 of the mandated order of work and what `app/service.py`
    returns until a model is proven to beat it.

    The interval is empirical: the 10th and 90th percentiles of the household's
    own recent monthly totals, widened when there are few months. It makes no
    distributional assumption, which is the point — an 80% normal interval on
    four observations of a skewed quantity is a fiction, whereas "in eight of
    your last ten months the total sat between these two numbers" is a claim
    that can be checked, and the evaluation harness checks it.
    """

    name = "baseline:trailing_median"

    def __init__(self, window: int = 3):
        self.window = window
        self.name = f"baseline:trailing_median_{window}m"

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        hist = _user_history(history, user_id)
        table = _pivot(hist)
        if table.empty:
            return _insufficient(self.name)

        n_months = len(table)
        window = table.iloc[-self.window :] if self.window else table

        per_category = window.median(axis=0)
        breakdown = {
            c: round(float(v), 2) for c, v in per_category.items() if v > 0.005
        }
        total = round(float(per_category.sum()), 2)

        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total,
                breakdown=breakdown,
                confidence=0.0,
                risk_flag="insufficient_history",
                method=self.name,
            )

        monthly_totals = table.sum(axis=1)
        mean_total = float(monthly_totals.mean())
        cv = float(monthly_totals.std(ddof=1) / mean_total) if mean_total > 0 else 0.0

        confidence = round(_confidence_from_cv(cv) * _evidence(n_months), 4)

        # Empirical interval over every month we have, not just the window:
        # three months cannot describe a spread.
        low = float(np.percentile(monthly_totals, 10))
        high = float(np.percentile(monthly_totals, 90))
        # Few months understate the spread. Widen proportionally to how little
        # evidence there is, centred on the point forecast.
        slack = (1.0 - _evidence(n_months)) * max(total, 1.0) * 0.5
        low = max(0.0, min(low, total) - slack)
        high = max(high, total) + slack

        rel_width = (high - low) / total if total > 0 else float("inf")
        risk_flag = "volatile" if rel_width > VOLATILE_REL_WIDTH else None

        return Forecast(
            total=total,
            breakdown=breakdown,
            confidence=confidence,
            low=round(low, 2),
            high=round(high, 2),
            risk_flag=risk_flag,
            method=self.name,
        )


class TrailingMeanForecaster:
    """
    Per-category mean over the household's whole history.

    Added after the sandbox extract showed that monthly spend per
    household-category has a lag-1 autocorrelation of about -0.07 — months are
    independent draws around a constant mean, with no trend, seasonality or
    persistence. Under that process the sample mean over ALL available history
    is the minimum-variance estimator of next month, and a median over a
    6-month window is doubly handicapped: less efficient than the mean for
    symmetric noise, and discarding two thirds of the evidence.

    This is not a model. It is the correct estimator for a process with no
    temporal structure, and it is reported as such. The trailing median remains
    the better choice wherever spend is heavy-tailed, because one anomalous
    month moves a mean and not a median — which is why both are kept and the
    comparison is made on the data rather than assumed.
    """

    name = "baseline:trailing_mean_all"

    def __init__(self, window: int = 0):
        self.window = window
        if window:
            self.name = f"baseline:trailing_mean_{window}m"

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        hist = _user_history(history, user_id)
        table = _pivot(hist)
        if table.empty:
            return _insufficient(self.name)

        n_months = len(table)
        window = table.iloc[-self.window :] if self.window else table

        per_category = window.mean(axis=0)
        breakdown = {c: round(float(v), 2) for c, v in per_category.items() if v > 0.005}
        total = round(float(per_category.sum()), 2)

        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total, breakdown=breakdown, confidence=0.0,
                risk_flag="insufficient_history", method=self.name,
            )

        monthly = table.sum(axis=1)
        mean_total = float(monthly.mean())
        cv = float(monthly.std(ddof=1) / mean_total) if mean_total > 0 else 0.0
        confidence = round(_confidence_from_cv(cv) * _evidence(n_months), 4)

        low = float(np.percentile(monthly, 10))
        high = float(np.percentile(monthly, 90))
        slack = (1.0 - _evidence(n_months)) * max(total, 1.0) * 0.5
        low = max(0.0, min(low, total) - slack)
        high = max(high, total) + slack

        rel_width = (high - low) / total if total > 0 else float("inf")
        return Forecast(
            total=total, breakdown=breakdown, confidence=confidence,
            low=round(low, 2), high=round(high, 2),
            risk_flag="volatile" if rel_width > VOLATILE_REL_WIDTH else None,
            method=self.name,
        )
