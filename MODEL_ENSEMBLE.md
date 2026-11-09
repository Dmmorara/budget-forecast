# Fitted model — the ensemble was tried, a single ExtraTrees was chosen

A fitted model is now required to ship. This records how it was chosen. A
three-learner ensemble (Ridge, ExtraTrees, HistGradientBoosting) beat the
shipped blend, but only while it was biased low. Correcting the bias removed
its advantage over ExtraTrees alone. **The model chosen to ship is
`extratrees-v1`: one capped ExtraTrees on the raw target.** `app/` does not use
it yet; wiring it in is the next step.

```bash
pip install -r requirements-train.txt                       # scikit-learn 1.5.2, training only
python3 -m scripts.build_panel                              # feature panel -> data/panel.csv
python3 -m scripts.fit_model --model extratrees             # extratrees-v1: holdout + artefact
python3 -m scripts.fit_model --validate-only [--capped]                 # ensemble A, months 13-15
python3 -m scripts.fit_model --targets fixed --validate-only [--capped] # ensemble B and C, 13-15
python3 -m scripts.measure_model_memory models/extratrees-v1.joblib
```

`--model extratrees` refuses to run with uncommitted tracked changes, and it
opens the holdout every time it runs.

**Data:** synthetic. The platform sandbox, `data/spending_records.csv`: 500
households, 17 categories, 18 months (Apr 2025 – Sep 2026). Every figure here
describes generated households.

**Splits.** Target months are numbered from Apr 2025 = 1. Configuration is
chosen by fitting on targets 4–12 and scoring 13–15 (Apr–Jun 2026). The final
model is refitted on 4–15. The holdout is 16–18 (Jul–Sep 2026), 1,500
household-months. All scoring goes through `app.evaluate.evaluate`, with the
same rolling origin as every other figure in the project. **Mean signed
error** is mean(predicted − actual) on the monthly total: negative means the
forecast is low.

---

## Result: extratrees-v1 against the blend, holdout

40 trees, max_depth 12, min_samples_leaf 20, max_features 1.0,
random_state 37, raw target, predictions clipped at 0.

| forecaster | MAE | MAPE | medAPE | category MAE | mean signed error |
|---|---|---|---|---|---|
| blend (shipped) | 8941.2 | 11.01% | 8.91% | 1925.7 | +824.2 |
| **extratrees-v1** | **8382.1** | **10.20%** | **8.13%** | **1850.4** | **−37.9** |

Paired against the blend on the same 1,500 household-months. Negative is
better.

| | Δ | t |
|---|---|---|
| MAE | **−559.0** | −6.40 |
| MAPE | −0.81 pp | −8.07 |
| category MAE | **−75.4** | −8.90 |
| wins (smaller total error) | 840 / 1500 | |

| month | MAE Δ | category MAE Δ | signed error | blend's signed error |
|---|---|---|---|---|
| Jul 2026 | −491.5 | −96.5 | −105.1 | +690.3 |
| Aug 2026 | −569.6 | −64.9 | +212.5 | +996.7 |
| Sep 2026 | −616.0 | −64.7 | −221.0 | +785.4 |

It is better than the blend on all four accuracy metrics and in each month,
and it is close to unbiased: −37.9 KES against a mean actual total of
74,777. The blend is the one forecasting high, by 824. On the months it was
chosen on (13–15) its signed error was +346.7. Its sign varies by month, from
−221 to +213, so the holdout shows no consistent lean either way.

**This holdout was not fresh.** The same capped configuration was the
ExtraTrees row of the capped-ensemble run below, and that run printed these
exact holdout figures before C was chosen. The choice rests on the
validation split, but the holdout cannot count as an independent
confirmation of it.

---

## How it got here

### 1. The ensemble won on the holdout, but only while it was biased low

The specification fitted Ridge on log1p(spend), inverted with expm1, and
HistGB with `loss="absolute_error"`. Unconstrained, on the holdout (variant A):

| forecaster | MAE | MAPE | medAPE | category MAE | mean signed error |
|---|---|---|---|---|---|
| blend | 8941.2 | 11.01% | 8.91% | 1925.7 | +824.2 |
| Ridge, log1p | 10299.0 | 12.57% | 10.16% | 1997.0 | −3919.1 |
| ExtraTrees | 8349.9 | 10.19% | 8.23% | 1868.1 | −22.8 |
| HistGB, absolute error | 9577.0 | 11.01% | 9.01% | 1860.7 | −7654.1 |
| ensemble, equal weight | 8443.7 | 9.81% | 7.70% | 1797.8 | **−3865.3** |

