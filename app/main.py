"""
U-CS 37 — AI Lifestyle Budgeting & Cost Modeling

  POST /forecast
    in : { "userId": "...", "month": 6, "year": 2026 }
    out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }

Do not change the shape without agreeing it with: U-CS 38 (spend-advisor), U-CS 43 (dependant-costs), U-CS 46 (ops-metrics)
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.schemas import Request, Response
from app.service import handle

app = FastAPI(title="U-CS 37 — budget-forecast", version="0.1.0")

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


@app.get("/health")
def health():
    """Hosting platforms call this to check the service is alive."""
    return {"status": "ok"}


@app.post("/forecast", response_model=Response)
def endpoint(body: Request) -> Response:
    return handle(body)


# Serve the demo console at the root, so the deployed URL shows something a
# person can use rather than a bare 404. Mounted last so it cannot shadow
# /forecast, /health or /docs, and skipped when the directory is absent so the
# service still starts from a partial checkout.
if DEMO_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DEMO_DIR, html=True), name="demo")
