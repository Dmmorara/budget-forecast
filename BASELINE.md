# Baseline — the number to beat

> *"Baseline. The dumbest thing that works, returned from `app/service.py`. Measure it and
> **write the number down.** You are not allowed to build a model before this exists."*
> — project README, order of work

This is that number. Reproduce it with:

```bash
python3 -m scripts.measure_baseline
```

**Data:** synthetic, seed 37 — 67,123 transactions, 28 households, 30 months.
No real or staging data has been used yet. Every figure below is labelled synthetic
and must be re-measured once the sandbox extract is in `data/`.

**Split:** the last 3 calendar months, held out globally, rolling origin. To forecast
month *M* the forecaster receives history strictly before *M* and nothing else. This is
asserted mechanically by `test_harness_never_shows_the_target_month`, not merely intended.

---

## Headline

| Forecaster | MAE | MAPE | median APE | category MAE | coverage | n | declined |
|---|---|---|---|---|---|---|---|
| `last_month` (the README's bar) | 6158.5 | 18.35% | 12.39% | 2153.3 | — | 75 | 6 |
| `trailing_median_3m` | 5802.1 | 14.96% | 8.28% | 1923.9 | 81.3% | 75 | 6 |
| **`trailing_median_6m`** ← **in the service** | **5137.9** | **13.79%** | **9.24%** | **1718.9** | **80.0%** | **75** | **6** |
| `trailing_median_all` | 5850.2 | 15.11% | 13.81% | 1781.5 | 78.7% | 75 | 6 |
| *irreducible noise floor* | *4389.7* | *12.74%* | *8.81%* | — | — | — | — |

**The model must beat MAE 5137.9 / MAPE 13.79% on these same held-out months.**

The six-month window is in the service because it wins on MAE, MAPE and category MAE.
The three-month window has a better *median* APE (8.28% vs 9.24%) while being worse on the
mean — it is more accurate for the typical household and less robust in the tail. Reported
rather than resolved, because which one matters depends on whether U-CS 38 is advising a
median household or guarding against a bad month.

## The noise floor, and why it is here

`generate()` returns the latent monthly expectation each household-month was drawn from
before noise was added. A perfect forecaster would return exactly that and still be wrong
by whatever the process injected. That gap is **MAE 4389.7**, and no forecaster can go
below it.

Reporting a model's error without this number beside it invites the reader to believe the
remaining error is a modelling failure. It is not. **Only 748.2 KES — 14.6% of the
baseline's error — is removable at all.** A model that cuts MAE to 4400 has extracted
essentially all available signal; one that claims 2000 has a leak.

Real data has no published truth, so this floor cannot be computed on the sandbox extract.
That is a limitation of the real-data evaluation worth stating in the report, not a reason
to skip it here.

## Where the removable error lives

| Profile | n | MAE | MAPE | Noise floor | Removable | % of own error |
|---|---|---|---|---|---|---|
| steady_tenant | 30 | 3410.6 | 7.4% | 2887.7 | 522.9 | **15.3%** |
| student | 30 | 2059.0 | 13.8% | 1840.9 | 218.1 | 10.6% |
| volatile | 15 | 14750.2 | 26.6% | 13592.9 | 1157.2 | 7.8% |

Volatile households hold the largest absolute error and the least removable share of it.
**The correct response for them is a wide interval and the `volatile` flag, not a better
point forecast** — pushing on their MAE is chasing noise. The households where modelling
can actually win are the steady tenants, whose removable error comes from rent escalation
steps and seasonality, both of which a trailing window structurally cannot track.

## Honest intervals

The interval is the 10th–90th percentile of the household's own monthly totals, widened
when there are few months. Nominal coverage 80%; **achieved 80.0%**.

An earlier, stationary version of the generator produced 94.7% coverage against the same
nominal 80% — conservative rather than dishonest, but the stated level was still wrong.
Coverage is now asserted two-sided in `test_interval_coverage_is_in_the_honest_range`:
far below 80% is a lie, far above is uninformative padding, and both are failures.

## The `volatile` flag

Fires on 10 of 75 household-months. Those months average **20.23% APE against 12.80% for
unflagged months** — 1.6× worse, which is what a reliability warning is supposed to
predict.

Defined on interval width relative to the point forecast, not on a coefficient of
variation. The CV version did not work and the reason is recorded in `app/forecaster.py`:
no threshold separated the groups, because a large steady rent dilutes the CV of the
total and made erratic spenders look calm.

## `insufficient_history`

6 household-months declined, all from households with fewer than 3 months of history.
Declined months are excluded from every error metric above and reported separately — a
service that answers nothing would otherwise score a perfect zero error and look
excellent for it.

---

## A finding about the test itself

The first version of the generator drew every household from **stationary** parameters.
The 6-month trailing median then scored **10.16% MAPE against a floor of 10.20%** — it had
saturated the data completely, because a trailing median is the statistically optimal
estimator of a stationary process. The test was unwinnable by construction.

Had the baseline not been measured first, the next sprint would have been spent tuning a
model against an unbeatable benchmark and concluding the architecture was worthless. The
generator now carries the non-stationarity real household spend has — annual seasonality,
compounding drift, and step changes from rent escalation and moves — which are precisely
the structures a trailing window cannot track. The reasoning is in
`app/synthetic.py`, and `test_generator_is_non_stationary` guards against drifting back.

This is the baseline-first rule paying for itself before a line of model code was written.
