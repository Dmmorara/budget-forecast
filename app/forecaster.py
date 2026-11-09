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

A fitted model is the one exception to "not fitted once", and
`ExtraTreesForecaster` keeps the claim in an explicit form. It still takes
`(history, user_id, year, month)` and keeps no per-household state between
calls. What it learned from the past is frozen in an artefact whose manifest
records the last month it was trained on, and it refuses any target month at
or before that one. It cannot be asked to forecast a month it was fitted to.

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

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

import numpy as np
import pandas as pd

from app.features import FEATURES, budget_lookup, household_features

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


class BudgetBlendForecaster:
    """
    Blends the household's own history with the budget it declared.

    The platform records `allocated_kes` per household per category, and in the
    staging extract that figure is constant across all 18 months and correlates
    0.80 with actual spend. It is therefore a second, independent estimate of
    the same quantity the history mean estimates — and averaging two noisy
    estimates of one quantity beats either, which is all this class does.

    `weight` is the share given to history. 0.8 was selected on a validation
    split (train months 1-12, test 13-15), which preferred it for total error;
    that split preferred 0.4 for category error, so the two metrics disagree
    and the contract's primary field decided it. An untouched holdout (train
    1-15, test 16-18) reproduced the same preference, and paired over 1,500
    held-out household-months it improves BOTH against history alone:
    MAE -70.4 (t -2.24) and category MAE -22.9 (t -8.26).

    That the two splits agreed is the reason this is believed at all. Several
    earlier results in this project looked convincing on one split and
    evaporated on another, and the weight was NOT chosen by reading the
    holdout.

    NO LEAKAGE: the budget is constant over the whole extract, so using it for
    a future month reveals nothing about that month. See `app.data.load_budgets`
    for what must change if budgets ever become time-varying.

    Falls back to history alone for any household-category with no budget row,
    so a missing budget file degrades to `TrailingMeanForecaster`.
    """

    def __init__(self, budgets: pd.DataFrame | None = None, weight: float = 0.8):
        self.weight = weight
        self.name = f"blend:history{weight:.1f}_budget{1 - weight:.1f}"
        self._budget: dict[tuple[str, str], float] = {}
        if budgets is not None and len(budgets):
            self._budget = {
                (str(r.user_id), str(r.category)): float(r.allocated)
                for r in budgets.itertuples()
            }

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        table = _pivot(_user_history(history, user_id))
        if table.empty:
            return _insufficient(self.name)

        n_months = len(table)
        w = self.weight
        breakdown: dict[str, float] = {}

        categories = set(table.columns) | {
            c for (u, c) in self._budget if u == str(user_id)
        }
        for category in categories:
            hist = (
                float(table[category].mean()) if category in table.columns else 0.0
            )
            allocated = self._budget.get((str(user_id), category))
            value = hist if allocated is None else w * hist + (1 - w) * allocated
            if value > 0.005:
                breakdown[category] = round(value, 2)

        total = round(float(sum(breakdown.values())), 2)
        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total, breakdown=breakdown, confidence=0.0,
                risk_flag="insufficient_history", method=self.name,
            )

        monthly = table.sum(axis=1)
        mean_total = float(monthly.mean())
        cv = float(monthly.std(ddof=1) / mean_total) if mean_total > 0 else 0.0
        low = float(np.percentile(monthly, 10))
        high = float(np.percentile(monthly, 90))
        slack = (1.0 - _evidence(n_months)) * max(total, 1.0) * 0.5
        low = max(0.0, min(low, total) - slack)
        high = max(high, total) + slack
        rel_width = (high - low) / total if total > 0 else float("inf")

        return Forecast(
            total=total, breakdown=breakdown,
            confidence=round(_confidence_from_cv(cv) * _evidence(n_months), 4),
            low=round(low, 2), high=round(high, 2),
            risk_flag="volatile" if rel_width > VOLATILE_REL_WIDTH else None,
            method=self.name,
        )


# ───────────────────────── the fitted model ─────────────────────────

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
SHIPPED_ARTEFACT = MODELS_DIR / "extratrees-v2.joblib"


