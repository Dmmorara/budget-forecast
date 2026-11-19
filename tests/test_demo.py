"""
Demo households (app/demo.py): sign up, declare a budget, build up history,
and get forecast through the same endpoints as a sandbox household.
"""

import secrets

from fastapi.testclient import TestClient

from app.data import load_monthly
from app.demo import DemoStore, simulate_month
from app.main import app
from app.service import DEMO

client = TestClient(app)

BUDGET = {"Rent": 20000.0, "Groceries": 12000.0, "Transport": 6000.0, "Gambling": 0.0}


def signup(pin: str = "1234") -> dict:
    # A fresh name per test: the store is shared by the whole session.
    res = client.post("/demo/signup", json={"name": f"Test {secrets.token_hex(4)}", "pin": pin})
    assert res.status_code == 200, res.text
    return res.json()


def budgeted() -> dict:
    household = signup()
    res = client.post(f"/demo/households/{household['userId']}/budget", json={"allocated": BUDGET})
    assert res.status_code == 200, res.text
    return res.json()


def forecast(household: dict) -> dict:
    res = client.post("/forecast", json={
        "userId": household["userId"], "month": household["month"], "year": household["year"],
    })
    assert res.status_code == 200, res.text
    return res.json()


def simulate(household: dict, months: int = 1) -> dict:
    res = client.post(f"/demo/households/{household['userId']}/simulate", json={"months": months})
    assert res.status_code == 200, res.text
    return res.json()


# ── sign up and log in ──


def test_signup_starts_the_month_after_the_sandbox_data_ends():
    household = signup()
    monthly, _ = load_monthly()
    last = int((monthly["year"] * 12 + monthly["month"]).max())
    assert household["userId"].startswith("demo-")
    assert household["year"] * 12 + household["month"] == last + 1
    assert household["historyMonths"] == 0
    assert household["isSynthetic"] is True


def test_login_finds_the_household_whatever_the_case_of_the_name():
    household = signup(pin="4321")
    res = client.post("/demo/login", json={"name": household["name"].upper(), "pin": "4321"})
    assert res.status_code == 200
    assert res.json()["userId"] == household["userId"]


def test_a_wrong_pin_and_an_unknown_name_get_the_same_answer():
    household = signup(pin="4321")
    wrong_pin = client.post("/demo/login", json={"name": household["name"], "pin": "0000"})
    unknown = client.post("/demo/login", json={"name": "nobody at all", "pin": "4321"})
    assert wrong_pin.status_code == unknown.status_code == 401
    assert wrong_pin.json() == unknown.json()


def test_a_name_can_only_be_signed_up_once():
    household = signup()
    res = client.post("/demo/signup", json={"name": household["name"], "pin": "1111"})
    assert res.status_code == 409


def test_the_pin_must_be_digits():
    for pin in ("12", "abcd", "123456789"):
        res = client.post("/demo/signup", json={"name": "Someone", "pin": pin})
        assert res.status_code == 422, pin


def test_the_pin_is_not_kept_in_the_clear():
    household = signup(pin="2468")
    stored = DEMO.get(household["userId"])
    assert b"2468" not in stored.pin_hash


def test_an_unknown_demo_household_is_a_404():
    assert client.get("/demo/households/demo-nobody").status_code == 404
    res = client.post("/demo/households/demo-nobody/simulate", json={"months": 1})
    assert res.status_code == 404


# ── budget ──


def test_the_budget_is_served_by_get_budget():
    household = budgeted()
    res = client.get("/budget", params={"userId": household["userId"]})
    assert res.json() == {"userId": household["userId"], "allocated": BUDGET, "isSynthetic": True}


def test_a_negative_budget_is_rejected():
    household = signup()
    res = client.post(
        f"/demo/households/{household['userId']}/budget", json={"allocated": {"Rent": -1}}
    )
    assert res.status_code == 422


def test_simulating_needs_a_budget():
    household = signup()
    res = client.post(f"/demo/households/{household['userId']}/simulate", json={"months": 1})
    assert res.status_code == 409


def test_categories_offer_a_typical_budget_for_each_commonly_budgeted_one():
    payload = client.get("/demo/categories").json()
    assert "Rent" in payload["categories"]
    assert set(payload["typical"]) <= set(payload["categories"])
    assert all(v > 0 for v in payload["typical"].values())


# ── building history ──


def test_a_new_household_has_insufficient_history():
    result = forecast(budgeted())
    assert result["riskFlag"] == "insufficient_history"
    assert result["isSynthetic"] is True


def test_the_forecast_appears_once_three_months_are_simulated():
    household = budgeted()
    for expected_months in (1, 2):
        household = simulate(household)
        assert household["historyMonths"] == expected_months
        assert forecast(household)["riskFlag"] == "insufficient_history"

    household = simulate(household)
    result = forecast(household)
    assert result["riskFlag"] != "insufficient_history"
    assert result["confidence"] > 0
    assert result["estimatedTotal"] > 0
    assert result["estimatedTotalLow"] <= result["estimatedTotal"] <= result["estimatedTotalHigh"]


def test_the_forecast_is_in_the_neighbourhood_of_the_budget():
    household = simulate(budgeted(), months=6)
    total = forecast(household)["estimatedTotal"]
    declared = sum(BUDGET.values())
    assert 0.6 * declared < total < 1.4 * declared


def test_simulating_advances_the_month_across_a_year_end():
    household = simulate(budgeted(), months=4)
    start = signup()
    start_key = start["year"] * 12 + start["month"]
    assert household["year"] * 12 + household["month"] == start_key + 4


def test_a_spend_lands_in_the_month_in_progress_and_survives_the_simulation():
    household = budgeted()
    user = household["userId"]
    res = client.post(f"/demo/households/{user}/spend", json={"category": "Electronics Upgrade", "amount": 45000})
    assert res.json()["spentThisMonth"] == {"Electronics Upgrade": 45000.0}

    simulate(household)
    monthly = DEMO.monthly(user)
    month = monthly[(monthly["year"] == household["year"]) & (monthly["month"] == household["month"])]
    assert month.set_index("category").loc["Electronics Upgrade", "amount"] == 45000.0


def test_insights_answer_for_a_demo_household():
    household = simulate(budgeted(), months=4)
    res = client.get("/insights", params={
        "userId": household["userId"], "month": household["month"], "year": household["year"],
    })
    payload = res.json()
    assert payload["historyMonths"] == 4
    assert payload["usual"] is not None
    assert payload["isSynthetic"] is True


def test_sandbox_households_are_unaffected():
    monthly, _ = load_monthly()
    user = str(monthly["user_id"].iloc[0])
    before = client.post("/forecast", json={"userId": user, "month": 10, "year": 2026}).json()
    simulate(budgeted(), months=3)
    after = client.post("/forecast", json={"userId": user, "month": 10, "year": 2026}).json()
    assert before == after


# ── the generator ──


def test_simulated_months_replay_identically():
    store = DemoStore((2026, 10))
    household = store.signup("Replay", "1234")
    store.set_budget(household.user_id, BUDGET)
    assert simulate_month(household, 2026, 10) == simulate_month(household, 2026, 10)


def test_a_zero_budget_category_is_never_spent_on():
    store = DemoStore((2026, 10))
    household = store.signup("Zero", "1234")
    store.set_budget(household.user_id, BUDGET)
    records = simulate_month(household, 2026, 10)
    assert "Gambling" not in {r["category"] for r in records}
    assert {r["category"] for r in records} == {"Rent", "Groceries", "Transport"}
