"""
ExtraTreesForecaster: the fitted model behind the stateless protocol.

The project's anti-leakage claim is that a forecaster is a function of the
history it is handed and cannot see the month it predicts. A fitted model has
seen its training months, so these tests hold it to the explicit form of that
claim: it refuses any target month it was trained on, it loads only the
artefact its manifest describes with the features it was fitted on, and it
keeps no state between calls.

Runs on the committed data/public/ slice and the committed artefact, so it
runs in CI. Synthetic data.
"""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

import app.features as features
from app.data import _adapt
from app.forecaster import (
    SHIPPED_ARTEFACT,
    BudgetBlendForecaster,
    ExtraTreesForecaster,
    Forecast,
    ModelArtefactError,
    TrainingPeriodError,
)
from app.synthetic import monthly_totals

PUBLIC = Path(__file__).resolve().parent.parent / "data" / "public"
MANIFEST = SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".manifest.json")
CALIBRATION = SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".calibration.json")


@pytest.fixture(scope="module")
def public():
    """`(monthly, budgets)` from the committed slice, read explicitly so a
    full extract in data/ does not change what is tested."""
    raw = pd.read_csv(PUBLIC / "spending_records.csv")
    monthly = monthly_totals(_adapt(raw, "data/public/spending_records.csv"))
    budgets = pd.read_csv(PUBLIC / "budget_categories.csv").rename(
        columns={"allocated_kes": "allocated"}
    )
    return monthly, budgets


@pytest.fixture(scope="module")
def forecaster(public):
    return ExtraTreesForecaster(budgets=public[1])


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


# ── the leakage guard ──


@pytest.mark.parametrize("year, month", [(2026, 6), (2026, 1), (2025, 7), (2024, 12)])
def test_refuses_a_target_month_inside_its_training_period(forecaster, public, year, month):
    assert forecaster.trained_through == "2026-06" == _manifest()["trained_through"]
    with pytest.raises(TrainingPeriodError, match="2026-06"):
        forecaster.forecast(public[0], "h001", year, month)


def test_answers_the_first_month_after_its_training_period(forecaster, public):
    fc = forecaster.forecast(public[0], "h001", 2026, 7)
    assert isinstance(fc, Forecast)
    assert fc.total > 0 and fc.breakdown


# ── the load-time guards ──


def test_rejects_a_mismatched_feature_list(tmp_path):
    reordered = _manifest()
    reordered["features"][0], reordered["features"][1] = (
        reordered["features"][1], reordered["features"][0],
    )
    shortened = _manifest()
    shortened["features"] = shortened["features"][:-1]

    for broken in (reordered, shortened):
        manifest = tmp_path / "broken.manifest.json"
        manifest.write_text(json.dumps(broken))
        with pytest.raises(ModelArtefactError, match="feature list"):
            ExtraTreesForecaster(SHIPPED_ARTEFACT, manifest=manifest)


def test_rejects_an_artefact_whose_sha256_does_not_match_the_manifest(tmp_path):
    artefact = tmp_path / SHIPPED_ARTEFACT.name
    shutil.copy(SHIPPED_ARTEFACT, artefact)
    shutil.copy(MANIFEST, tmp_path / MANIFEST.name)
    shutil.copy(CALIBRATION, tmp_path / CALIBRATION.name)
    ExtraTreesForecaster(artefact)  # the untouched copy loads

    with artefact.open("ab") as f:
        f.write(b"\0")
    with pytest.raises(ModelArtefactError, match="SHA-256"):
        ExtraTreesForecaster(artefact)


# ── the interval and the confidence ──


def test_serves_the_offsets_its_holdout_verification_passed(forecaster, public):
    """The 80% offsets under-covered the 60 deployed households (78.9%), so
    the fallback fixed before the holdout was read is what is served."""
    calibration = json.loads(CALIBRATION.read_text())
    attempts = calibration["verification"]["attempts"]
    assert [a["passed"] for a in attempts] == [False, True]
    served = calibration["fallback_if_undercovered"]
    assert forecaster.interval_nominal == served["nominal"] == 0.90

    assert calibration["scale"] == "relative"
    for user in ("h001", "h017", "h060"):
        fc = forecaster.forecast(public[0], user, 2026, 10)
        assert 0 <= fc.low <= fc.total <= fc.high
        assert fc.low == pytest.approx(fc.total * (1 + served["lower"]), abs=0.01)
        assert fc.high == pytest.approx(fc.total * (1 + served["upper"]), abs=0.01)


def test_refuses_to_serve_an_interval_that_failed_both_verifications(tmp_path):
    failed = json.loads(CALIBRATION.read_text())
    for attempt in failed["verification"]["attempts"]:
        attempt["passed"] = False
    calibration = tmp_path / "failed.calibration.json"
    calibration.write_text(json.dumps(failed))
    with pytest.raises(ModelArtefactError, match="failed its holdout verification"):
        ExtraTreesForecaster(calibration=calibration)


def test_refuses_a_calibration_made_for_another_artefact(tmp_path):
    other = json.loads(CALIBRATION.read_text())
    other["artefact_sha256"] = "0" * 64
    calibration = tmp_path / "other.calibration.json"
    calibration.write_text(json.dumps(other))
    with pytest.raises(ModelArtefactError, match="different artefact"):
        ExtraTreesForecaster(calibration=calibration)
    with pytest.raises(ModelArtefactError, match="missing"):
        ExtraTreesForecaster(calibration=tmp_path / "absent.calibration.json")


def test_confidence_is_the_households_steadiness_as_for_the_blend(forecaster, public):
    """Same formula, same history, same number: it describes the household."""
    monthly, budgets = public
    before = monthly[monthly["year"] * 12 + monthly["month"] < 2026 * 12 + 10]
    blend = BudgetBlendForecaster(budgets)
    for user in ("h001", "h017", "h060"):
        assert forecaster.forecast(before, user, 2026, 10).confidence == (
            blend.forecast(before, user, 2026, 10).confidence
        )


# ── statelessness ──


def test_is_stateless(forecaster, public):
    monthly, budgets = public
    before = monthly.copy()

    first = forecaster.forecast(monthly, "h001", 2026, 10)
    second = forecaster.forecast(monthly, "h001", 2026, 10)
    assert first == second

    # Other households in between must not change the answer.
    forecaster.forecast(monthly, "h002", 2026, 10)
    forecaster.forecast(monthly, "h017", 2026, 11)
    forecaster.forecast(monthly, "h060", 2026, 8)
    after = forecaster.forecast(monthly, "h001", 2026, 10)
    assert after == first

    # Nor may anything carried over from construction: a fresh instance agrees.
    assert ExtraTreesForecaster(budgets=budgets).forecast(monthly, "h001", 2026, 10) == first

    # And the history it was handed is not modified.
    pd.testing.assert_frame_equal(monthly, before)


def test_ignores_history_at_or_after_the_target_month(forecaster, public):
    monthly, _ = public
    keys = monthly["year"] * 12 + monthly["month"]
    strictly_before = monthly[keys < 2026 * 12 + 8]
    with_target_and_later = monthly  # runs to 2026-09

    assert forecaster.forecast(with_target_and_later, "h001", 2026, 8) == (
        forecaster.forecast(strictly_before, "h001", 2026, 8)
    )


# ── one definition of the features ──


def test_training_and_serving_share_one_feature_definition():
    import scripts.build_panel as build_panel

    assert build_panel.FEATURES is features.FEATURES
    assert build_panel.feature_rows is features.feature_rows
    assert len(features.FEATURES) == 31
