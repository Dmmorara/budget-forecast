# Model — what beat the baseline, and what did not

Step 3 of the partner's order of work. The bar is [`BASELINE.md`](BASELINE.md).

```bash
python3 -m scripts.compare_model          # 12 populations, both holdouts
```

**Data:** synthetic. 12 independent populations, seeds 37–48, 28 households
each, 30 months. No real or staging data has been used. Every number here must
be re-measured once the sandbox extract is in `data/`.

**Shipped:** `TwoShapeForecaster` with day-count normalisation and the
fixed/habitual split. Seasonality, drift and step detection were implemented,
measured and **rejected**.

---

## Result

Paired against `baseline:trailing_median_6m` on identical populations.
Negative is better. `t` is a one-sample t statistic on the 12 paired
differences; |t| > 2.2 is significant at 5%. `wins` is a sign test.

| | holdout 3 months | holdout 12 months |
|---|---|---|
| MAE | **−97.7** (sd 106, t −3.20, 10/12) | **−37.1** (sd 50, t −2.58, 10/12) |
| MAPE | −0.14 pp (t −1.82, 8/12) | −0.11 pp (t −2.71, 10/12) |
| category MAE | **−30.3** (t −6.94, 11/12) | **−16.9** (t −7.22, 12/12) |
| vs `last_month` | −1344.9 (t −8.78, **12/12**) | −1464.5 (t −19.83, **12/12**) |
| interval coverage | 86.3% (base 82.9%) | 83.9% (base 82.1%) |
| share of removable error captured | 19.8% | 4.4% |

**The most robust finding is the category breakdown**, not the total: better on
12 populations out of 12 with t = −7.22. That is the number U-CS 38 should care
about, because it consumes `breakdown` rather than `estimatedTotal` alone.

**Two bars, two verdicts.** The project README's bar is "beats *same as last
month*", and the model clears it by roughly 1,400 KES on every population
tested — t = −19.83 is not a marginal result. The trailing-median baseline
introduced in `BASELINE.md` is a much stronger opponent, and that one is
cleared narrowly. Both statements belong in the report; quoting only the first
would overstate the work and only the second would understate it.

---

## How this was nearly reported wrongly

Every component was first measured on **one** synthetic population, seed 37,
and on that population every single one of them appeared to work. The table
being assembled read:

```
day+fixed+seasonal     MAE 4772.29   vs base -190.78   captured 20.0%
  (3-month holdout)    MAE 4874.41   vs base -263.45   captured 35.2%
```

That was about to be written up as the headline. Re-measured across 12
populations, the same configuration is **not an improvement at all**: mean MAE
+14.0 with t = 0.46, better on 5 populations out of 12.

The cause is sample size, and it was knowable in advance. One population is 28
households; over a 12-month holdout that is 300 forecasts, and the standard
deviation of the MAE difference between two forecasters on a single population
is 50–110 KES. The component effects being chased are around 40 KES. They were
never detectable on one population — and a single-population ablation will
always produce a winner, because something has to come top.

What the seed sweep cost: a few minutes. What it changed: three of four
components rejected, and the headline claim cut from 35% of removable error to
between 4% and 20%.

---

## Ablation

12 populations, 12-month holdout, paired against the baseline.

| variant | MAE Δ | t | wins | catMAE Δ | wins | verdict |
|---|---|---|---|---|---|---|
| day-count only | +16.5 | 0.88 | 7/12 | +18.9 | 0/12 | not alone |
| fixed split only | −13.5 | −2.88 | 8/12 | −9.8 | 12/12 | keep |
| **day-count + fixed split** | **−37.1** | **−2.58** | **10/12** | **−16.9** | **12/12** | **shipped** |
| + seasonality | +14.0 | 0.46 | 5/12 | +16.3 | 6/12 | rejected |
| seasonality alone | +112.9 | **+3.38** | 2/12 | +69.3 | 0/12 | rejected |

### Day-count normalisation only works with the fixed split

Habitual spend accrues per day — a 28-day February holds about three fewer
commuting days than a 31-day March — so a median over raw monthly totals
carries that error permanently.

But applied on its own it makes the breakdown **worse on 12 populations out of
12**, because it also scales rent. Rent does not depend on how many Tuesdays a
month has. Only once the fixed split has taken fixed charges out of the series
does day-count normalisation pay. Neither component is an improvement in
isolation on the breakdown; together they are the shipped model. This is the
clearest argument in the project for the two-shape architecture, and it came
out of the measurement rather than the design.

