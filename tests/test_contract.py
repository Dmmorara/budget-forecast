"""
Contract test: the shape other teams rely on. If this breaks, you broke someone else.

The skeleton shipped with `test_endpoint_responds` posting `{}` and asserting
200. That test passed against a stub that returned a hardcoded response and
would have kept passing against a service that ignored its input entirely. Now
that the request fields are required, `{}` is a 422 — so the assertion is
inverted here deliberately, and the real body is tested alongside it.

Downstream consumers: U-CS 38 (spend-advisor), U-CS 43 (dependant-costs),
U-CS 46 (ops-metrics).
"""

from fastapi.testclient import TestClient

from app.data import load_monthly
from app.main import app

client = TestClient(app)


def a_known_user() -> str:
    monthly, _ = load_monthly()
    counts = (
        monthly.assign(k=monthly["year"] * 12 + monthly["month"])
        .groupby("user_id")["k"]
        .nunique()
    )
    # A household with plenty of history, so this test exercises the forecast
    # path rather than the insufficient-history path.
    return str(counts.sort_values().index[-1])


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_empty_body_is_rejected():
    """A forecast for nobody is a bug, not a 200."""
    assert client.post("/forecast", json={}).status_code == 422


def test_month_out_of_range_is_rejected():
    res = client.post(
        "/forecast", json={"userId": "x", "month": 13, "year": 2026}
    )
    assert res.status_code == 422


def test_contract_shape():
    body = {"userId": a_known_user(), "month": 6, "year": 2026}
    res = client.post("/forecast", json=body)
    assert res.status_code == 200, res.text
    payload = res.json()

    # The four frozen fields, by name and by type.
    assert isinstance(payload["estimatedTotal"], (int, float))
    assert isinstance(payload["breakdown"], dict)
    assert isinstance(payload["confidence"], (int, float))
    assert payload["riskFlag"] is None or isinstance(payload["riskFlag"], str)

    assert "method" in payload
    assert isinstance(payload["isSynthetic"], bool)

    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["estimatedTotal"] >= 0


def test_breakdown_sums_to_total():
    """
    U-CS 38 consumes the breakdown and U-CS 46 charts the total. If they
    disagree, two teams display different numbers for the same household and
    the discrepancy surfaces as a platform bug rather than ours.
    """
    body = {"userId": a_known_user(), "month": 6, "year": 2026}
    payload = client.post("/forecast", json=body).json()
    assert payload["breakdown"], "a household with history should have a breakdown"
    assert abs(sum(payload["breakdown"].values()) - payload["estimatedTotal"]) < 0.5


def test_interval_brackets_the_point_forecast():
    body = {"userId": a_known_user(), "month": 6, "year": 2026}
    payload = client.post("/forecast", json=body).json()
    low, high, point = (
        payload["estimatedTotalLow"],
        payload["estimatedTotalHigh"],
        payload["estimatedTotal"],
    )
    assert low is not None and high is not None
    assert low <= point <= high, (low, point, high)
    assert low >= 0


def test_unknown_user_is_flagged_not_an_error():
    res = client.post(
        "/forecast",
        json={"userId": "nobody-has-this-id", "month": 6, "year": 2026},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["riskFlag"] == "insufficient_history"
    assert payload["estimatedTotal"] == 0
    assert payload["breakdown"] == {}


def test_synthetic_data_is_declared_as_synthetic():
    """
    Project rule: synthetic data is labelled as synthetic, in the code and in
    the report. While no real CSV is present the flag must be True, so that no
    number this service emits can be quoted without the caveat attached.
    """
    _monthly, is_synthetic = load_monthly()
    payload = client.post(
        "/forecast", json={"userId": a_known_user(), "month": 6, "year": 2026}
    ).json()
    assert payload["isSynthetic"] is is_synthetic