def conformal_bounds(point, offsets: tuple[float, float], scale: str):
    """
    The interval around `point` from calibrated residual offsets
    `(lower, upper)`, where a residual is actual - predicted on the monthly
    total. `absolute` adds them in KES; `relative` scales them by the point.
    The lower bound is clipped at zero. Works on a number or an array.

    scripts/calibrate_interval.py computes the offsets and calls this same
    function, so the interval that is calibrated is the interval served.
    """
    point = np.asarray(point, dtype=float)
    lower, upper = offsets
    if scale == "absolute":
        low, high = point + lower, point + upper
    elif scale == "relative":
        low, high = point * (1 + lower), point * (1 + upper)
    else:
        raise ValueError(f"unknown scale {scale!r}")
    low = np.maximum(low, 0.0)
    return low, np.maximum(high, low)


def _fallback_verified(offsets: dict, name: str) -> bool:
    """True if the recorded verification calls for the fallback offsets."""
    attempts = (offsets.get("verification") or {}).get("attempts", [])
    if not attempts or attempts[0]["passed"]:
        return False
    if len(attempts) > 1 and attempts[1]["passed"]:
        return True
    raise ModelArtefactError(
        f"{name}: the interval failed its holdout verification and the "
        "fallback has not passed one; refusing to serve it."
    )


class ModelArtefactError(RuntimeError):
    """The artefact or its manifest cannot be trusted. Raised at construction."""


class TrainingPeriodError(ValueError):
    """A target month the model was trained on. Forecasting it would leak."""


