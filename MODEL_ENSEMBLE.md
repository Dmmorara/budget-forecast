# Fitted model — the ensemble was tried, a single ExtraTrees was chosen

A fitted model is now required to ship. This records how it was chosen. A
three-learner ensemble (Ridge, ExtraTrees, HistGradientBoosting) beat the
shipped blend, but only while it was biased low. Correcting the bias removed
its advantage over ExtraTrees alone. **The model chosen to ship is
`extratrees-v2`: one capped ExtraTrees on the raw target, fitted without any of
the 60 households the deployed service serves**, so every live forecast is
out-of-sample. `app/` does not use it yet; wiring it in is the next step.

```bash
pip install -r requirements-train.txt                       # scikit-learn 1.5.2, training only
python3 -m scripts.build_panel                              # feature panel -> data/panel.csv
python3 -m scripts.fit_model --model extratrees --disjoint  # extratrees-v2, shipped
python3 -m scripts.fit_model --model extratrees             # extratrees-v1, all 500 (history)
python3 -m scripts.fit_model --validate-only [--capped]                 # ensemble A, months 13-15
python3 -m scripts.fit_model --targets fixed --validate-only [--capped] # ensemble B and C, 13-15
python3 -m scripts.measure_model_memory models/extratrees-v2.joblib
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

## Shipped: extratrees-v2, no deployed household in training

The deployed service serves 60 households (`data/public/`). They are a sample
of the same 500, under pseudonymised ids, so `extratrees-v1` below, fitted on
all 500, had seen every one of them. `extratrees-v2` is the same
configuration, same random_state, nothing re-tuned, refitted on target months
4–15 for the **440 households outside the slice**. The 60 were mapped back
through `scripts.minimise_extract.slice_alias`, the function that selects
them. The mapping was checked record for record against the committed slice
(35,263 records, identical) before fitting, and the training panel is
asserted to contain none of them.

**No household the deployed service serves was in training. Every forecast
it gives a live household is out-of-sample** in the household as well as the
month.

Holdout, months 16–18, scored twice:

**The 440 training households** (out-of-month, in-household), 1,320
household-months:

| forecaster | MAE | MAPE | medAPE | category MAE | mean signed error |
|---|---|---|---|---|---|
| blend | 8916.2 | 10.98% | 8.89% | 1933.4 | +881.6 |
| **extratrees-v2** (440) | **8319.7** | **10.13%** | **8.10%** | **1855.9** | **−22.1** |
| extratrees-v1 (all 500) | 8287.4 | 10.06% | 8.01% | 1855.0 | −28.3 |

| paired | MAE Δ (t) | MAPE Δ pp (t) | category MAE Δ (t) | wins |
|---|---|---|---|---|
| v2 vs blend | **−596.4 (−6.04)** | −0.85 (−7.58) | **−77.6 (−8.21)** | 721/1320 |
| v2 vs v1 | +32.3 (+1.22) | +0.07 (+2.08) | +0.9 (+0.35) | 646/1320 |

**Accuracy on the 440 is materially unchanged** by dropping 60 households
from training. MAE is 32.3 KES (0.4%) worse and not significant. Category MAE
is unchanged. MAPE is 0.07 points worse, with t = 2.08: nominally significant
over 1,320 pairs, but too small to matter. That is the whole cost of the
trade.

**The 60 deployed households** (out-of-month AND out-of-household), 180
household-months:

| forecaster | MAE | MAPE | medAPE | category MAE | mean signed error |
|---|---|---|---|---|---|
| blend | 9124.5 | 11.22% | 9.77% | 1869.1 | +402.7 |
| **extratrees-v2** | **9086.3** | **11.19%** | **9.56%** | **1823.0** | **+50.3** |
| extratrees-v1 (had seen them) | 9076.7 | 11.19% | 9.55% | 1816.4 | −108.4 |

| paired | MAE Δ (t) | MAPE Δ pp (t) | category MAE Δ (t) | wins |
|---|---|---|---|---|
| v2 vs blend | −38.2 (−0.16) | −0.03 (−0.10) | −46.2 (−1.99) | 88/180 |
| v2 vs v1 | +9.7 (+0.13) | +0.01 (+0.07) | +6.6 (+0.85) | 94/180 |

**On the deployed households the model is not shown to beat the blend on the
total.** The MAE gain is 38 KES with t = −0.16. The category gain is 46 KES,
with t = −1.99, on the edge of significance. Two things say this is the 60
households rather than the exclusion. First, v1, which trained on them, does
no better on them (v2 vs v1: +9.7, t 0.13). Second, 180 household-months is a
small sample. So holding the deployed households out cost nothing
measurable, but nor does this sample confirm the gain seen on the 440. The
live demo should be presented as the contract and the honesty mechanisms
working, not as evidence of accuracy.

---

## Before the disjoint refit: extratrees-v1 against the blend, holdout

Fitted on all 500 households. Replaced by v2, and kept here because it is the
model the selection and the holdout below describe.

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

`models/extratrees-v2.joblib` is **4.3 MB** (4,309,443 bytes). v1 was 4.5 MB,
the capped three-learner ensemble 6.4 MB and the unconstrained one 33.9 MB.
None of those is in the tree.

Resident memory of a fresh process that answers one `POST /forecast` through
the app, then loads the artefact and makes one prediction. Measured in the
service's own Docker image (Linux, arm64) with scikit-learn 1.5.2 added:

| data in the image | service alone | service + extratrees-v2 | peak | headroom on 512 MB |
|---|---|---|---|---|
| deployed 60-household slice | 107.3 MB | **190.3 MB** | 189.5 MB | ~322 MB |
| full 500-household extract | 160.1 MB | **209.9 MB** | 239.8 MB | ~272 MB at peak |

v1 measured 190.5 and 210.0 MB, the same within noise.

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

## The interval: split conformal

```bash
python3 -m scripts.calibrate_interval analyse            # months 13-15 only
python3 -m scripts.calibrate_interval write --scale relative
python3 -m scripts.calibrate_interval verify             # months 16-18; refuses a third run
```

The model gives a point forecast and nothing else, and the contract needs a
range. The blend's range comes from percentiles of the household's own past
totals, which measures how much the household varies, not how wrong a
forecast is. So the model's interval is calibrated on its residuals instead:
offsets taken from how wrong it was on months it had not been fitted on,
added to its point forecast. `app.forecaster.conformal_bounds` applies them,
in the calibration script and in `ExtraTreesForecaster` alike, so the
interval calibrated is the interval served.

**Calibration data.** The shipped model was trained on target months 4–15,
so its own residuals on 13–15 would be in-sample, and its guard refuses
those months anyway. The calibration model is the same configuration and
random_state, refitted on target months 4–12 for the same 440 households,
and scored on 13–15: 1,320 out-of-sample residuals. No deployed household is
involved. With three fewer months of training it should, if anything, err
wide.

**Relative, not KES, because the errors grow with the forecast.** On
months 13–15:

| predicted-total quintile | mean predicted | mean \|residual\| | \|residual\| / predicted | coverage, KES offsets | coverage, relative offsets |
|---|---|---|---|---|---|
| Q1 | 36,041 | 3,528 | 0.099 | 97.7% | 80.7% |
| Q2 | 48,674 | 5,386 | 0.111 | 94.3% | 77.3% |
| Q3 | 66,943 | 8,069 | 0.122 | 88.3% | 83.7% |
| Q4 | 94,238 | 9,641 | 0.102 | 68.9% | 79.2% |
| Q5 | 129,495 | 13,443 | 0.104 | 51.5% | 79.9% |

The absolute error roughly quadruples across the quintiles while the error
as a share of the forecast stays at 10–12% (Spearman 0.44 between predicted
total and |residual|). KES offsets (−12,133.8 / +10,754.9) reach 80% on
average by over-covering small households and covering only half of the
largest. Relative offsets (−15.7% / +15.5%) cover 77–84% in every quintile.
Both sets are recorded in `models/extratrees-v2.calibration.json`. The
offsets are conformal quantiles with the finite-sample correction, and the
lower bound is clipped at zero.

**Verified once on the holdout, failed, corrected once.** The fallback
was fixed in the calibration file before months 16–18 were read: if
coverage fell below 80% for either household group, recompute from the same
13–15 residuals at a 90% nominal level and verify once more.

| verification | interval | 440 trained | 60 deployed |
|---|---|---|---|
| 1 | relative, nominal 80% (−15.7% / +15.5%) | 80.5% | **78.9%** (142/180), fails |
| 2 | fallback, nominal 90% (−18.7% / +22.3%) | 90.8% | 89.4% |

The 60-household figure rests on 180 household-months, so its standard
error is about ±3 points. The 1.1-point shortfall is well within that, and
the 80% interval may well have been honest. But the rule was fixed in
advance, so the fallback is what ships. **The served interval is the
nominal-90% one, achieving about 90%.** It is a little wider than an 80%
interval needs to be. `ExtraTreesForecaster` reads the recorded verification
and serves the fallback because the first attempt failed and the second
passed. Had both failed, it would refuse to serve an interval at all. The
script refuses a third verification.

**Tree spread is not an interval.** The 10th–90th percentile of the 40
trees' individual totals covers 27.3% of outcomes on months 13–15, and 31.2%
and 26.1% on the holdout, at about a tenth of the point's width. The trees
disagree with each other far less than the forecast is wrong, because each
tree is fitted to the same data and their spread measures model variance:
how much the forest would change with a different random draw. It does not
measure the month-to-month noise in a household's spending, which is most
of the error. An interval built from it would claim 80% and deliver under a
third.

**Confidence is unchanged and describes the household.** It is the
baselines' formula, [1/(1+CV)] × [n/(n+3)], with CV taken over the
household's own monthly totals before the target month. A test asserts it
equals the blend's confidence for the same history. It measures how steady
the household has been, not how certain the model is; the interval carries
the model's uncertainty. The code says so where it is computed.

### The volatile flag no longer works with this interval

The flag fires when the range spans more than 60% of the point forecast.
**Under the conformal interval it never fires: 0 of 1,320 and 0 of 180 on
the holdout.** That is not a threshold that needs moving. With relative
offsets every interval is the same share of its forecast, 0.410 (0.312 at
80%); the zero clip never binds at −18.7%. So any threshold on that share fires
for every household or for none. The flag cannot tell a volatile household
from a steady one, and "MAE is larger where it fires" cannot be tested
because it does not fire. Tree spread never fires either.

The blend's flag, which is built from the household's own history, still
works where there is enough data. On the 440 it fires on 44 household-months
with MAE 11,903.5 against 8,813.1 where it does not. On the 60 it fires 5
times, with MAE 8,419.3 against 9,144.6, the wrong way round, but 5 cases
decide nothing. The obvious repair was to make the model's interval
household-specific. It was tried, on months 13–15 only, and it does not
work. The next section explains why.

### Normalised conformal does not rescue it

```bash
python3 -m scripts.calibrate_interval analyse-normalised    # months 13-15 only
```

Normalised, or locally weighted, conformal prediction divides each
residual by a household-specific scale term u before taking the quantile,
then multiplies back. That keeps the marginal coverage guarantee while
letting the width vary (Papadopoulos, Vovk & Gammerman, 2011; Lei, G'Sell,
Rinaldo, Tibshirani & Wasserman, 2018). Here the score is
|residual| / (point × u) and the interval is point × (1 ± q·u), with u
computed from the household's monthly totals before the target month only.
Four candidates for u were fixed before anything was measured: 1 (the
current interval), the CV of those totals, √(1 + 1/n) for history length,
and the two combined. Each was judged on months 13–15 at the served 90%
nominal level, on two criteria together: coverage holds, and span/point
varies enough for the 60% threshold to separate households.

| u | coverage | coverage by CV quintile (lowest → highest) | span/point: mean, sd | p10 / p50 / p90 | flag fires | MAE when the flag fires vs not | MAPE when the flag fires vs not |
|---|---|---|---|---|---|---|---|
| 1 | 90.0% | 88.3 / 89.4 / 88.6 / 93.2 / 90.5% | 0.400, 0.000 | 0.400 / 0.400 / 0.400 | 0 | — | — |
| √(1 + 1/n) | 90.1% | 88.6 / 89.4 / 88.6 / 93.2 / 90.5% | 0.399, 0.001 | 0.398 / 0.399 / 0.400 | 0 | — | — |
| CV | 90.1% | **75.0** / 86.0 / 92.8 / 97.7 / 98.9% | 0.556, 0.383 | 0.305 / 0.437 / 0.837 | 296 (22.4%) | 8,282.5 vs 7,935.6 | 10.20% vs 10.34% |
| CV × √(1 + 1/n) | 90.1% | **75.0** / 86.0 / 92.8 / 97.7 / 98.9% | 0.556, 0.383 | 0.305 / 0.436 / 0.838 | 295 (22.3%) | 8,293.1 vs 7,932.9 | 10.21% vs 10.33% |

- **History length cannot vary the width.** Every calibration household has
  12, 13 or 14 months, and which one depends only on the target month.
- **CV varies the width, but not with the error.** The spread is real (sd
  0.383), and the flag fires on 22% of household-months. But the model's
  relative error is unrelated to a household's CV: Spearman −0.035 between
  CV and |residual| / point. So the width moves without any matching change
  in error:
  - the steadiest fifth of households are covered 75%, below the 80% in
    NFR-01, and the most volatile fifth 98.9%;
  - where the flag fires, KES error is 4% higher (Welch t = +0.50), only
    because those households forecast larger totals (78,178 against 74,182);
  - relative error is slightly lower there (t = −0.25).
  The flag would mark households whose past spending varied, not forecasts
  that are less reliable.

**So no scale definition makes the 60% threshold discriminate while
holding coverage.** Following the rule set before this was tried, the
holdout was not opened for it and nothing was adopted. The served interval
is unchanged.

**The finding: FR-03's flag is incompatible with a calibrated interval for
this model.** The rule is "the range spans more than 60% of the point
forecast". That is a fixed fraction of the point, and a calibrated interval
is as wide as the model's errors. This model's errors scale with the point
and with nothing else measured here. So the honest interval is a constant
share of the point, and no threshold on that share can separate households.
Making the width vary on purpose, as the CV scaling does, buys a flag that
fires by breaking coverage for steady households, and the flagged forecasts
are not in fact worse. The blend's flag discriminated (MAE 11,903.5 against
8,813.1 on the 440) because the blend's errors are larger for volatile
households. The model has removed that relationship, and with it the thing
the flag was detecting.

**Proposed change to FR-03, for decision.** Stop defining the flag as
interval width over the point. Either:

1. **define it on the household, and say so.** For example: "the
   household's monthly spending has varied by more than X% (CV of prior
   totals)". This is true and checkable, with X chosen on months 13–15 to a
   stated firing rate. It makes no claim about forecast error, because none
   holds. The response contract's `riskFlag` value is unchanged; what
   changes is FR-03's wording and what Chapter 5 claims it means; or
2. **drop the volatile value for the model's forecasts.** Keep
   `insufficient_history`, and let the interval alone carry uncertainty,
   since the interval is calibrated and the flag would not be.

Either needs FR-03 amended before the model is wired in. Shipping the
current rule would mean a flag that never fires, and tuning a threshold
until it does would claim something that is not true.

References:
Papadopoulos, H., Vovk, V. and Gammerman, A. (2011). Regression conformal
prediction with nearest neighbours. *Journal of Artificial Intelligence
Research*, 40, 815–840.
Lei, J., G'Sell, M., Rinaldo, A., Tibshirani, R. J. and Wasserman, L. (2018).
Distribution-free predictive inference for regression. *Journal of the
American Statistical Association*, 113(523), 1094–1111.

### For Chapter 5

Holdout, months 16–18. Synthetic. Width is the mean of (high − low) / point.
"MAE when the flag fires" compares household-months where the volatile flag
fires against those where it does not.

| interval | coverage, 440 trained (n 1,320) | coverage, 60 deployed (n 180) | mean width / point (440 / 60) | flag fires (440 / 60) | MAE when the flag fires vs not, 440 | MAE when the flag fires vs not, 60 |
|---|---|---|---|---|---|---|
| blend (history percentiles + slack) | 91.8% | 89.4% | 0.433 / 0.424 | 44 / 5 | 11,903.5 vs 8,813.1 | 8,419.3 vs 9,144.6 |
| conformal, nominal 80% (failed verification) | 80.5% | 78.9% | 0.312 / 0.312 | 0 / 0 | — | — |
| **conformal, nominal 90% (served)** | **90.8%** | **89.4%** | **0.410 / 0.410** | 0 / 0 | — | — |
| tree spread, p10–p90 of 40 trees | 31.2% | 26.1% | 0.101 / 0.103 | 0 / 0 | — | — |

The 60-household coverage figures rest on 180 observations, so each has a
standard error of about ±2–3 points.

---

## What this does not show

- **The holdout has been read many times.** SANDBOX_RESULTS.md scored months
  16–18 to confirm the blend's weight and several rejected alternatives, and
  this work read them for variant A and its parts, including the
  configuration that was later chosen. Nothing was tuned on them, but they
  are no longer an independent test. The validation split is the stronger
  evidence.
- **The volatile flag is inert with the model's interval** (above). Wiring
  needs a household-specific basis for it.
- **Synthetic data, one extract.** 500 generated households over 18 months.
- **The deployed households are out-of-sample, but they are only 60.** On
  them the model is not shown to beat the blend on the total (t −0.16). The
  demo shows the contract and the honesty mechanisms working, not accuracy.
- **`has_budget` is constant.** Every candidate category has a budget row in
  this extract, so the feature carries nothing. It is kept so the feature
  list does not depend on the extract.

## Reproducibility

`models/extratrees-v2.joblib` and its manifest are tracked. `.gitignore`
excludes the contents of `models/` and un-ignores `*.joblib` and
`*.manifest.json`. CI's secrets check exempts this one artefact by exact path
and still fails on any other `.joblib`. The manifest records:

- `git_head` 5f886bc, the commit that wrote this manifest, with no
  uncommitted tracked changes. The artefact was first written at 9f6e020;
  the regeneration at 5f886bc only added the selection record, and its bytes
  are identical;
- the selection evidence: the configuration was fixed by extratrees-v1's
  validation run (dc48878, committed in 87b9a0a) and not re-selected, with
  that run's months 13–15 figures (MAE 7848.5, category MAE 1779.4, signed
  error +346.7);
- 440 training households, 57,000 training rows, and
  `deployed_households_in_training: 0`;
- the last training month (2026-06) and the ordered list of 31 features;
- the installed versions: scikit-learn 1.5.2, pandas 2.2.3, numpy 2.1.1,
  joblib 1.6.0;
- random_state 37 and the artefact's SHA-256, `b8b88235…bf0941c`;
- both holdout scorings above.

Two fits of v2 in a fresh process give identical bytes, matching that hash.
One anomaly is unexplained. The very first v2 run, at the previous commit,
wrote a file with a different hash (`87e0f3b4…`) but identical scores to
the last digit. It was deleted before the rerun, so the two could not be
compared.

v1 is no longer in the tree. It is in history at 87b9a0a, and
`--model extratrees` regenerates it byte for byte (`5ec309c3…88055a`), which
was checked. The disjoint run refits v1 in memory for its comparison.

The variant A runs (`fit_model` without `--model extratrees`) still write
`models/ensemble-v1*.joblib`. Those are history, not something to commit;
stage model files by explicit path, never `git add models/`.

## What shipping would take

Steps 1–4 are done; the service does not use the model yet.

1. **Done.** `scikit-learn==1.5.2` and `joblib==1.6.0`, the versions the
   manifest records, are in `requirements.txt`. The service image goes from
   492 MB to 803 MB. The build should still be quick: PyPI has a 1.5.2 wheel
   for CPython 3.11 on manylinux x86-64, which is what `python:3.11-slim` runs.
   The six-minute compile seen on Render was most likely the static site's
   builder installing `requirements.txt` on its default Python 3.14, for
   which 1.5.2 has no wheel. That is an inference; no Render build log
   confirms it.
2. **Done.** `app.forecaster.ExtraTreesForecaster` loads
   `models/extratrees-v2.joblib` once and refuses it unless its SHA-256
   matches the manifest and the manifest's 31 features are
   `app.features.FEATURES` in order. It refuses any target month at or before
   `trained_through` (2026-06). It keeps no per-household state between
   calls. Scored through `evaluate`, it reproduces the manifest's holdout
   figures exactly for both household groups.
3. **Done.** The features are defined once, in `app/features.py`.
   `scripts/build_panel.py` builds the training panel from them and the
   forecaster builds each request's features from them. A refit through the
   moved code reproduces the artefact byte for byte.
4. **Done.** Interval and confidence: split-conformal interval at nominal
   90% after the 80% one failed on the 60 deployed households, and the
   household-steadiness confidence (see "The interval").
5. Amend FR-03 (see "Normalised conformal does not rescue it"), then wire
   the model into `app/service.py`. Under the calibrated interval the 60%
   width rule never fires, and no household-specific width fixes that
   honestly.