Paired against the blend, the ensemble had MAE −497.5 (t −3.50), MAPE
−1.20 pp (t −6.73) and category MAE −127.9 (t −12.19). It won on all four
metrics and in all three months.

It forecast 3,865 KES (5%) low. For this project that is the wrong direction:
the problem is households spending on an inflated sense of available money,
and a forecast that says the month will cost less than it will makes that
worse.

### 2. The bias came from the specified targets

The cause was the specification, not chance. log1p then expm1 estimates
something nearer the geometric mean, and absolute-error loss estimates the
median. On right-skewed spend both sit below the arithmetic mean, and the
ensemble averaged their biases.

### 3. Correcting it removed the advantage

Variant B fits Ridge on the raw target and HistGB with `squared_error`. The
grid was re-run for it on months 13–15, not borrowed from A. C is ExtraTrees
alone, unchanged. Validation only, months 13–15:

**Capped** (ExtraTrees 40 trees, max_depth 12; HistGB max_depth 6), which is
what ships:

| | MAE | category MAE | mean signed error |
|---|---|---|---|
| blend | 8416.1 | 1886.8 | +1581.8 |
| A. ensemble, log1p / absolute error | 7961.7 | **1730.0** | **−3549.0** |
| B. ensemble, raw / squared error | 7944.1 | 1790.4 | +388.0 |
| **C. ExtraTrees alone** | **7848.5** | 1779.4 | **+346.7** |

**Unconstrained:**

| | MAE | category MAE | mean signed error |
|---|---|---|---|
| A. ensemble | 7973.1 | 1732.6 | −3496.3 |
| B. ensemble | 7951.4 | 1791.9 | +388.8 |
| C. ExtraTrees alone | 7905.9 | 1786.7 | +389.1 |

The correction worked on the parts:

| capped | A signed error | B signed error |
|---|---|---|
| HistGB | −7010.0 | +215.4 |
| Ridge | −3983.6 | +601.8 |

But A's lead on category MAE was the only thing it had over C, and it came
with the bias. Once the bias was gone, B lost to C on both MAE and category
MAE. So the three-learner ensemble is recorded as a negative finding, and C,
capped, was chosen. B was never scored on the holdout.

### What the negative finding does and does not say

- **The B-vs-C gaps are small and untested.** Capped, C leads by 95.6 MAE and
  11.0 category MAE; unconstrained, by 45.5 and 5.2. No paired test was run
  on the validation split, and three months of 500 households may not
  separate them.
- **HistGB sat at its grid boundary with a real spread.** For B it chose the
  smallest setting searched, learning_rate 0.05 with 200 iterations, and the
  candidates ranged from 8,149.7 to 8,692.4 MAE. A smaller or slower setting
  outside the grid might do better and could change the outcome. (Ridge also
  chose a boundary, alpha 100, but its four candidates are within 36 KES of
  each other.)
- **So the claim is "no advantage over ExtraTrees alone at the
  configurations searched"**, not that a bias-free ensemble cannot help.

The grid (in `scripts/fit_model.py`, printed by every run):

| learner | candidates | chosen for B, by total MAE on 13–15 |
|---|---|---|
| Ridge | alpha 0.1, 1, 10, 100 | 100 |
| ExtraTrees | min_samples_leaf 1, 5, 20 × max_features 1.0, 0.5 | leaf 20, max_features 1.0 |
| HistGB | learning_rate 0.05, 0.1 × max_iter 200, 500 | 0.05, 200 |

HistGB runs with `early_stopping=False`, because its built-in early stopping
holds out a random tenth of the rows and would mix months. The capped
variants apply max_depth on top of the grid. The caps were fixed before
fitting, not chosen on any split.

---

## Where the gain comes from

Impurity importances from the unconstrained ensemble's ExtraTrees, training
fit. They show where the trees split, not a causal ranking.

| feature | importance |
|---|---|
| declared budget | 0.355 |
| trailing median, all months | 0.177 |
| blend value | 0.122 |
| category = Rent | 0.097 |
| trailing mean, all months | 0.088 |
| trailing mean, last 6 months | 0.081 |

The trees lean on the same two signals the blend does, the budget and the
level of past spending, but they combine them per category and per level
instead of with one fixed 0.8 / 0.2 weight. Calendar month and last month's
amount do not appear near the top. That fits SANDBOX_RESULTS.md's finding
that the sandbox has no temporal structure to exploit (lag-1 autocorrelation
−0.07). The gain is a better combination of level estimates, not a model of
change over time.