class ExtraTreesForecaster:
    """
    The fitted ExtraTrees model (MODEL_ENSEMBLE.md), behind the same stateless
    protocol as every other forecaster.

    Construction loads the artefact once and refuses it unless all three hold:

      integrity   its SHA-256 matches the manifest's;
      features    the manifest's feature list, and the artefact's own, are
                  exactly `app.features.FEATURES`, in order, so the model is
                  served the columns it was fitted on;
      period      the manifest names the last month it was trained on;
      calibration the interval's calibration file names this artefact's
                  SHA-256, so offsets calibrated for another model are refused.

    Each `forecast` builds features from the history it is handed, through
    `app.features.household_features`, the function the training panel was
    built with. No per-household state is kept between calls. The budgets and
    the model are fixed at construction and never written afterwards.

    `forecast` raises TrainingPeriodError for any target month at or before
    `trained_through`, rather than returning a number scored on data it was
    fitted to.

    The interval is split conformal (scripts/calibrate_interval.py): offsets
    taken from how wrong the same configuration was on months it had not been
    fitted on, applied to the point forecast by `conformal_bounds`. It is not
    the spread of the household's past spending, which is what the blend's
    interval measures, and not the spread of the trees, which measures how
    much the forest disagrees with itself rather than how wrong it is.

    Which offsets are served follows the calibration file's recorded holdout
    verification: the calibrated ones if the first verification passed, the
    wider fallback (fixed before the holdout was read) if the first failed and
    the second passed, and none at all if both failed. `use_fallback` overrides
    that, for the verification itself.
    """

    def __init__(
        self,
        artefact: Path = SHIPPED_ARTEFACT,
        manifest: Path | None = None,
        budgets: pd.DataFrame | None = None,
        calibration: Path | None = None,
        use_fallback: bool | None = None,
    ):
        artefact = Path(artefact)
        manifest = (
            Path(manifest) if manifest is not None
            else artefact.with_name(artefact.stem + ".manifest.json")
        )
        record = json.loads(manifest.read_text())

        digest = hashlib.sha256(artefact.read_bytes()).hexdigest()
        if digest != record.get("sha256"):
            raise ModelArtefactError(
                f"{artefact.name}: SHA-256 {digest[:12]}... does not match the "
                f"manifest's {str(record.get('sha256'))[:12]}...; refusing to load it."
            )

        if list(record.get("features", [])) != FEATURES:
            raise ModelArtefactError(
                f"{manifest.name}: its feature list ({len(record.get('features', []))} "
                f"entries) is not app.features.FEATURES ({len(FEATURES)}) in the same "
                "order. The model would be served columns it was not fitted on."
            )

        try:
            year, month = (int(x) for x in record["trained_through"].split("-"))
        except (KeyError, ValueError) as exc:
            raise ModelArtefactError(
                f"{manifest.name}: no usable trained_through ({exc!r})."
            ) from exc
        self.trained_through = f"{year:04d}-{month:02d}"
        self._last_trained_key = year * 12 + month

        # Imported here so that importing this module does not pull in
        # scikit-learn for the forecasters that do not need it.
        import joblib

        bundle = joblib.load(artefact)
        if list(bundle.get("features", [])) != FEATURES:
            raise ModelArtefactError(
                f"{artefact.name}: the artefact's own feature list is not "
                "app.features.FEATURES in the same order."
            )
        self._model = bundle["learners"]["extra_trees"]

        calibration = (
            Path(calibration) if calibration is not None
            else artefact.with_name(artefact.stem + ".calibration.json")
        )
        if not calibration.exists():
            raise ModelArtefactError(
                f"{calibration.name} is missing: the model has no calibrated "
                "interval. Run scripts/calibrate_interval.py."
            )
        offsets = json.loads(calibration.read_text())
        if offsets.get("artefact_sha256") != digest:
            raise ModelArtefactError(
                f"{calibration.name} was calibrated for a different artefact; "
                "refusing to serve its interval with this one."
            )
        if use_fallback is None:
            use_fallback = _fallback_verified(offsets, calibration.name)
        chosen = offsets["fallback_if_undercovered"] if use_fallback else offsets
        self.interval_nominal = float(chosen["nominal"])
        self._scale = offsets["scale"]
        self._offsets = (float(chosen["lower"]), float(chosen["upper"]))
        self._budget = budget_lookup(budgets) if budgets is not None else {}
        self.name = f"model:{artefact.stem}"

    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        if year * 12 + month <= self._last_trained_key:
            raise TrainingPeriodError(
                f"{self.name} was trained on target months up to "
                f"{self.trained_through}; it will not forecast {year:04d}-{month:02d}, "
                "because that month's spending was part of its training data."
            )

        rows = household_features(
            history, self._budget.get(str(user_id), {}), str(user_id), year, month
        )
        if rows.empty:
            return _insufficient(self.name)

        n_months = int(rows["n_history"].iloc[0])
        predicted = np.clip(
            self._model.predict(rows[FEATURES].to_numpy(dtype=float)), 0.0, None
        )
        breakdown = {
            str(c): round(float(v), 2)
            for c, v in zip(rows["category"], predicted)
            if v > 0.005
        }
        total = round(float(sum(breakdown.values())), 2)
        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total, breakdown=breakdown, confidence=0.0,
                risk_flag="insufficient_history", method=self.name,
            )

        low, high = conformal_bounds(total, self._offsets, self._scale)
        low, high = float(low), float(high)

        # CONFIDENCE DESCRIBES THE HOUSEHOLD, NOT THE MODEL. It is the same
        # formula as the baselines and the blend: [1 / (1 + CV)] x [n / (n + 3)],
        # where CV is the coefficient of variation of the household's own
        # monthly totals before the target month and n is how many months there
        # are. A steady household with a long history scores high. It says
        # nothing about how certain the model is of this forecast; that is
        # what the interval is for, and the two must not be read as one.
        mkey = year * 12 + month
        own = _user_history(history, str(user_id))
        own = own[own["year"] * 12 + own["month"] < mkey]
        monthly = _pivot(own).sum(axis=1)
        mean_total = float(monthly.mean())
        cv = float(monthly.std(ddof=1) / mean_total) if mean_total > 0 else 0.0
        confidence = round(_confidence_from_cv(cv) * _evidence(n_months), 4)

        rel_width = (high - low) / total if total > 0 else float("inf")
        return Forecast(
            total=total, breakdown=breakdown, confidence=confidence,
            low=round(low, 2), high=round(high, 2),
            risk_flag="volatile" if rel_width > VOLATILE_REL_WIDTH else None,
            method=self.name,
        )
