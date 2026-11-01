"""
SYNTHETIC DATA. Nothing in this module is real.

Every record produced here is generated from the profiles below. It exists so
that the baseline, the evaluation harness and the model can be built and tested
before the staging sandbox is wired up, and so that the forecaster can be
scored against a process whose true parameters are known.

Project rule: synthetic data is labelled as synthetic, in the code and in the
report. `generate()` returns frames whose `is_synthetic` column is True on
every row, and the service sets `isSynthetic` on every response it derives from
them. Real sandbox data must arrive through `app.data`, which sets the flag to
False — the two sources are never concatenated without the flag surviving.

WHY THE GROUND TRUTH MATTERS
----------------------------
`generate()` returns a second frame, `truth`, holding the latent monthly
expectation each (household, month, category) was drawn from before noise was
added. That gives an *irreducible error floor*: no forecaster, however good,
can beat the noise the process itself injects. Without that floor there is no
way to tell a model that has stopped improving from a model that has run out of
signal, and the honest answer to "why is MAE still 900 KES" may well be "because
900 KES of it is not predictable."

THE SHAPE IS A PROVISIONAL GUESS
--------------------------------
The real column names come from the sandbox `spending_records` endpoint, which
has not been read yet. `app.data` owns the mapping from that shape onto the
canonical columns used here; when the real CSVs land, the adapter changes and
this module does not.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

# Canonical internal columns. Both this module and the real-data loader in
# app.data must produce exactly these.
RECORD_COLUMNS = ["user_id", "occurred_on", "category", "amount", "is_synthetic"]

CATEGORIES = ["Rent", "Utilities", "Transport", "Food", "Personal", "Other"]


@dataclass
class FixedObligation:
    """A near-constant charge on a near-constant day. Rent, wifi, a loan."""

    category: str
    amount: float
    day_of_month: int
    jitter_days: int = 2
    amount_sd: float = 0.0
    # Probability the charge is paid at all in a given month. Real obligations
    # are missed; a forecaster that assumes they never are will overshoot.
    reliability: float = 0.98


@dataclass
class HabitualSpend:
    """
    Many small transactions with no fixed payee — the matatu-fare shape.

    Modelled as a per-day rate rather than a monthly total, because the number
    of billable days in a month varies and weekday/weekend behaviour differs.
    This is the half of the problem that a per-payee recurrence detector cannot
    see, and the reason the forecaster needs two components rather than one.
    """

    category: str
    weekday_txns: float          # expected transactions per weekday
    weekend_txns: float          # expected transactions per weekend day
    amount_mean: float
    amount_sd: float


@dataclass
class OccasionalSpend:
    """Low-frequency, high-variance. The part that makes intervals wide."""

    category: str
    per_month: float             # expected number of transactions per month
    amount_mean: float
    amount_sd: float


@dataclass
class Profile:
    name: str
    fixed: list[FixedObligation] = field(default_factory=list)
    habitual: list[HabitualSpend] = field(default_factory=list)
    occasional: list[OccasionalSpend] = field(default_factory=list)
    # Months of history this household has. Short history is not an edge case
    # to be filtered out — it is the commonest state of a new user, and the
    # service has to answer for them too.
    #
    # 30 months rather than 18 so that a December appears more than once. A
    # seasonal effect observed a single time is indistinguishable from a one-off
    # event, and a model that claims to learn seasonality from one observation
    # is overfitting a single month — so the data has to contain at least two
    # before the claim can be tested at all.
    months_history: int = 30


PROFILES: dict[str, Profile] = {
    # Salaried tenant: the easy case. A large fixed obligation dominates the
    # total, so even a weak forecaster scores well on percentage error. Any
    # headline metric averaged over a population of these flatters the model.
    "steady_tenant": Profile(
        name="steady_tenant",
        fixed=[
            FixedObligation("Rent", 18_000, day_of_month=3, jitter_days=2, amount_sd=0),
            FixedObligation("Utilities", 2_500, day_of_month=10, jitter_days=3, amount_sd=120),
        ],
        habitual=[
            HabitualSpend("Transport", weekday_txns=2.0, weekend_txns=0.6, amount_mean=70, amount_sd=20),
            HabitualSpend("Food", weekday_txns=0.9, weekend_txns=1.4, amount_mean=320, amount_sd=140),
        ],
        occasional=[
            OccasionalSpend("Personal", per_month=1.6, amount_mean=1_400, amount_sd=900),
            OccasionalSpend("Other", per_month=1.0, amount_mean=800, amount_sd=700),
        ],
    ),
    # Student: no rent, so there is no large constant to hide behind and the
    # whole forecast rests on habitual spend. This is the profile that actually
    # tests the model.
    "student": Profile(
        name="student",
        fixed=[
            FixedObligation("Utilities", 1_000, day_of_month=12, jitter_days=4, amount_sd=200, reliability=0.9),
        ],
        habitual=[
            HabitualSpend("Transport", weekday_txns=2.4, weekend_txns=1.0, amount_mean=60, amount_sd=25),
            HabitualSpend("Food", weekday_txns=1.3, weekend_txns=1.1, amount_mean=180, amount_sd=90),
        ],
        occasional=[
            OccasionalSpend("Personal", per_month=2.2, amount_mean=600, amount_sd=500),
            OccasionalSpend("Other", per_month=1.4, amount_mean=400, amount_sd=400),
        ],
    ),
    # Volatile: a genuine forecast exists but the interval around it must be
    # wide. If the model reports the same confidence here as for a steady
    # tenant, the confidence number is decoration.
    "volatile": Profile(
        name="volatile",
        fixed=[
            FixedObligation("Rent", 12_000, day_of_month=5, jitter_days=6, amount_sd=1_500, reliability=0.85),
        ],
        habitual=[
            HabitualSpend("Transport", weekday_txns=1.2, weekend_txns=1.6, amount_mean=250, amount_sd=220),
            HabitualSpend("Food", weekday_txns=0.7, weekend_txns=1.0, amount_mean=500, amount_sd=450),
        ],
        occasional=[
            OccasionalSpend("Other", per_month=2.5, amount_mean=4_000, amount_sd=4_000),
            OccasionalSpend("Personal", per_month=1.0, amount_mean=2_000, amount_sd=2_500),
        ],
    ),
    # Two months of history. Must trigger `insufficient_history` rather than a
    # confident number.
    "new_user": Profile(
        name="new_user",
        months_history=2,
        habitual=[
            HabitualSpend("Transport", weekday_txns=2.0, weekend_txns=0.5, amount_mean=65, amount_sd=20),
            HabitualSpend("Food", weekday_txns=1.0, weekend_txns=1.2, amount_mean=250, amount_sd=120),
        ],
        occasional=[
            OccasionalSpend("Personal", per_month=1.0, amount_mean=900, amount_sd=700),
        ],
    ),
}

# ─────────────────── non-stationarity ───────────────────
#
# A first version of this generator drew every household from fixed
# parameters. The 6-month trailing median then scored 10.16% MAPE against an
# irreducible floor of 10.20% — it had saturated the data completely, because a
# trailing median is the optimal estimator of a stationary process. The test was
# unwinnable by construction, and a model evaluated on it would have looked
# worthless for reasons that had nothing to do with the model.
#
# Real household spend is not stationary. The three sources of movement below
# are the ones a trailing window structurally cannot track, and they are what
# gives a forecaster something real to earn:
#
#   seasonality  repeats annually, so a 3- or 6-month window never sees the
#                December spike coming — it only learns about it in January,
#                by which time the information is worthless.
#   drift        compounds, so any backward-looking average is biased low for
#                as long as prices keep rising. Half the window length, on
#                average.
#   step changes a rent escalation or a move shifts the level discontinuously.
#                A trailing median lags a step by roughly half its window and
#                is actively wrong for every month in between.

# Multiplicative seasonal factors by calendar month (1-12). Shaped on the
# Kenyan calendar: a heavy December, a tight January after it, and travel
# around April and August school holidays. Rent and utilities do not move.
SEASONALITY: dict[str, dict[int, float]] = {
    "Food":      {12: 1.35, 1: 0.95, 4: 1.08, 8: 1.05},
    "Personal":  {12: 1.50, 1: 0.70, 4: 1.10},
    "Transport": {12: 1.20, 1: 1.05, 4: 1.12, 8: 1.12},
    "Other":     {12: 1.40, 1: 1.20, 9: 1.15},
}

# Compounding monthly drift. Transport leads because matatu fares track fuel
# prices closely and adjust fast; rent is handled separately as a step.
MONTHLY_DRIFT: dict[str, float] = {
    "Transport": 0.008,
    "Food": 0.005,
    "Personal": 0.003,
    "Other": 0.003,
    "Utilities": 0.002,
    "Rent": 0.0,
}

# Rent rises once a year, on the household's own anniversary month, as a step.
RENT_ESCALATION = 0.08

# Share of households that move or change commute partway through the history.
# The step is large and its timing is unknown to the forecaster, which is the
# realistic case: the service finds out a household's circumstances changed by
# watching the spend change.
MOVE_PROBABILITY = 0.25


@dataclass
class UserPlan:
    """Per-household non-stationarity, fixed once so it is reproducible."""

    anniversary_month: int          # calendar month rent escalates
    move_at: int | None = None      # index into the household's month sequence
    move_rent_factor: float = 1.0
    move_habitual_factor: float = 1.0


def _user_plan(rng: np.random.Generator, profile: Profile, n_months: int) -> UserPlan:
    anniversary = int(rng.integers(1, 13))
    move_at = None
    rent_factor = 1.0
    habitual_factor = 1.0
    # Only households with enough history for a step to be visible on both
    # sides of it. A move in month 1 is just a different household.
    if n_months >= 8 and rng.random() < MOVE_PROBABILITY:
        move_at = int(rng.integers(4, n_months - 2))
        rent_factor = float(rng.uniform(0.75, 1.35))
        habitual_factor = float(rng.uniform(0.60, 1.50))
    return UserPlan(anniversary, move_at, rent_factor, habitual_factor)


def _scale(
    category: str,
    calendar_month: int,
    t: int,
    plan: UserPlan,
    is_fixed: bool,
) -> float:
    """
    Multiplier on a category's amount for one household-month.

    `t` is months elapsed since the start of this household's history, so drift
    compounds forward and the forecaster sees a level that keeps moving.
    """
    factor = SEASONALITY.get(category, {}).get(calendar_month, 1.0)
    factor *= (1.0 + MONTHLY_DRIFT.get(category, 0.0)) ** t

    if category == "Rent":
        # One step per completed year, on the anniversary month.
        years_elapsed = (t + (12 - plan.anniversary_month)) // 12
        factor *= (1.0 + RENT_ESCALATION) ** years_elapsed

    if plan.move_at is not None and t >= plan.move_at:
        factor *= plan.move_rent_factor if is_fixed else plan.move_habitual_factor

    return factor


# Default population mix. Deliberately not uniform: the mix decides what the
# headline metric means, so it is stated here rather than left implicit.
DEFAULT_MIX = {
    "steady_tenant": 10,
    "student": 10,
    "volatile": 5,
    "new_user": 3,
}

# The last month of the population behind every REPORTED synthetic figure:
# BASELINE.md, MODEL.md, and the tests that assert their numbers.
#
# Pinned because generate() defaults to the month before today, so an unpinned
# population moves every calendar month: different months of history, a
# different seasonal phase, different held-out months. A reported figure that
# depends on the date it was run is not reproducible, and NFR-05 requires every
# reported figure to be. BASELINE.md was measured when that default resolved
# to 30 September 2026; run unpinned on 1 November, the same script gave MAE
# 3520.2 instead of 5137.9, and the single-population seasonality check flipped
# sign. Pinning restores both exactly.
#
# The default itself is left alone for interactive use, and app/data.py's
# fallback keeps it: that is live behaviour, where "up to last month" is right.
REFERENCE_LAST_MONTH = date(2026, 9, 30)


def _month_days(year: int, month: int) -> list[date]:
    n = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, n + 1)]


def _months_ending(last: date, count: int) -> list[tuple[int, int]]:
    """The `count` (year, month) pairs ending at and including `last`."""
    out: list[tuple[int, int]] = []
    y, m = last.year, last.month
    for _ in range(count):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _emit_fixed(
    rng: np.random.Generator,
    ob: FixedObligation,
    year: int,
    month: int,
    scale: float = 1.0,
) -> tuple[list[tuple[date, float]], float]:
    """Returns (transactions, latent monthly expectation)."""
    amount_now = ob.amount * scale
    expectation = amount_now * ob.reliability
    if rng.random() > ob.reliability:
        return [], expectation
    n_days = calendar.monthrange(year, month)[1]
    day = int(np.clip(ob.day_of_month + rng.integers(-ob.jitter_days, ob.jitter_days + 1), 1, n_days))
    amount = (
        amount_now
        if ob.amount_sd == 0
        else float(rng.normal(amount_now, ob.amount_sd * scale))
    )
    return [(date(year, month, day), max(0.0, round(amount, 2)))], expectation


def _emit_habitual(
    rng: np.random.Generator,
    hb: HabitualSpend,
    year: int,
    month: int,
    scale: float = 1.0,
) -> tuple[list[tuple[date, float]], float]:
    txns: list[tuple[date, float]] = []
    expectation = 0.0
    mean_now = hb.amount_mean * scale
    sd_now = hb.amount_sd * scale
    for d in _month_days(year, month):
        rate = hb.weekend_txns if d.weekday() >= 5 else hb.weekday_txns
        expectation += rate * mean_now
        for _ in range(int(rng.poisson(rate))):
            amount = max(5.0, float(rng.normal(mean_now, sd_now)))
            txns.append((d, round(amount, 2)))
    return txns, expectation


def _emit_occasional(
    rng: np.random.Generator,
    oc: OccasionalSpend,
    year: int,
    month: int,
    scale: float = 1.0,
) -> tuple[list[tuple[date, float]], float]:
    txns: list[tuple[date, float]] = []
    n_days = calendar.monthrange(year, month)[1]
    mean_now = oc.amount_mean * scale
    for _ in range(int(rng.poisson(oc.per_month))):
        day = int(rng.integers(1, n_days + 1))
        amount = max(10.0, float(rng.normal(mean_now, oc.amount_sd * scale)))
        txns.append((date(year, month, day), round(amount, 2)))
    return txns, oc.per_month * mean_now


def generate(
    seed: int = 37,
    mix: dict[str, int] | None = None,
    last_month: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build a synthetic spending population.

    Returns `(records, truth)`:

      records  one row per transaction, columns RECORD_COLUMNS
      truth    one row per (user_id, year, month, category) with `expected`,
               the latent monthly mean the records were drawn from, and
               `actual`, what was in fact drawn. The gap between the two is
               irreducible noise and bounds how well any forecaster can do.

    `last_month` is the most recent month with data; history runs backwards from
    it. It defaults to the month before today, because the current month is
    always partial and a partial month silently drags every trailing average
    downwards.
    """
    rng = np.random.default_rng(seed)
    mix = dict(mix or DEFAULT_MIX)

    if last_month is None:
        today = date.today()
        first_of_this = date(today.year, today.month, 1)
        last_month = first_of_this - timedelta(days=1)

    rows: list[tuple] = []
    truth_rows: list[tuple] = []

    for profile_name, count in mix.items():
        profile = PROFILES[profile_name]
        for i in range(count):
            user_id = f"{profile_name}-{i + 1:02d}"
            plan = _user_plan(rng, profile, profile.months_history)

            for t, (year, month) in enumerate(
                _months_ending(last_month, profile.months_history)
            ):
                per_category_expected: dict[str, float] = {}
                per_category_actual: dict[str, float] = {}

                groups: list[tuple[str, list]] = [
                    ("fixed", profile.fixed),
                    ("habitual", profile.habitual),
                    ("occasional", profile.occasional),
                ]
                for kind, items in groups:
                    for item in items:
                        scale = _scale(
                            item.category, month, t, plan, is_fixed=(kind == "fixed")
                        )
                        if kind == "fixed":
                            txns, expected = _emit_fixed(rng, item, year, month, scale)
                        elif kind == "habitual":
                            txns, expected = _emit_habitual(rng, item, year, month, scale)
                        else:
                            txns, expected = _emit_occasional(rng, item, year, month, scale)

                        per_category_expected[item.category] = (
                            per_category_expected.get(item.category, 0.0) + expected
                        )
                        for when, amount in txns:
                            rows.append((user_id, when, item.category, amount, True))
                            per_category_actual[item.category] = (
                                per_category_actual.get(item.category, 0.0) + amount
                            )

                for category, expected in per_category_expected.items():
                    truth_rows.append(
                        (
                            user_id,
                            year,
                            month,
                            category,
                            round(expected, 2),
                            round(per_category_actual.get(category, 0.0), 2),
                            profile_name,
                        )
                    )

    records = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    records["occurred_on"] = pd.to_datetime(records["occurred_on"])
    records = records.sort_values(["user_id", "occurred_on"]).reset_index(drop=True)

    truth = pd.DataFrame(
        truth_rows,
        columns=["user_id", "year", "month", "category", "expected", "actual", "profile"],
    )
    return records, truth


def monthly_totals(records: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse transactions to (user_id, year, month, category, amount).

    The forecast is a monthly quantity, so this is the grain everything
    downstream — baseline, evaluation, model — actually works on. Shared by the
    synthetic and real paths so neither can aggregate differently from the
    other.
    """
    df = records.copy()
    df["occurred_on"] = pd.to_datetime(df["occurred_on"])
    df["year"] = df["occurred_on"].dt.year
    df["month"] = df["occurred_on"].dt.month
    out = (
        df.groupby(["user_id", "year", "month", "category"], as_index=False)["amount"]
        .sum()
        .sort_values(["user_id", "year", "month", "category"])
        .reset_index(drop=True)
    )
    out["amount"] = out["amount"].round(2)
    return out