---

## Size and memory

`models/extratrees-v1.joblib` is **4.5 MB** (4,528,035 bytes). The capped
three-learner ensemble was 6.4 MB and the unconstrained one 33.9 MB; both
have been deleted.

Resident memory of a fresh process that answers one `POST /forecast` through
the app, then loads the artefact and makes one prediction. Measured in the
service's own Docker image (Linux, arm64) with scikit-learn 1.5.2 added:

| data in the image | service alone | service + extratrees-v1 | peak | headroom on 512 MB |
|---|---|---|---|---|
| deployed 60-household slice | 107.3 MB | **190.5 MB** | 189.8 MB | ~321 MB |
| full 500-household extract | 160.1 MB | **210.0 MB** | 239.5 MB | ~272 MB at peak |

Both are well under the 512 MB Render free instance and under the ~300 MB
line. With the full extract the peak comes from loading the 53 MB CSV, not
from the model: it is reached before the artefact is read.

About 78 MB of what the model adds is importing scikit-learn and scipy, before
any artefact is read (measured on macOS: 66.8 MB with pandas and numpy, 145.1
MB after the scikit-learn imports).

An earlier macOS measurement put the full extract at 387 MB with the
unconstrained ensemble. That was macOS's figure; Linux is the platform Render
runs. Two limits on these numbers:

- Render runs x86-64; this container ran on arm64.
- It is one process answering one request at a time. Concurrent requests
  were not measured.

---

## What this does not show

- **The holdout has been read many times.** SANDBOX_RESULTS.md scored months
  16–18 to confirm the blend's weight and several rejected alternatives, and
  this work read them for variant A and its parts, including the
  configuration that was later chosen. Nothing was tuned on them, but they
  are no longer an independent test. The validation split is the stronger
  evidence.
- **No interval and no confidence.** The model gives a point forecast per
  category. The service's contract returns an interval and a confidence, and
  the blend's 91.5% coverage has no counterpart here.
- **Synthetic data, one extract.** 500 generated households over 18 months.
- **The deployed slice is a sample of the same sandbox**
  (`scripts/minimise_extract.py`), under pseudonymised ids. Its households
  were in the training panel under their original ids, so a forecast served
  for one of them on the live site is not out-of-sample. The demo shows the
  contract and the honesty mechanisms working, not accuracy.
- **`has_budget` is constant.** Every candidate category has a budget row in
  this extract, so the feature carries nothing. It is kept so the feature
  list does not depend on the extract.

## Reproducibility

`models/extratrees-v1.joblib` and its manifest are tracked. `.gitignore`
excludes the contents of `models/` and un-ignores `*.joblib` and
`*.manifest.json`. The manifest records:

- `git_head` dc48878, the commit that produced the artefact, with no
  uncommitted tracked changes;
- the last training month (2026-06) and the ordered list of 31 features;
- the installed versions: scikit-learn 1.5.2, pandas 2.2.3, numpy 2.1.1,
  joblib 1.6.0;
- random_state 37 and the artefact's SHA-256, `5ec309c3…88055a`.

A second fit of the same configuration, done without scoring, gave a
byte-identical file.

The variant A runs (`fit_model` without `--model extratrees`) still write
`models/ensemble-v1*.joblib`. Those are history, not something to commit;
stage model files by explicit path, never `git add models/`.

## What shipping would take

None of this is done. `app/` is unchanged.

1. Move `scikit-learn==1.5.2` into `requirements.txt`. That undoes most of
   the image saving from #38 (772 MB → 492 MB), but it should not slow the
   build: PyPI has a 1.5.2 wheel for CPython 3.11 on manylinux x86-64, which is
   what the service's `python:3.11-slim` image runs. The six-minute compile
   seen on Render was most likely the static site's builder installing
   `requirements.txt` on its default Python 3.14, for which 1.5.2 has no wheel.
   That is an inference; no Render build log confirms it.
2. Load the artefact in the service. It is tracked in the repository Render
   builds from, so it reaches the image through `COPY . .`. Check it against
   the manifest's SHA-256 at start-up and refuse a mismatch.
3. Serve features with `scripts.build_panel.features_for`, which is what the
   memory measurement exercised. It needs to move into `app/` first.
4. Decide the interval and the confidence before `POST /forecast` returns
   this model's numbers.
