"""
The forecast model. Step 3 of the mandated order of work.

It must beat the recorded baseline — MAE 5137.9 / MAPE 13.79% on the seed-37
synthetic population — and it is built against the four specific weaknesses
BASELINE.md identified in a trailing window, rather than by reaching for a
general-purpose regressor and hoping.

WHAT WAS ATTEMPTED, AND WHAT SURVIVED
-------------------------------------
BASELINE.md named four weaknesses in a trailing window. A correction was built
for each. Only two of the four survived validation, and the result is a modest
but real improvement rather than the large one the first measurements
suggested.

1.  Month length and weekday composition. Habitual spend accrues per day, and
    a 28-day February holds roughly three fewer commuting days than a 31-day
    March. A median over raw monthly totals carries that error permanently.
    -> KEPT, conditionally. Habitual categories are modelled as a daily rate
       multiplied by the target month's own composition. On its own this is
       NOT an improvement; it pays only once (4) has removed fixed charges
       from the series.

2.  Seasonality. It repeats annually, so a 3- or 6-month window never
    anticipates December.
    -> REJECTED. Significantly worse than doing nothing: twelve monthly
       factors cannot be estimated from 18-27 months of history. See
       `Components`.

3.  Drift. It compounds, so a backward-looking average is biased low for as
    long as prices keep rising.
    -> REJECTED. The measured effect changes sign across populations.

4.  Step changes. A rent escalation shifts the level discontinuously, and a
    trailing median lags it by about half its window.
    -> KEPT for fixed obligations, which are detected separately and levelled
       off the last three months only. REJECTED for habitual spend, where
       detecting the step cost more in variance than it recovered.

HOW THESE CONCLUSIONS WERE REACHED, AND HOW THEY WERE NEARLY GOT WRONG
----------------------------------------------------------------------
Every component above was first measured on a single synthetic population
(seed 37) and every one of them appeared to work. Validated across 12
independent populations as a paired difference, three of the four turned out
to be noise or harm. The standard deviation of the MAE difference between two
forecasters on one population of 28 households is about 108 KES; the effects
being chased are around 40. They were never detectable at that sample size.

So the numbers in MODEL.md are paired across seeds, and no component is
claimed on the strength of one population. A single-population ablation table
is not evidence, however many components it contains and however principled
each one sounds.

THE TWO SHAPES
--------------
The split between fixed obligations and habitual spend is the one finding that
survived the project's change of scope intact. It came out of Daniel's real
M-Pesa statements in Phase 1: recurring spend has two distinct forms, a small
number of fixed per-payee obligations (rent, wifi) and a large number of
habitual category-level transactions (130 transport payees with a median of one
transaction each). A single model of "recurring spend" fits neither. The
synthetic generator was built to reproduce that structure, so the architecture
is grounded in observed behaviour and only its coefficients are synthetic.

ON DELIBERATE RESTRAINT
-----------------------
Every component here is switchable, and `scripts/compare_model.py` ablates
them. That is not decoration: only 14.6% of the baseline's error is removable
at all, so a component that cannot be shown to pay for itself is removed rather
than kept on the grounds that it sounds principled. The ablation table is the
evidence for which of the four gaps above actually mattered.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.forecaster import (
    MIN_MONTHS_FOR_FORECAST,
    VOLATILE_REL_WIDTH,
    Forecast,
    _confidence_from_cv,
    _evidence,
    _insufficient,
    _pivot,
    _user_history,
)

# ── recurrence and constancy are DIFFERENT properties ──
#
# Measured against the sandbox's own `is_recurring` label (4,000 recurring and
# 1,334 non-recurring household-category pairs):
#
#   detector                        precision   recall      F1
#   amount CV (_is_constant)            0.974    0.085   0.156
#   presence >= 90% of months           1.000    1.000   1.000
#   gap CV < 0.5                        1.000    0.107   0.194
#   day-of-month concentration > 0.8    0.000    0.000   0.000
#
# Median amount CV is 0.231 for NON-recurring pairs and 0.240 for recurring
# ones. Amount variability carries essentially no information about whether
# something recurs — a rent that changes every month recurs just as reliably as
# one that does not. An earlier version of this module used amount CV alone and
# called the result a fixed-obligation detector; it found 8.5% of them.
#
# So the two properties are now separate, because they answer different
# questions and a category can have either, both or neither:
#
#   recurring   — does it happen every month?  Answers WHETHER to forecast it.
#                 Detected from presence. Rent, Transport and Groceries all are.
#   constant    — is the amount steady?        Answers HOW to level it.
#                 Detected from amount CV. Rent is; Transport is not.
#
# Day-of-month concentration scores zero here only because these are CATEGORY
# aggregates with many transactions spread across the month. At payee grain —
# Phase 1's problem — it is informative, and Phase 1's RecurrenceDetector used
# interval regularity for exactly that reason. The right timing signal depends
# on the grain.
FIXED_WINDOW = 6
FIXED_MIN_PRESENT = 5          # of FIXED_WINDOW months
FIXED_MAX_CV = 0.12
RECURRING_MIN_PRESENCE = 0.90

# ── level estimation ──
FIXED_LEVEL_WINDOW = 3         # short, so a step is absorbed quickly
HABITUAL_LEVEL_WINDOW = 6      # longer, because habitual spend is noisier

# ── seasonality ──
# Shrinkage of 1.5 means two observations of a calendar month carry ~57% of
# their raw signal. With at most two Decembers in 30 months, anything less
# conservative is fitting a single festive season.
SEASONAL_SHRINKAGE = 1.5
SEASONAL_CLAMP = (0.60, 1.80)

# ── drift ──
DRIFT_WINDOW = 12
DRIFT_CLAMP = (0.90, 1.15)     # total multiplier, not per month
# The level is a median over HABITUAL_LEVEL_WINDOW months, so it describes a
# point roughly this many months before the target.
DRIFT_LEAD = 3.5

# ── intervals ──
# Nominal coverage the interval claims, matching the baseline's so the two are
# directly comparable.
TARGET_COVERAGE = 0.80


# ── step detection on habitual spend ──
# A household that moves or changes commute shifts its habitual level
# discontinuously. The level window is 6 months, so it lags such a step by
# about three. A step is declared when the last 3 months differ from the
# preceding 3 by more than this many robust deviations, and the level is then
# taken from the recent months alone.
STEP_THRESHOLD = 2.5


@dataclass(frozen=True)
class Components:
    """
    Which corrections are active. Used by the ablation script.

    Three of the five default to OFF. All three were implemented, measured
    across 12 independent synthetic populations, and rejected on the evidence.
    They stay in the code because the ablation table documenting why they were
    dropped is worth more to the project than any of them would have been.

    Every figure below is a paired difference against the trailing-median
    baseline over a 12-month holdout, across 12 seeds. Negative is better.

    `seasonality` — REJECTED, and it is the instructive one. On its own it
    costs +112.9 KES of MAE with t = +3.38, significantly *worse* than doing
    nothing, and it worsens the category breakdown on 12 seeds out of 12.
    Twelve monthly factors estimated from 18-27 months means one or two
    observations per factor, and SEASONAL_SHRINKAGE of 1.5 let two
    observations carry 57% of their raw signal, which is far too generous.
    The seasonal structure genuinely exists in the data; it is not estimable
    from this much history. A single population made it look worth 191 KES.

    `drift` — REJECTED. The MAE difference changes sign across seeds (mean
    -6.4 and -1.8 on two holdout lengths, never consistently negative) while
    the category breakdown is worse on all 8 runs measured. An earlier
    ungated version was clearly harmful; R²-gating made it merely
    indistinguishable from nothing.

    `step` — REJECTED. Shortening the level window when the habitual level
    shifts, aimed at the quarter of households that move. Costs 184 KES of MAE
    even after the decomposition order was corrected. The mechanism it targets
    is real, but estimating a step from three months of a noisy series costs
    more in variance than it recovers in bias.

    What survives is `day_count` + `fixed_split`: -37.1 KES MAE, t = -2.58,
    better on 10 seeds of 12, and better on the category breakdown on 12 of
    12. Note that `day_count` alone is NOT an improvement (+16.5 KES, and
    worse on the breakdown on 12 seeds of 12) — it only pays once the fixed
    split has removed rent from the series, because rent does not depend on
    how many Tuesdays a month has.
    """

    day_count: bool = True
    seasonality: bool = False
    drift: bool = False
    fixed_split: bool = True
    step: bool = False

    def label(self) -> str:
        on = [
            name
            for name, flag in (
                ("day", self.day_count),
                ("seas", self.seasonality),
                ("drift", self.drift),
                ("fixed", self.fixed_split),
                ("step", self.step),
            )
            if flag
        ]
        return "+".join(on) if on else "none"


def _mkey_to_ym(mkey: int) -> tuple[int, int]:
    year, month = divmod(mkey, 12)
    return (year - 1, 12) if month == 0 else (year, month)


def _composition(mkey: int) -> tuple[int, int]:
    """(billable weekdays, weekend days) in the month `mkey` identifies."""
    year, month = _mkey_to_ym(mkey)
    n_days = calendar.monthrange(year, month)[1]
    weekend = sum(
        1 for d in range(1, n_days + 1) if calendar.weekday(year, month, d) >= 5
    )
    return n_days - weekend, weekend


def _day_weight(mkey: int, weekend_weight: float) -> float:
    """
    A month's billable-day weight.

    Weekend days are weighted rather than counted equally, because habitual
    spend is not uniform across the week. The weight is estimated per category
    from the household's own history, so a weekday commuter and a weekend
    shopper are described differently rather than both being assumed flat.
    """
    weekdays, weekend = _composition(mkey)
    return weekdays + weekend_weight * weekend


def _estimate_weekend_weight(mkeys: list[int], values: np.ndarray) -> float:
    """
    Least squares for `total ~ a * weekdays + b * weekend`, returned as b / a.

    Month-to-month variation in weekday count is small (20 to 23), so this is a
    weak signal and the fit is unstable on short or noisy histories. It is
    therefore clamped to a plausible range and falls back to 1.0 — every day
    equal, i.e. plain day-count normalisation — whenever the fit is degenerate.
    Preferring a defensible fallback over an unstable coefficient is the whole
    point; an unclamped fit produced negative weekend rates on some households.
    """
    if len(mkeys) < 6:
        return 1.0
    comp = np.array([_composition(m) for m in mkeys], dtype=float)
    if np.linalg.matrix_rank(comp) < 2:
        return 1.0
    try:
        coef, *_ = np.linalg.lstsq(comp, values, rcond=None)
    except np.linalg.LinAlgError:
        return 1.0
    a, b = float(coef[0]), float(coef[1])
    if not np.isfinite(a) or not np.isfinite(b) or a <= 0 or b <= 0:
        return 1.0
    return float(np.clip(b / a, 0.25, 3.0))


def _seasonal_map(
    mkeys: list[int], normalised: np.ndarray
) -> dict[int, float]:
    """
    A multiplicative factor per calendar month, each shrunk toward 1.0.

    Compares each calendar month's observations against the household's overall
    level. A month never observed gets exactly 1.0, which is the honest answer
    rather than borrowing a neighbour's.

    Returned as a full map rather than a single factor for the target month,
    because the series has to be DESEASONALISED before the level and any step
    are estimated. An earlier version applied the seasonal factor only at the
    end, which left seasonality inside the series the level was measured from —
    and the step detector then read December as a permanent change of
    circumstances, levelling off an inflated window. That cost 310 KES of MAE
    on the three-month holdout. Order of decomposition is not cosmetic.
    """
    factors: dict[int, float] = {}
    overall = float(np.mean(normalised))
    if overall <= 0:
        return factors

    months = np.array([_mkey_to_ym(m)[1] for m in mkeys])
    for month in range(1, 13):
        same = normalised[months == month]
        if len(same) == 0:
            continue
        raw = float(np.mean(same)) / overall
        factor = 1.0 + (raw - 1.0) * _evidence(len(same), SEASONAL_SHRINKAGE)
        factors[month] = float(np.clip(factor, *SEASONAL_CLAMP))
    return factors


def _drift_multiplier(normalised: np.ndarray) -> float:
    """
    Capped extrapolation of recent per-month growth, weighted by fit quality.

    Ordinary least squares on the last DRIFT_WINDOW months, as a fraction of
    the mean level, projected DRIFT_LEAD months forward from the middle of the
    level window.

    The correction is scaled by the fit's R², which is the gate that makes this
    defensible at all. An ungated version of this function made the forecast
    worse on every household profile, by between 141 and 211 KES of MAE: a
    straight line through twelve noisy months has a slope whatever the data
    does, and extrapolating it amplifies noise into a confident wrong number.
    Weighting by explained variance means an erratic household contributes
    almost no drift while a steadily inflating one contributes nearly all of
    its measured trend.
    """
    series = normalised[-DRIFT_WINDOW:]
    if len(series) < 6:
        return 1.0
    mean = float(np.mean(series))
    if mean <= 0:
        return 1.0

    x = np.arange(len(series), dtype=float)
    slope, intercept = np.polyfit(x, series, 1)

    total_var = float(np.sum((series - mean) ** 2))
    if total_var <= 0:
        return 1.0
    residual_var = float(np.sum((series - (slope * x + intercept)) ** 2))
    r_squared = max(0.0, 1.0 - residual_var / total_var)

    deviation = (float(slope) / mean) * DRIFT_LEAD * r_squared
    return float(np.clip(1.0 + deviation, *DRIFT_CLAMP))


def _level(normalised: np.ndarray, detect_step: bool) -> float:
    """
    The habitual level, from a window that shortens when the level has moved.

    A household that moves house or changes commute shifts its habitual spend
    as a step, and a 6-month median averages the old life with the new one for
    three months after it happens. Comparing the last three months against the
    preceding three, scaled by the series' own robust spread, detects that
    without assuming when it occurred — which matters because in production the
    service finds out a household's circumstances changed only by watching the
    spend change.

    Deliberately conservative: a single unusual month must not trigger it, so
    the comparison is between medians of three rather than between points, and
    the threshold is in units of the series' own variability rather than a
    fixed percentage.
    """
    window = normalised[-HABITUAL_LEVEL_WINDOW:]
    if not detect_step or len(normalised) < 6:
        return float(np.median(window))

    recent = normalised[-3:]
    previous = normalised[-6:-3]

    spread = float(np.median(np.abs(normalised - np.median(normalised))))
    if spread <= 0:
        return float(np.median(window))

    shift = abs(float(np.median(recent)) - float(np.median(previous)))
    if shift > STEP_THRESHOLD * spread:
        return float(np.median(recent))
    return float(np.median(window))


def _is_recurring(values: np.ndarray) -> bool:
    """
    Does this category appear in nearly every month?

    Presence over the whole history, not amount steadiness. On the sandbox this
    separates the platform's own `is_recurring` label perfectly: every recurring
    pair is present in all 18 months, every non-recurring one in at most 14.

    Note what this does NOT buy on the sandbox. Gating sporadic categories to
    zero improves total MAE by 76 KES but worsens the category breakdown by 106
    (t = +19.1, better on only 4.3% of forecasts), because knowing a category is
    sporadic says nothing about WHEN it will occur — occurrence there is
    independent month to month. The detector is correct; the data gives it
    nothing to exploit. On data with genuine recurring obligations it should,
    and that remains untested.
    """
    if len(values) < FIXED_WINDOW:
        return False
    return float((values > 0).mean()) >= RECURRING_MIN_PRESENCE


def _is_constant(values: np.ndarray) -> bool:
    """
    Is the amount steady when it does occur?

    Named for what it measures. This is NOT a recurrence test — see the note
    above the constants — and it must not be used as one.
    """
    recent = values[-FIXED_WINDOW:]
    if len(recent) < FIXED_WINDOW:
        return False
    present = recent[recent > 0]
    if len(present) < FIXED_MIN_PRESENT:
        return False
    mean = float(np.mean(present))
    if mean <= 0:
        return False
    cv = float(np.std(present, ddof=1) / mean) if len(present) > 1 else 0.0
    return cv < FIXED_MAX_CV


class TwoShapeForecaster:
    """
    Fixed obligations plus habitual daily rates, with seasonality and drift.

    Stateless, like every forecaster here: it receives only months strictly
    before the one being predicted, so it cannot see the future by
    construction.
    """

    def __init__(self, components: Components | None = None, intervals: bool = True):
        self.components = components or Components()
        # The interval replays the model over the household's own history, so
        # it costs one forecast per origin per category. That is negligible for
        # a single API request and quadratic across a long evaluation, so the
        # ablation script turns it off to measure point accuracy alone.
        self.intervals = intervals
        self.name = (
            "model:two_shape"
            if self.components == Components()
            else f"model:two_shape[{self.components.label()}]"
        )

    # ── per-category forecast ──
    def _forecast_category(
        self,
        mkeys: list[int],
        values: np.ndarray,
        target_mkey: int,
        target_month: int,
    ) -> float:
        c = self.components

        if c.fixed_split and _is_constant(values):
            # A steady charge. No day-count scaling (rent does not depend on
            # how many Tuesdays a month has), no seasonality, no drift — the
            # last three months already carry any step that has happened.
            recent = values[-FIXED_LEVEL_WINDOW:]
            return float(np.median(recent))

        # The decomposition runs in this order on purpose: remove the effects
        # that are known functions of the calendar first, so that the level,
        # the step and the trend are all estimated on a series from which
        # calendar effects have already been taken out.
        #
        #   1. day composition  — a known property of the target month
        #   2. seasonality      — a repeating function of calendar month
        #   3. level and step   — what is left, which is the household's life
        #   4. drift            — the direction that remainder is moving
        #
        # Estimating any later stage before an earlier one has been removed
        # attributes calendar structure to the household's circumstances.

        if c.day_count:
            weekend_weight = _estimate_weekend_weight(mkeys, values)
            weights = np.array([_day_weight(m, weekend_weight) for m in mkeys])
            weights[weights <= 0] = 1.0
            normalised = values / weights
            target_weight = _day_weight(target_mkey, weekend_weight)
        else:
            normalised = values.astype(float)
            target_weight = 1.0

        if c.seasonality:
            seasonal_map = _seasonal_map(mkeys, normalised)
            divisors = np.array(
                [seasonal_map.get(_mkey_to_ym(m)[1], 1.0) for m in mkeys]
            )
            divisors[divisors <= 0] = 1.0
            deseasonalised = normalised / divisors
            target_seasonal = seasonal_map.get(target_month, 1.0)
        else:
            deseasonalised = normalised
            target_seasonal = 1.0

        level = _level(deseasonalised, c.step)
        drift = _drift_multiplier(deseasonalised) if c.drift else 1.0

        return max(0.0, level * target_weight * target_seasonal * drift)

    # ── interval ──
    def _interval(
        self, table: pd.DataFrame, point: float, n_months: int
    ) -> tuple[float, float]:
        """
        Residual-based, from one-step-ahead errors the model would have made.

        Replaying the model over the household's own history gives the spread
        of its actual mistakes, which is a far better description of
        uncertainty than the spread of the monthly totals themselves — the
        baseline's interval was wide partly because it included variation the
        model can now explain. Quantiles of real residuals keep the stated
        level meaningful; `test_interval_coverage_is_honest` checks it.
        """
        mkeys = list(table.index)
        residuals: list[float] = []

        start = max(MIN_MONTHS_FOR_FORECAST, len(mkeys) - DRIFT_WINDOW)
        for i in range(start, len(mkeys)):
            predicted = 0.0
            for category in table.columns:
                predicted += self._forecast_category(
                    mkeys[:i],
                    table[category].to_numpy()[:i],
                    mkeys[i],
                    _mkey_to_ym(mkeys[i])[1],
                )
            actual = float(table.iloc[i].sum())
            if actual > 0:
                residuals.append((predicted - actual) / actual)

        if len(residuals) < 3:
            # Not enough replay to describe a spread. Fall back to a wide,
            # evidence-scaled band rather than inventing a tight one.
            slack = 0.35 + 0.4 * (1.0 - _evidence(n_months))
            return max(0.0, point * (1 - slack)), point * (1 + slack)

        # A conformal quantile, not an empirical percentile.
        #
        # The first version took the 10th and 90th percentiles of these
        # residuals and achieved 66.7% coverage against a nominal 80%. The
        # reason is small samples: the empirical 90th percentile of a dozen
        # points sits systematically inside the true 90th percentile, so the
        # interval is confidently too narrow — the worst failure available to
        # a confidence range, because it is wrong in the direction that looks
        # good.
        #
        # Taking the k-th smallest absolute residual with k = ceil(q(n+1))
        # instead gives the finite-sample coverage guarantee of split
        # conformal prediction: coverage is at least q regardless of the error
        # distribution, which matters here because spending residuals are
        # skewed and nothing justifies assuming normality.
        absolute = np.sort(np.abs(np.array(residuals)))
        n = len(absolute)
        k = min(n, int(np.ceil(TARGET_COVERAGE * (n + 1))))
        spread = float(np.clip(absolute[k - 1], 0.05, 1.50))

        # Few months of history means even the conformal quantile rests on few
        # residuals, so widen further where evidence is thin.
        spread *= 1.0 + 0.5 * (1.0 - _evidence(n_months))

        return max(0.0, point * (1.0 - spread)), point * (1.0 + spread)

    # ── Forecaster protocol ──
    def forecast(
        self, history: pd.DataFrame, user_id: str, year: int, month: int
    ) -> Forecast:
        hist = _user_history(history, user_id)
        table = _pivot(hist)
        if table.empty:
            return _insufficient(self.name)

        n_months = len(table)
        mkeys = list(table.index)
        target_mkey = year * 12 + month

        breakdown: dict[str, float] = {}
        for category in table.columns:
            value = self._forecast_category(
                mkeys, table[category].to_numpy(), target_mkey, month
            )
            if value > 0.005:
                breakdown[category] = round(value, 2)

        total = round(float(sum(breakdown.values())), 2)

        if n_months < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=total,
                breakdown=breakdown,
                confidence=0.0,
                risk_flag="insufficient_history",
                method=self.name,
            )

        low, high = (
            self._interval(table, total, n_months)
            if self.intervals
            else (None, None)
        )

        monthly = table.sum(axis=1)
        mean_total = float(monthly.mean())
        cv = float(monthly.std(ddof=1) / mean_total) if mean_total > 0 else 0.0
        confidence = round(_confidence_from_cv(cv) * _evidence(n_months), 4)

        if low is not None and high is not None and total > 0:
            rel_width = (high - low) / total
        else:
            rel_width = 0.0
        risk_flag = "volatile" if rel_width > VOLATILE_REL_WIDTH else None

        return Forecast(
            total=total,
            breakdown=breakdown,
            confidence=confidence,
            low=None if low is None else round(low, 2),
            high=None if high is None else round(high, 2),
            risk_flag=risk_flag,
            method=self.name,
        )
