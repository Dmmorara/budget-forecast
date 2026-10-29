"""
CORS (IR-02): the Flutter web build runs on a different domain from the
service, so the browser sends a preflight before every JSON POST and refuses
the real response unless the preflight names its origin.

The allowed origins are read from CORS_ALLOWED_ORIGINS when the app is built,
so each test rebuilds app.main under the environment it needs and restores the
default afterwards.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

import app.main

FLUTTER_WEB = "https://budget-forecast-web.example.com"


@pytest.fixture
def client_with_origins(monkeypatch):
    def build(value: str | None) -> TestClient:
        if value is None:
            monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("CORS_ALLOWED_ORIGINS", value)
        return TestClient(importlib.reload(app.main).app)

    yield build
    monkeypatch.undo()
    importlib.reload(app.main)


def preflight(client: TestClient, origin: str):
    return client.options(
        "/forecast",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_preflight_from_the_configured_origin_is_allowed(client_with_origins):
    client = client_with_origins(f"{FLUTTER_WEB}/, http://localhost:5000")
    res = preflight(client, FLUTTER_WEB)

    assert res.status_code == 200, res.text
    assert res.headers["access-control-allow-origin"] == FLUTTER_WEB
    assert "POST" in res.headers["access-control-allow-methods"]
    assert "content-type" in res.headers["access-control-allow-headers"].lower()
    # No credentials are shared, so the browser must not be told otherwise.
    assert "access-control-allow-credentials" not in res.headers


def test_preflight_from_another_origin_is_refused(client_with_origins):
    client = client_with_origins(FLUTTER_WEB)
    res = preflight(client, "https://somewhere-else.example.com")

    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_no_cross_origin_access_by_default(client_with_origins):
    """Unset must mean closed, not open to every site."""
    client = client_with_origins(None)
    res = preflight(client, FLUTTER_WEB)

    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_the_real_response_carries_the_header(client_with_origins):
    """The preflight alone is not enough: the POST itself must be readable."""
    client = client_with_origins(FLUTTER_WEB)
    res = client.post(
        "/forecast",
        json={"userId": "nobody-has-this-id", "month": 6, "year": 2026},
        headers={"Origin": FLUTTER_WEB},
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == FLUTTER_WEB
