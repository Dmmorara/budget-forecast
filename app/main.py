"""
U-CS 37 — AI Lifestyle Budgeting & Cost Modeling

  POST /forecast
    in : { "userId": "...", "month": 6, "year": 2026 }
    out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }

Do not change the shape without agreeing it with: U-CS 38 (spend-advisor), U-CS 43 (dependant-costs), U-CS 46 (ops-metrics)
"""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.demo import DemoError
from app.schemas import (
    BudgetResponse,
    DemoBudget,
    DemoCategoriesResponse,
    DemoHouseholdResponse,
    DemoLogin,
    DemoSimulate,
    DemoSpend,
    InsightsResponse,
    Request,
    Response,
)
from app.service import (
    DEMO,
    FORECASTER,
    budget_for,
    demo_categories,
    demo_response,
    demo_set_budget,
    handle,
    insights,
)

app = FastAPI(title="U-CS 37 — budget-forecast", version="0.1.0")

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def allowed_origins() -> list[str]:
    """
    Browser origins allowed to call this service cross-origin (IR-02).

    Read from CORS_ALLOWED_ORIGINS as a comma-separated list, for example
    "https://budget-forecast-web.onrender.com,http://localhost:5000". The
    Flutter web build runs on a different domain from the service, and the
    browser refuses to hand it a response unless that origin is named here.

    Unset or empty means NO cross-origin access. That is the safe default: a
    deployment nobody configured stays closed rather than open to every site,
    and the failure is a visible CORS error in the browser console rather than
    a silent exposure. Server-to-server callers (the platform, U-CS 38, 43 and
    46) and the demo console served from this same origin are unaffected —
    CORS is enforced by browsers only.

    A trailing slash is stripped, because a browser's Origin header never has
    one and "https://x.onrender.com/" would otherwise never match.
    """
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


# No credentials: the service has no cookies or auth to share, and leaving
# allow_credentials off means a misconfigured "*" can never be combined with
# credentialed requests. Content-Type is the one header the client sends that
# triggers a preflight, since a JSON body is not a CORS "simple" request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    """
    Hosting platforms call this to check the service is alive.

    `forecaster` (additive) names what POST /forecast is answering with: the
    fitted model, or the blend when the model did not load, in which case
    `fallbackReason` says why. A deployment whose model file went missing
    still answers every request, so this is where that shows.
    """
    return {
        "status": "ok",
        "forecaster": FORECASTER.name,
        "fallbackReason": FORECASTER.fallback_reason,
    }


@app.post("/forecast", response_model=Response)
def endpoint(body: Request) -> Response:
    return handle(body)


@app.get("/budget", response_model=BudgetResponse)
def budget(
    userId: str = Query(min_length=1, description="Household/user identifier"),
) -> BudgetResponse:
    """
    The household's declared budget per category (FR-09).

    An unknown household is a 200 with an empty `allocated`, not a 404: there
    is simply no budget to show. A missing or empty userId is a 422.
    """
    return budget_for(userId)


@app.get("/insights", response_model=InsightsResponse)
def insights_endpoint(
    userId: str = Query(min_length=1, description="Household/user identifier"),
    month: int = Query(ge=1, le=12, description="The month the insights lead up to, 1-12"),
    year: int = Query(ge=2000, le=2100, description="Its year"),
) -> InsightsResponse:
    """
    Usual spend, spending calendar and discretionary trend for the months
    before `month`/`year` (additive; POST /forecast is unchanged).

    Fewer than three months of history, or an unknown household, is a 200 with
    the three sections null, as POST /forecast answers insufficient_history.
    """
    return insights(userId, month, year)


# ── demo households, for presentations (app/demo.py) ──
#
# Additive. Every route is POST or GET, so the CORS configuration above needs
# no new method.


def _demo(action):
    try:
        return demo_response(action())
    except DemoError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc


@app.get("/demo/categories", response_model=DemoCategoriesResponse)
def demo_categories_endpoint() -> DemoCategoriesResponse:
    """Categories a demo budget can use, with a typical sandbox budget for each."""
    return demo_categories()


@app.post("/demo/signup", response_model=DemoHouseholdResponse)
def demo_signup(body: DemoLogin) -> DemoHouseholdResponse:
    """A new demo household. 409 if the name is taken."""
    return _demo(lambda: DEMO.signup(body.name, body.pin))


@app.post("/demo/login", response_model=DemoHouseholdResponse)
def demo_login(body: DemoLogin) -> DemoHouseholdResponse:
    """An existing demo household. 401 if the name and PIN do not match."""
    return _demo(lambda: DEMO.login(body.name, body.pin))


@app.get("/demo/households/{userId}", response_model=DemoHouseholdResponse)
def demo_household(userId: str) -> DemoHouseholdResponse:
    return _demo(lambda: DEMO.get(userId))


@app.post("/demo/households/{userId}/budget", response_model=DemoHouseholdResponse)
def demo_budget(userId: str, body: DemoBudget) -> DemoHouseholdResponse:
    """Replace the household's budget."""
    return _demo(lambda: demo_set_budget(userId, body.allocated))


@app.post("/demo/households/{userId}/spend", response_model=DemoHouseholdResponse)
def demo_spend(userId: str, body: DemoSpend) -> DemoHouseholdResponse:
    """One transaction in the month in progress."""
    return _demo(lambda: DEMO.add_spend(userId, body.category, body.amount, body.day))


@app.post("/demo/households/{userId}/simulate", response_model=DemoHouseholdResponse)
def demo_simulate(userId: str, body: DemoSimulate) -> DemoHouseholdResponse:
    """Fill in the month in progress from the budget and move to the next, `months` times."""
    return _demo(lambda: DEMO.simulate(userId, body.months))


# Serve the demo console at the root, so the deployed URL shows something a
# person can use rather than a bare 404. Mounted last so it cannot shadow
# /forecast, /health or /docs, and skipped when the directory is absent so the
# service still starts from a partial checkout.
if DEMO_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DEMO_DIR, html=True), name="demo")
