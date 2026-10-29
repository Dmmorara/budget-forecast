"""
The contract, as validated types. Other teams depend on these shapes.

U-CS 37 — budget-forecast

    POST /forecast
      in : { "userId": "...", "month": 6, "year": 2026 }
      out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }

Downstream consumers: U-CS 38 (spend-advisor), U-CS 43 (dependant-costs),
U-CS 46 (ops-metrics).

Two deliberate decisions are recorded here so they are not re-litigated later:

1.  The request fields are REQUIRED. The skeleton shipped with
    `extra="allow"` and no fields, which meant `POST /forecast {}` returned a
    cheerful 200 and a forecast for nobody. A missing or misspelled `userId`
    must fail loudly at the boundary, not silently produce a number another
    team then displays to a user. Unknown EXTRA fields are still ignored, so a
    caller adding metadata we do not use cannot break us.

2.  `estimatedTotalLow` / `estimatedTotalHigh` are additive and optional.
    The frozen contract carries `confidence` as a single scalar, but a scalar
    cannot express a range, and "the confidence range is honest" is in the
    done-when. Optional additive fields do not break any existing consumer —
    they are invisible to anyone not looking for them — but they ARE a change
    to the published shape and must be reported to Benjamin for the Team
    Integration Map rather than assumed.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Risk flags are a closed set, not free text. A downstream team branching on
# this value needs to know what it can receive.
RiskFlag = Literal[
    "insufficient_history",  # too few months of data to forecast responsibly
    "volatile",              # spend varies too much for the interval to be tight
    "overspend_risk",        # forecast materially exceeds the household's budget
]

# What the platform categorises spend into. Sourced from budget_categories;
# kept open at the type level because the sandbox may add to it.
CategoryName = str


class Request(BaseModel):
    """in : { "userId": "...", "month": 6, "year": 2026 }"""

    userId: str = Field(min_length=1, description="Household/user identifier")
    month: int = Field(ge=1, le=12, description="Calendar month being forecast, 1-12")
    year: int = Field(ge=2000, le=2100, description="Calendar year being forecast")

    # Extras ignored rather than rejected: forgiving to integrators, while the
    # required fields above still catch the realistic mistake (a typo in a key
    # name leaves the real key missing, which is a 422).
    model_config = {"extra": "ignore"}


class Response(BaseModel):
    """out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }"""

    estimatedTotal: float = Field(default=0.0, ge=0.0)
    breakdown: dict[CategoryName, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    riskFlag: Optional[RiskFlag] = None

    # Additive, optional — see note 2 in the module docstring.
    estimatedTotalLow: Optional[float] = Field(default=None, ge=0.0)
    estimatedTotalHigh: Optional[float] = Field(default=None, ge=0.0)

    # Present in the skeleton stub, kept. `isSynthetic` is a project rule:
    # every number this service emits while it is trained on generated data
    # says so on its face, so a figure cannot be quoted in a report or a demo
    # without the caveat travelling with it.
    isSynthetic: bool = True
    method: str = "baseline"

    model_config = {"extra": "allow"}


class BudgetResponse(BaseModel):
    """
    out of GET /budget?userId=... (FR-09):
      { "userId": "...", "allocated": { "<category>": 0.0 }, "isSynthetic": true }

    A new endpoint, so this is additive: POST /forecast is untouched.

    An UNKNOWN household gets HTTP 200 with `allocated` empty, not a 404 — the
    same choice POST /forecast makes, for the same reason. To the client the
    two cases mean the same thing: there is no declared budget to show beside
    the forecast (FR-13), just as the forecaster falls back to history alone
    when a budget is missing (FR-08). A 404 would add an error class the client
    is not specified to handle (IR-04 covers timeout, network failure, 422 and
    5xx). A missing or empty `userId` is still a 422, as for /forecast (FR-02).

    A category budgeted at 0 is present with 0.0: a declared zero is a
    declaration, and differs from a category the household never budgeted.
    """

    userId: str
    allocated: dict[CategoryName, float] = Field(default_factory=dict)
    isSynthetic: bool = True
