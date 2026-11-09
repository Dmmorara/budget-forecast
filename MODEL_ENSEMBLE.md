# Fitted ensemble — Ridge + ExtraTrees + HistGradientBoosting against the blend

A fitted model is now required to ship. This records the candidate: an
equal-weight ensemble of three learners on a per-category feature panel,
measured against what the service ships today, `BudgetBlendForecaster`
(0.8 × trailing mean + 0.2 × declared budget). An earlier side experiment with
the same design was never committed; nothing here reuses its numbers.

```bash
pip install -r requirements-train.txt           # scikit-learn 1.5.2, training only
python3 -m scripts.build_panel                  # feature panel -> data/panel.csv
python3 -m scripts.fit_model                    # every number below, unconstrained
python3 -m scripts.fit_model --capped           # the capped variant
python3 -m scripts.measure_model_memory models/ensemble-v1.joblib
```

**Data:** synthetic. The platform sandbox, `data/spending_records.csv`: 500
households, 17 categories, 18 months (Apr 2025 – Sep 2026). Every figure here
describes generated households.

**Not shipped.** `app/` is unchanged. What shipping would take is at the end.

---

## Result

Holdout: target months 16–18 (Jul–Sep 2026), 1,500 household-months, scored
by `app.evaluate.evaluate` with the same rolling origin as every other figure
in the project. The blend's row reproduces SANDBOX_RESULTS.md exactly.

| forecaster | MAE | MAPE | medAPE | category MAE |
|---|---|---|---|---|
| blend (shipped) | 8941.2 | 11.01% | 8.91% | 1925.7 |
| Ridge, log1p target | 10299.0 | 12.57% | 10.16% | 1997.0 |
| ExtraTrees | 8349.9 | 10.19% | 8.23% | 1868.1 |
| HistGradientBoosting, absolute error | 9577.0 | 11.01% | 9.01% | 1860.7 |
| **ensemble, equal weight** | **8443.7** | **9.81%** | **7.70%** | **1797.8** |

Paired against the blend on the same 1,500 household-months. Negative is
better. `t` is a one-sample t statistic on the per-household-month
differences; `wins` counts household-months where the total's error is
smaller than the blend's.

| | MAE Δ (t) | MAPE Δ pp (t) | category MAE Δ (t) | wins |
|---|---|---|---|---|
| Ridge | +1357.9 (+7.42) | +1.56 (+6.24) | +71.2 (+4.18) | 592/1500 |
| ExtraTrees | **−591.2 (−6.54)** | −0.82 (−7.88) | −57.6 (−6.38) | 827/1500 |
| HistGB | +635.8 (+2.95) | −0.00 (−0.01) | −65.0 (−5.01) | 670/1500 |
| **ensemble** | **−497.5 (−3.50)** | **−1.20 (−6.73)** | **−127.9 (−12.19)** | 781/1500 |

Ensemble minus blend, MAE by month: **−300.0** (Jul), **−686.6** (Aug),
**−506.0** (Sep). Better in each of the three.

**The ensemble beats the blend on all four metrics**, and the category
breakdown, which U-CS 38 consumes, is the strongest result: t = −12.19.

**It is not the best single forecaster on the total.** ExtraTrees alone has the
lower MAE (−591.2 against −497.5). The validation split showed the same thing
before the holdout was opened (below), so this is not a holdout artefact. But
switching to ExtraTrees alone now would be a choice made after reading months
16–18, and the requirement asked for the ensemble; it is recorded here as the
obvious next comparison, not acted on.

**Wins are 781 of 1,500, barely half.** The mean improvement comes from fewer
large misses, not from being closer on a typical household-month. The medAPE
gain (8.91% to 7.70%) says the same.

---

## Two splits agreed

Configuration was chosen with the holdout cut out of the panel: fit on
targets 4–12, score 13–15. The final model was then refitted on 4–15.

| months 13–15 | MAE | category MAE |
|---|---|---|
| blend (shipped) | 8416.1 | 1886.8 |
| Ridge, alpha 0.1 ← chosen | 10027.1 | 1946.1 |
| ExtraTrees, 100 trees, leaf 20, all features ← chosen | 7905.9 | 1786.7 |
| HistGB, lr 0.1, 500 iterations ← chosen | 8917.4 | 1791.1 |
| **ensemble of the three** | **7973.1** | **1732.6** |

