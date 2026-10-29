"""
GET /budget (FR-09): the household's declared budget per category, for the
Flutter client's budget comparison (FR-13).

Expectations are read from app.data.load_budgets() rather than hard-coded, so
the suite holds against both the full extract on the developer's machine and
the committed data/public/ slice a clean clone sees.
"""

from fastapi.testclient import TestClient

from app.data import load_budgets
from app.main import app

client = TestClient(app)


def a_budgeted_user() -> str:
    budgets = load_budgets()
    assert not budgets.empty, "no budget file found in data/ or data/public/"
    return str(budgets["user_id"].iloc[0])


def test_budget_returns_every_declared_category():
    user = a_budgeted_user()
    budgets = load_budgets()
    expected = budgets[budgets["user_id"] == user].set_index("category")["allocated"]

    res = client.get("/budget", params={"userId": user})
    assert res.status_code == 200, res.text
    payload = res.json()

    assert payload["userId"] == user
    assert set(payload["allocated"]) == set(expected.index)
    for category, amount in payload["allocated"].items():
        assert isinstance(amount, (int, float))
        assert abs(amount - expected[category]) < 0.01, category


def test_budget_is_declared_synthetic():
    payload = client.get("/budget", params={"userId": a_budgeted_user()}).json()
    assert payload["isSynthetic"] is True


def test_unknown_household_is_an_empty_budget_not_an_error():
    """The documented choice: 200 with nothing to show, as POST /forecast does."""
    res = client.get("/budget", params={"userId": "nobody-has-this-id"})
    assert res.status_code == 200
    assert res.json() == {
        "userId": "nobody-has-this-id",
        "allocated": {},
        "isSynthetic": True,
    }


def test_missing_or_empty_user_id_is_rejected():
    assert client.get("/budget").status_code == 422
    assert client.get("/budget", params={"userId": ""}).status_code == 422