### Seasonality — rejected, and this is the instructive one

Significantly **worse** than doing nothing: +112.9 KES MAE with t = +3.38, and
worse on the breakdown on 12 populations out of 12.

The seasonal structure is genuinely there — the generator puts a 1.35×
December on food and 1.5× on personal spend. It is simply **not estimable from
this much history**. Twelve monthly factors from 18–27 months of data means one
or two observations per factor, and the shrinkage term let two observations
carry 57% of their raw signal, which is far too generous. The correction is
real, the data cannot support it, and adding it injects more variance than the
bias it removes.

Two secondary findings worth recording:

The **decomposition order mattered enormously.** Applying the seasonal factor
only at the end, leaving seasonality inside the series from which the level and
any step were estimated, cost 310 KES of MAE on the three-month holdout — the
step detector read December as a permanent change of circumstances. Removing
calendar effects *before* estimating the household's level nearly doubled
seasonality's apparent contribution on seed 37. It still did not survive the
seed sweep.

The **three-month holdout cannot test seasonality at all.** Those three months
are July, August and September, which carry almost no seasonal effect in this
population. Any seasonal result measured on that window is uninformative rather
than negative, which is why both holdout lengths are reported throughout.

### Drift — rejected

R²-gated extrapolation of recent growth. The MAE difference **changes sign
across populations** (mean −6.4 and −1.8 on the two holdout lengths, never
consistently negative) while the category breakdown is worse on all 8 runs
measured. An ungated version was clearly harmful, by 141–211 KES depending on
household profile; gating by explained variance made it merely
indistinguishable from nothing.

### Step detection on habitual spend — rejected

Shortening the level window when the habitual level shifts, aimed at the
quarter of households that move or change commute. Costs around 184 KES of MAE
even after the decomposition order was corrected. The mechanism it targets is
real and present in the data; estimating a step from three months of a noisy
series costs more in variance than it recovers in bias.

Note that step handling **was** kept for fixed obligations, where it works: a
rent increase appears in the next forecast rather than being averaged with six
months of the old rent. `test_fixed_charge_absorbs_a_step_quickly` asserts it.

---

## Intervals

Coverage 83.9% (12-month) and 86.3% (3-month) against a nominal 80%.

The interval is a **conformal quantile** of the model's own one-step-ahead
residuals, replayed over the household's history: the k-th smallest absolute
residual with k = ⌈0.8(n+1)⌉. That guarantees coverage of at least 80%
regardless of the error distribution, which matters because spending residuals
are skewed and nothing here justifies assuming normality. Landing slightly
above nominal is the guarantee working, not a miscalibration.

The first version took the empirical 10th and 90th percentiles of those
residuals and achieved **66.7%** against the same nominal 80%. Small-sample
percentiles sit inside the true quantiles, so the interval was confidently too
narrow — the worst failure available to a confidence range, because it errs in
the direction that looks good.

The model's interval is wider than the baseline's (mean relative width 0.53
against 0.47) while its point forecast is better. That is the honest trade:
the baseline's interval was built from the spread of monthly totals, which
includes variation the model can now explain, and it reached its coverage
partly by accident.

---

## Limitations

**Synthetic data only.** Every figure above describes a population generated by
`app/synthetic.py`. The architecture is grounded in real behaviour — the
two-shape finding came out of real M-Pesa statements in Phase 1 — but the
coefficients, the noise floor and all of these margins are synthetic. The
staging extract (Issue #6) is still outstanding, and the model must be
re-measured against it before any of these numbers appear in the report as
evidence about real households.

**The margin over the trailing median is small.** 4.4% of removable error on the
12-month holdout. A reader should not be left with the impression that the
model transforms the forecast; it does not. Most of the error that remains is
process noise no forecaster can reach, and `BASELINE.md` quantifies that.

**Only four household profiles exist.** 28 households drawn from four templates
is not a population. The seed sweep controls for sampling noise within that
design; it cannot tell us how the model behaves on household types the
generator does not contain.

**The rejected components may be wrong rather than the ideas.** Seasonality in
particular would likely pay on three or more years of history. The finding is
"not estimable from 18–27 months", not "seasonality does not exist" — and the
code is retained with its flag so the question can be re-asked when the real
extract reveals how much history the platform actually holds.