The ensemble led the blend on validation by 443 MAE and 154 category MAE, and
on the holdout by 498 and 128. Same direction, similar size. Agreement between
two splits is the standard this project has applied to every result it
believes; SANDBOX_RESULTS.md and MODEL.md record several that held on one split
and vanished on another.

The grid (all of it is in `scripts/fit_model.py` and printed by it):

| learner | candidates | chosen by total MAE |
|---|---|---|
| Ridge | alpha 0.1, 1, 10, 100 | 0.1 |
| ExtraTrees | min_samples_leaf 1, 5, 20 × max_features 1.0, 0.5; 100 trees | leaf 20, max_features 1.0 |
| HistGB | learning_rate 0.05, 0.1 × max_iter 200, 500 | 0.1, 500 |

Ridge's choice sits at the edge of its grid, but the four alphas are within
92 KES of each other, so a wider grid would not change anything that matters.
HistGB runs with `early_stopping=False`: its built-in early stopping holds out
a random tenth of the rows, which would mix months.

---

## Why Ridge and HistGB lose on the total

Mean signed error on the total, holdout:

| | predicted − actual |
|---|---|
| blend | +824.2 |
| Ridge | −3919.1 |
| ExtraTrees | −22.8 |
| HistGB | −7654.1 |
| ensemble | **−3865.3** |

Both under-forecast, by construction:

- **Ridge** is fitted on log1p(spend) and the prediction is transformed back
  with expm1. That estimates something nearer the geometric mean, which for
  right-skewed spend is below the arithmetic mean.
- **HistGB** uses `loss="absolute_error"`, which estimates the conditional
  median. Per-category medians of skewed amounts sum to less than the mean
  total.

Both choices were specified, not tuned. They still place spend in the right
categories (both beat the blend on category MAE) while missing the total low.
**The ensemble averages the three biases: it forecasts 3,865 KES (5%) below
the mean actual total of 74,777.** A household would see a forecast
that is systematically a little low. Correcting it, for example by fitting
Ridge and HistGB to the mean rather than the log or the median, would need a
fresh validation pass, not a tweak read off this table.

---

## Where the gain comes from

ExtraTrees impurity importances, from the training fit (where the trees split,
not a causal ranking):

| feature | importance |
|---|---|
| declared budget | 0.355 |
| trailing median, all months | 0.177 |
| blend value | 0.122 |
| category = Rent | 0.097 |
| trailing mean, all months | 0.088 |
| trailing mean, last 6 months | 0.081 |

The model leans on the same two signals the blend does, budget and history
level, but combines them per category and per level instead of with one fixed
0.8 / 0.2 weight. Calendar month, days in month and last month's amount do not
appear near the top. That fits SANDBOX_RESULTS.md's finding that the sandbox
has no temporal structure to exploit (lag-1 autocorrelation −0.07): the gain is
a better combination of level estimates, not a model of change over time.

---

## Size and memory

| | unconstrained | capped |
|---|---|---|
| artefact on disk | **33.9 MB** | 6.4 MB |
| ExtraTrees | 100 trees, depth unlimited | 40 trees, max_depth 12 |
| HistGB | depth unlimited | max_depth 6 |

Resident memory of a fresh process that answers one `POST /forecast` through
the app, then loads the artefact and makes one ensemble prediction. Measured
in the service's own Docker image with scikit-learn 1.5.2 added, with
`data/` holding only the 60-household slice the deployment serves:

| Linux aarch64 container, deployed slice | current RSS | the model adds |
|---|---|---|
| service alone, one forecast | 106.8 MB | — |
| service + **unconstrained** model | **246.9 MB** | 140.0 MB |
| service + capped model | 193.8 MB | 87.0 MB |

About 78 MB of what the model adds is importing scikit-learn and scipy, before
any artefact is read (measured on macOS: 66.8 MB with pandas and numpy, 145.1
MB after the scikit-learn imports). The capped trees save about 53 MB beyond
that.

