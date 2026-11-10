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
| 4. Integration | **Deployed** — service <https://budget-forecast-e8ad.onrender.com>, passing `scripts/smoke_test.py`; web app <https://budget-forecast-web.onrender.com> |

**All numbers so far are from synthetic data.** The sandbox extract is not yet in `data/`,
and every response carries `isSynthetic: true` until it is.

## Where things are

```
app/
  schemas.py     the contract as validated types — the frozen shape
  service.py     POST /forecast; FORECASTER is the single swap point
  forecaster.py  the Forecaster interface, the two baselines, and
                 ExtraTreesForecaster (the fitted model; not yet served)
  features.py    the model's features: one definition for fitting and serving
  evaluate.py    rolling-origin time split, metrics, noise floor
  model.py       the shipped forecaster: fixed obligations + habitual rates
  data.py        real sandbox CSVs if present in data/, synthetic otherwise
  synthetic.py   the generator — labelled synthetic throughout
scripts/
  measure_baseline.py   reproduces every number in BASELINE.md
  compare_model.py      reproduces every number in MODEL.md (12 populations)
  analyse_sandbox.py    reproduces SANDBOX_RESULTS.md's autocorrelation, oracle
                        and dependants figures (needs the full extract)
  smoke_test.py         checks a deployed URL answers the contract
  measure_latency.py    times warm POST /forecast calls for NFR-07
  build_panel.py        the fitted ensemble's feature panel (needs the full extract)
  fit_model.py          reproduces every number in MODEL_ENSEMBLE.md, and writes
                        the shipped models/extratrees-v2 (--model extratrees --disjoint)
  measure_model_memory.py  resident memory of the service with the model loaded
  calibrate_interval.py    the model's split-conformal interval, verified once
tests/
  test_contract.py      the shape other teams rely on
  test_synthetic.py     the generator, and that it stays non-stationary
  test_forecaster.py    the baselines
  test_evaluation.py    the harness, and the anti-leakage guarantee
  test_model.py         the model, paired across populations
  test_model_pins.py    every model manifest's scikit-learn, numpy and pandas
                        versions match requirements.txt; a bump fails CI
BASELINE.md      the number to beat, and where the removable error lives
MODEL.md         what beat it, what did not, and why three components were cut
PERFORMANCE.md   NFR-07 response times against the deployed service
MODEL_ENSEMBLE.md  the fitted model: ensemble tried, ExtraTrees chosen (not yet in app/)
requirements-train.txt  scikit-learn, for the ensemble scripts only
client/          the Flutter app (Android, web, iOS) — see client/README.md
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

## Requirement numbering

The code, tests and other documents here use the original Chapter 4 numbering:
FR-01 to FR-16 and NFR-01 to NFR-10. The submitted report consolidates these into
five functional and five non-functional requirements. The IDs in this repository
are **not** renumbered. To find a requirement in the report, use this table:

| Report | Original IDs used in this repo | Covers |
|---|---|---|
| FR-01 | FR-01, FR-03, FR-04 | the response contract |
| FR-02 | FR-05 | only months before the target month are used |
| FR-03 | FR-02, FR-06, FR-07 | honest degradation, including the volatile flag |
| FR-04 | FR-08, FR-09 | the budget blend and `GET /budget` |
| FR-05 | FR-10 to FR-16 | client presentation |
| NFR-01 | NFR-02 | honesty of uncertainty |
| NFR-02 | NFR-03, NFR-04 | privacy and security |
| NFR-03 | NFR-01, NFR-05, NFR-09 | contract stability and reproducibility |
| NFR-04 | NFR-07, NFR-08 | performance and availability |
| NFR-05 | NFR-06, NFR-10 | portability and usability |

The amended volatile rule ("FR-07 as amended" in `app/`, `MODEL_ENSEMBLE.md` and the
tests) is a clause inside the report's FR-03, not a requirement of its own. So, for
example, `PERFORMANCE.md`'s NFR-07 is the report's NFR-04.

No copy of Chapter 4 is kept in this repository. The submitted report is the
authority for requirement wording.

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

### GET /budget (FR-09)

A separate, additive endpoint for the Flutter client's budget comparison. `POST
/forecast` is unchanged.

```
GET /budget?userId=h015
  200: { "userId": "h015", "allocated": { "Rent": 20000.0, ... }, "isSynthetic": true }
```

| case | response |
|---|---|
| known household | 200, `allocated` maps each budgeted category to KES; a declared 0 appears as `0.0` |
| unknown household | 200, `allocated` is `{}` — **not a 404** |
| `userId` missing or empty | 422 |

An unknown household is not an error, as with `POST /forecast`. For the client it
means the same as a household with no budget: there is nothing to show beside the
forecast. A 404 would add an error class the client is not specified to handle.

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
python3 -m scripts.smoke_test https://budget-forecast-e8ad.onrender.com
```

That checks the contract three other teams depend on, not just that the process is
up — including that `POST /forecast {}` is a 422 and that `breakdown` sums to
`estimatedTotal`.

**The Flutter web app is a second service in the blueprint,** `budget-forecast-web`,
a Render static site. Render's build image has no Flutter, so
[`client/tool/render_build.sh`](client/tool/render_build.sh) fetches the pinned SDK
and builds it; `client/build/` is never committed. The two services need each
other's URL, so after the first deploy set two values in the dashboard:

1. `FORECAST_API_URL` on `budget-forecast-web`: the service's URL. Redeploy the
   site, because the URL is compiled into the app. Until it is set, the site's
   build fails on purpose.
2. `CORS_ALLOWED_ORIGINS` on `budget-forecast`: the web app's origin.

**The Flutter web build needs CORS.** Set `CORS_ALLOWED_ORIGINS` on the Render
service to the web app's origin, `https://budget-forecast-web.onrender.com` (comma-separate
several). Unset, the service allows no cross-origin browser calls at all, which is
the safe default and shows up as a CORS error in the browser console. Callers that
are not browsers (the platform, U-CS 38, 43 and 46) need nothing.

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

### Which forecaster is answering

`POST /forecast` answers with the fitted model, `extratrees-v2`, when its files
load at startup: the artefact's SHA-256 must match its manifest, and the feature
list and calibration must validate. Otherwise it answers with the blend, and the
service never returns a 500 because of a model file. The blend also answers
whenever the model must not, request by request:

- households with fewer than three months of history, exactly as before the model;
- months inside the model's training period, up to 2026-06;
- any request on which the model raises.

`method` in each response names whichever forecaster answered. `GET /health`
names the active one, additively:

```json
{"status": "ok", "forecaster": "model:extratrees-v2", "fallbackReason": null}
```

A deployment whose model file went missing still looks healthy, because every
request is answered. When that happens, `forecaster` is `blend:history0.8_budget0.2`
and `fallbackReason` says why. The startup log says the same once.

### Is the model in the image?

`.dockerignore` admits the three shipped model files by exact name and nothing
else from `models/`. To check a built image rather than assume it:

```bash
docker run --rm --entrypoint python budget-forecast -c "
import hashlib, json, pathlib
m = pathlib.Path('/app/models')
man = json.loads((m / 'extratrees-v2.manifest.json').read_text())
assert hashlib.sha256((m / 'extratrees-v2.joblib').read_bytes()).hexdigest() == man['sha256']
from app.service import FORECASTER
assert FORECASTER.model is not None, FORECASTER.fallback_reason
print('model present and loaded:', FORECASTER.name)"
```

On the deployed service, `curl https://budget-forecast-e8ad.onrender.com/health`
answers the same question.
