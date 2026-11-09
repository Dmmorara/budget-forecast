"""
The service's choice of forecaster, and that a model file can never cause a
500.

POST /forecast answers with the fitted model when its files load and
validate, and with the blend otherwise, and also, per request, whenever the
model must not answer (app/service.py, ServedForecaster). These tests break the
model files in each way the service has to survive, and check that the
response still satisfies the contract.
"""

import json
import shutil

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.service as service
from app.data import load_monthly
from app.forecaster import SHIPPED_ARTEFACT, BudgetBlendForecaster, ExtraTreesForecaster
from app.main import app
from app.schemas import Request

client = TestClient(app)

MANIFEST = SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".manifest.json")
CALIBRATION = SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".calibration.json")
CONTRACT_FIELDS = (
    "estimatedTotal", "breakdown", "estimatedTotalLow", "estimatedTotalHigh",
    "confidence", "riskFlag",
)


def _copy_model(tmp_path):
    for path in (SHIPPED_ARTEFACT, MANIFEST, CALIBRATION):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path / SHIPPED_ARTEFACT.name


def _known_users(n: int = 5) -> list[str]:
    monthly, _ = load_monthly()
    return sorted(monthly["user_id"].unique())[:n]


# ── falling back at startup ──


def _assert_fell_back(served, reason_fragment: str):
    assert served.model is None
    assert served.name == served.blend.name
    assert reason_fragment in served.fallback_reason


def test_the_shipped_model_is_selected_when_its_files_are_sound():
    served = service.select_forecaster()
    assert served.model is not None and served.fallback_reason is None
    assert served.name == "model:extratrees-v2"


def test_service_falls_back_when_artefact_absent(tmp_path):
    _assert_fell_back(
        service.select_forecaster(artefact=tmp_path / SHIPPED_ARTEFACT.name),
        "FileNotFoundError",
    )


def test_service_falls_back_when_manifest_is_corrupt(tmp_path):
    artefact = _copy_model(tmp_path)
    (tmp_path / MANIFEST.name).write_text('{"sha256": "trunc')
    _assert_fell_back(service.select_forecaster(artefact=artefact), "JSONDecodeError")


def test_service_falls_back_when_sha256_does_not_match(tmp_path):
    artefact = _copy_model(tmp_path)
    with artefact.open("ab") as f:
        f.write(b"\0")
    _assert_fell_back(service.select_forecaster(artefact=artefact), "SHA-256")


def test_service_falls_back_when_the_feature_list_does_not_validate(tmp_path):
    artefact = _copy_model(tmp_path)
    manifest = json.loads(MANIFEST.read_text())
    manifest["features"] = manifest["features"][::-1]
    (tmp_path / MANIFEST.name).write_text(json.dumps(manifest))
    _assert_fell_back(service.select_forecaster(artefact=artefact), "feature list")


def test_fallback_response_still_satisfies_the_contract(tmp_path, monkeypatch):
    fallback = service.select_forecaster(artefact=tmp_path / "absent.joblib")
    monkeypatch.setattr(service, "FORECASTER", fallback)
    import app.main as main
    monkeypatch.setattr(main, "FORECASTER", fallback)

    health = client.get("/health").json()
    assert health["forecaster"] == fallback.blend.name
    assert health["fallbackReason"]

    for user in _known_users():
        res = client.post("/forecast", json={"userId": user, "month": 10, "year": 2026})
        assert res.status_code == 200, res.text
        payload = res.json()
        assert payload["method"] == fallback.blend.name
        for field in CONTRACT_FIELDS:
            assert field in payload
        assert payload["estimatedTotalLow"] <= payload["estimatedTotal"] <= payload["estimatedTotalHigh"]
        assert abs(sum(payload["breakdown"].values()) - payload["estimatedTotal"]) < 0.5


# ── the model path ──


def test_every_contract_field_is_populated_on_the_model_path():
    assert client.get("/health").json() == {
        "status": "ok", "forecaster": "model:extratrees-v2", "fallbackReason": None,
    }
    for user in _known_users(10):
        res = client.post("/forecast", json={"userId": user, "month": 10, "year": 2026})
        assert res.status_code == 200, res.text
        payload = res.json()
        assert payload["method"] == "model:extratrees-v2"
        assert payload["estimatedTotal"] > 0
        assert payload["breakdown"]
        assert payload["estimatedTotalLow"] is not None
        assert payload["estimatedTotalHigh"] is not None
        assert payload["estimatedTotalLow"] <= payload["estimatedTotal"] <= payload["estimatedTotalHigh"]
        assert 0 < payload["confidence"] <= 1
        # riskFlag is populated by being decided: null means "not volatile".
        assert payload["riskFlag"] in (None, "volatile")


def test_confidence_on_the_model_path_is_the_blends_formula():
    monthly, _ = load_monthly()
    for user in _known_users():
        before = monthly[monthly["year"] * 12 + monthly["month"] < 2026 * 12 + 10]
        model = service.FORECASTER.forecast(before, user, 2026, 10)
        blend = service.FORECASTER.blend.forecast(before, user, 2026, 10)
        assert model.method == "model:extratrees-v2"
        assert model.confidence == blend.confidence


# ── what the model must not answer ──


def test_short_history_never_touches_the_model(monkeypatch):
    served = service.FORECASTER

    def must_not_run(*args, **kwargs):
        raise AssertionError("the model was called for a household with too little history")

    monkeypatch.setattr(served.model, "forecast", must_not_run)
    history = pd.DataFrame(
        [("new", 2026, 8, "Groceries", 9_000.0), ("new", 2026, 9, "Groceries", 11_000.0)],
        columns=["user_id", "year", "month", "category", "amount"],
    )
    fc = served.forecast(history, "new", 2026, 10)
    assert fc == served.blend.forecast(history, "new", 2026, 10)
    assert fc.risk_flag == "insufficient_history" and fc.confidence == 0.0


def test_unknown_user_answer_is_the_same_with_or_without_the_model(tmp_path):
    fallback = service.select_forecaster(artefact=tmp_path / "absent.joblib")
    body = Request(userId="nobody-has-this-id", month=10, year=2026)
    assert service.handle(body) == service.handle(body, fallback)
    assert service.handle(body).method == "blend:history0.8_budget0.2 (no history for user)"


def test_a_month_inside_the_training_period_is_answered_by_the_blend():
    user = _known_users(1)[0]
    res = client.post("/forecast", json={"userId": user, "month": 6, "year": 2026})
    assert res.status_code == 200, res.text
    assert res.json()["method"] == "blend:history0.8_budget0.2"


def test_a_model_error_on_a_request_falls_back_rather_than_500(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure inside the model")

    monkeypatch.setattr(service.FORECASTER.model, "forecast", broken)
    user = _known_users(1)[0]
    res = client.post("/forecast", json={"userId": user, "month": 10, "year": 2026})
    assert res.status_code == 200, res.text
    assert res.json()["method"] == "blend:history0.8_budget0.2"