**Against the 512 MB Render free instance, the unconstrained model fits under
the ~300 MB line, at 247 MB.** The capped variant was fitted and measured
anyway, because the margin is not large:

- With the full 500-household extract loaded instead of the slice, the same
  measurement on macOS gives 387.0 MB unconstrained and 349.2 MB capped. Both
  are over the line. A deployment that serves the full extract needs more
  headroom than this.
- Render runs x86-64; this container ran on arm64. The figures will differ
  somewhat.
- It is one process answering one request at a time. Concurrent requests
  were not measured.

Capping costs little accuracy. Holdout, paired against the blend:

| ensemble | MAE | category MAE | MAE Δ (t) | category MAE Δ (t) | mean signed error |
|---|---|---|---|---|---|
| unconstrained | 8443.7 | 1797.8 | −497.5 (−3.50) | −127.9 (−12.19) | −3865.3 |
| capped | 8459.5 | 1791.1 | −481.7 (−3.38) | −134.6 (−12.87) | −3908.6 |

The caps were fixed before fitting, not chosen on any split; within them the
grid was re-run on months 13–15 and chose the same configurations. Capped
validation: ensemble 7961.7 / 1732.6. Capped by month, ensemble minus blend:
−283.2, −660.0, −501.9.

---

## What this does not show

- **Months 16–18 have been read many times.** SANDBOX_RESULTS.md scored them
  to confirm the blend's weight and several rejected alternatives. Nothing
  here was tuned on them, but every additional comparison on the same 1,500
  household-months makes a lucky winner more likely than its t statistic
  suggests. The validation split agreeing is the stronger evidence.
- **No interval and no confidence.** The ensemble produces a point forecast
  per category. The service's contract returns an interval and a confidence,
  and the blend's 91.5% coverage has no counterpart here.
- **Synthetic data, one extract.** 500 generated households over 18 months.
- **The deployed slice is a sample of the same sandbox**
  (`scripts/minimise_extract.py`), under pseudonymised ids. Its households
  were in the training panel under their original ids, so a forecast served
  for one of them is not an out-of-sample test.
- **`has_budget` is constant.** Every candidate category has a budget row in
  this extract, so the feature carries nothing. It is kept so the feature
  list does not depend on the extract.

## Reproducibility

`scripts/fit_model.py` writes the same artefact byte for byte on every run
(`random_state=37` everywhere): sha256 `b73bb636…46c7c` unconstrained,
`65759cfc…a4ec1f` capped. Each `models/*.manifest.json` records the last
training month (2026-06), the ordered feature list, the installed versions
(scikit-learn 1.5.2, pandas 2.2.3, numpy 2.1.1, joblib 1.6.0), the chosen
configuration, the git commit and the artefact's SHA-256.

`models/` is gitignored, so the artefacts and manifests are not committed.
The manifests record `git_head` b1c5092 with uncommitted tracked changes, and
the scripts that wrote them were not yet committed. Rerunning after the
scripts are committed gives the same artefact and a clean manifest.

## What shipping would take

None of this is done. `app/` was deliberately left alone.

1. Move `scikit-learn==1.5.2` into `requirements.txt`. That undoes most of
   the image saving from #38 (772 MB → 492 MB), but it should not slow the
   build: PyPI has a 1.5.2 wheel for CPython 3.11 on manylinux x86-64, which is
   what the service's `python:3.11-slim` image runs. The six-minute compile
   seen on Render was most likely the static site's builder installing
   `requirements.txt` on its default Python 3.14, for which 1.5.2 has no wheel.
   That is an inference; no Render build log confirms it.
2. Get the artefact to the service. `models/` is gitignored and Render builds
   from the repository, so either commit a 6.4–33.9 MB binary or fetch it at
   start-up and check it against the manifest's SHA-256.
3. Serve features with `scripts.build_panel.features_for`, which is what the
   memory measurement exercised. It needs to move into `app/` first.
4. Decide on the interval, the confidence and the −3,865 KES bias before
   `POST /forecast` returns this model's numbers.
