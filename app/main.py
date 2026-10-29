"""
U-CS 37 — AI Lifestyle Budgeting & Cost Modeling

  POST /forecast
    in : { "userId": "...", "month": 6, "year": 2026 }
    out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }

Do not change the shape without agreeing it with: U-CS 38 (spend-advisor), U-CS 43 (dependant-costs), U-CS 46 (ops-metrics)
"""
import os
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import BudgetResponse, Request, Response
from app.service import budget_for, handle

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
    """Hosting platforms call this to check the service is alive."""
    return {"status": "ok"}


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


# Serve the demo console at the root, so the deployed URL shows something a
# person can use rather than a bare 404. Mounted last so it cannot shadow
# /forecast, /health or /docs, and skipped when the directory is absent so the
# service still starts from a partial checkout.
if DEMO_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DEMO_DIR, html=True), name="demo")
