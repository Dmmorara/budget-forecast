# budget-forecast  —  U-CS 37

**AI Lifestyle Budgeting & Cost Modeling** · Wasaa Lifestyle

Predict what a household will spend next month, per category, with a confidence range.

---

## Your contract

This is the shape the rest of the system expects. Agree any change with the teams below,
then tell Benjamin so the Team Integration Map gets reissued.

```
POST /forecast
  in : { "userId": "...", "month": 6, "year": 2026 }
  out: { "estimatedTotal": 0, "breakdown": {}, "confidence": 0.0, "riskFlag": null }
```

**Call it `budget-forecast` everywhere** — your repo name, your service URL, your route, and the
variable Benjamin sets when integrating you: `BUDGET_FORECAST_SERVICE_URL`

## Who you depend on

Nothing. You are upstream — start on day one.

## Who depends on you

U-CS 38 (spend-advisor), U-CS 43 (dependant-costs), U-CS 46 (ops-metrics)

## Done when

Your forecast beats "same as last month" on held-out months, and the confidence range is honest.

---

## Run it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> — FastAPI gives you interactive API docs for free, so you can
test your endpoint without writing a client. Open `demo/index.html` for the mini app.

```bash
pytest -q                 # the contract test
docker build -t budget-forecast . && docker run -p 8000:8000 budget-forecast
```

## The order of work

1. **Baseline.** The dumbest thing that works, returned from `app/service.py`. Measure it and
   **write the number down.** You are not allowed to build a model before this exists.
2. **Evaluation.** Pick your metric. Split your data **by time**, not at random, and hold the
   last part back.
3. **Model.** Build the real thing. Show it beats the baseline.
4. **Integration.** Keep the contract identical while the inside changes completely. Deploy it,
   send Benjamin the URL.

## What you hand in

- This repo, on GitHub, with Benjamin added as a collaborator
- A live URL that answers
- The filled-in documents (templates are in the `documents/` folder of the skeleton repo)
- A README a stranger could run this from

## Rules

- No secrets in git. No `.env`, no keys. Commit `.env.example` instead.
- Label synthetic data as synthetic — in the code and in the report.
- Staging data only. Never production, never live M-Pesa.
- Tell Benjamin the same day if you find a real bug in the platform.

---

# Implementation

Daniel Momanyi · ADM 168326 · ICS 4.1 E · Strathmore University
Supervisor: Dr Vincent Ochango · Industry partner: Webmasters Kenya

## Status

| Step | State |
|---|---|
| 1. Baseline | **Done** — measured, recorded in [`BASELINE.md`](BASELINE.md), live in `app/service.py` |
| 2. Evaluation | **Done** — rolling-origin time split, `app/evaluate.py` |
| 3. Model | **Done** — `TwoShapeForecaster`, recorded in [`MODEL.md`](MODEL.md), live in `app/service.py` |
| 4. Integration | Dockerfile deploy-ready; `render.yaml` blueprint; awaiting a live URL |

**All numbers so far are from synthetic data.** The sandbox extract is not yet in `data/`,
and every response carries `isSynthetic: true` until it is.

## Where things are

```
app/
  schemas.py     the contract as validated types — the frozen shape
  service.py     POST /forecast; FORECASTER is the single swap point
  forecaster.py  the Forecaster interface and the two baselines
  evaluate.py    rolling-origin time split, metrics, noise floor
  model.py       the shipped forecaster: fixed obligations + habitual rates
  data.py        real sandbox CSVs if present in data/, synthetic otherwise
  synthetic.py   the generator — labelled synthetic throughout
scripts/
  measure_baseline.py   reproduces every number in BASELINE.md
  compare_model.py      reproduces every number in MODEL.md (12 populations)
  smoke_test.py         checks a deployed URL answers the contract
tests/
  test_contract.py      the shape other teams rely on
  test_synthetic.py     the generator, and that it stays non-stationary
  test_forecaster.py    the baselines
  test_evaluation.py    the harness, and the anti-leakage guarantee
  test_model.py         the model, paired across populations
BASELINE.md      the number to beat, and where the removable error lives
MODEL.md         what beat it, what did not, and why three components were cut
```

## Two things a stranger should know before reading the code

**The forecaster interface is stateless on purpose.** A forecaster is a function of
`(history, user_id, year, month)` where `history` contains only months strictly *before*
the target. It is not an object fitted once and then queried. That makes leakage
structurally impossible rather than merely avoided, and
`test_harness_never_shows_the_target_month` asserts it with a spy that fails the suite if
any future row is ever handed over.

**Only 14.6% of the baseline's error is removable.** The synthetic generator reports the
latent monthly expectation each household-month was drawn from, which gives an irreducible
noise floor of MAE 4389.7 against the baseline's 5137.9. A model reaching 4400 has
extracted essentially all available signal; one reporting 2000 has a leak. See
[`BASELINE.md`](BASELINE.md).

**No forecasting claim rests on one population.** Component effects here are around 40 KES
and the standard deviation of the MAE difference between two forecasters on a single
population is 50-110 KES, so a single-population comparison cannot tell an improvement
from a lucky draw. Every figure in [`MODEL.md`](MODEL.md) is paired across 12 populations.
Measuring on one population first suggested three components worked that do not.

## Contract notes

Two deliberate departures from the skeleton, both documented in `app/schemas.py`:

1. **Request fields are required.** The skeleton accepted `POST /forecast {}` with a 200.
   A missing or misspelled `userId` now returns 422 rather than a forecast for nobody.
   Unknown *extra* fields are still ignored, so a caller adding metadata cannot break us.

2. **`estimatedTotalLow` / `estimatedTotalHigh` are additive and optional.** The frozen
   contract carries `confidence` as a scalar, which cannot express a range, and "the
   confidence range is honest" is in the done-when. Optional additive fields are invisible
   to any consumer not looking for them — but this **is** a change to the published shape
   and needs Benjamin's sign-off for the Team Integration Map.

`riskFlag` is a closed set: `insufficient_history`, `volatile`, `overspend_risk`.
Downstream teams branching on it need to know what they can receive.

## Run it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000    # http://localhost:8000/docs
pytest -q                                   # 49 tests
python3 -m scripts.measure_baseline          # reproduce BASELINE.md
python3 -m scripts.compare_model             # reproduce MODEL.md (slow)
```

With no CSV in `data/`, the service generates its own synthetic population on first
request, so it runs with no setup and no credentials.

## Deploy it

Render builds the image itself, so no local Docker installation is needed:

1. Render dashboard → **New** → **Blueprint** → select this repository.
2. Render reads [`render.yaml`](render.yaml), builds the Dockerfile and assigns a URL.
3. Verify it, then send the URL to Benjamin for `BUDGET_FORECAST_SERVICE_URL`:

```bash
python3 -m scripts.smoke_test https://budget-forecast-xxxx.onrender.com
```

That checks the contract three other teams depend on, not just that the process is
up — including that `POST /forecast {}` is a 422 and that `breakdown` sums to
`estimatedTotal`.

**The free plan sleeps** after ~15 minutes idle, and the next request takes about 50
seconds. Send one request a few minutes before any demo, and tell Benjamin, because
a cold start looks like a timeout from the calling side.

To build locally instead (needs Docker Desktop):

```bash
docker build -t budget-forecast .
docker run --rm -e PORT=8000 -p 8000:8000 budget-forecast
```

[`.dockerignore`](.dockerignore) keeps `.env`, `venv/` and the test suite out of the
image. Without it `COPY . .` would bake any `.env` into a layer, where `docker history`
exposes it even if a later layer deletes the file.
