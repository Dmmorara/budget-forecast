# Results on the staging sandbox

The first evaluation against platform data rather than data this project
generated. It overturns the synthetic result, and the reason it does is the
most useful finding in the project so far.

**Data.** `data/spending_records.csv` from
`/api/v1/sandbox/dataset/`, fetched 14 October 2026. 298,536 records, 500
households, 17 categories, 18 months (Apr 2025 – Sep 2026). Last 3 months held
out; 15 months of training history per household.

**Synthetic.** The platform supervisor confirmed the sandbox is generated data:
*"All synthetic, say so in the report."* `isSynthetic` stays `true` on every
response, and `app.data.provenance()` reports `platform-sandbox` to distinguish
it from this project's own generator. **No figure here describes a real
household.**

---

## Headline

| forecaster | MAE | MAPE | catMAE |
|---|---|---|---|
| `last_month` | 12290.5 | 15.53% | 2848.5 |
| `trailing_median_3m` | 9968.2 | 11.95% | 2313.4 |
| `trailing_median_6m` (the synthetic winner) | 9413.5 | 11.04% | 2102.4 |
| `two_shape` model | 9352.2 | 11.03% | 2121.6 |
| **`trailing_mean_all`** ← **shipped** | **9011.6** | **10.99%** | **1948.6** |
| *best constant fitted on the test months — unreachable* | *7163.9* | *8.85%* | *1482.8* |

Paired over all 1,500 held-out household-months, against `trailing_median_6m`:

| | MAE Δ | t | better on |
|---|---|---|---|
| `two_shape` model | −61.2 | −1.04 | 50.7% — indistinguishable |
| `two_shape` **catMAE** | **+19.2** | **+5.25** | 45.6% — **significantly worse** |
| `trailing_mean_all` | **−401.8** | **−2.25** | 54.2% |
| `trailing_mean_all` **catMAE** | **−153.7** | **−9.62** | **67.0%** |

---

## The model does not transfer, and the reason is not a bug

The two-shape model — validated across 12 synthetic populations, where it beat
the trailing median on the category breakdown on 12 of 12 — is **worse** on the
sandbox, significantly so on the breakdown, and worse on **every one of the ten
populated categories** without exception.

Three measurements explain it, in order of depth.

**The fixed/habitual split stops firing.** `_is_fixed` classifies Rent as a
fixed obligation in 5% of sandbox households and Transport in 16%, against
near-100% for rent on synthetic data. `FIXED_MAX_CV = 0.12` was fitted to a
generator whose rent had *zero* amount variance. Real sandbox rent varies more,
so almost everything falls through to the habitual path and gets day-count
normalised — including Rent, School Fees and Savings, none of which accrue per
day. That is precisely the configuration the synthetic sweep had already
flagged as harmful: day-count alone was worse on the breakdown on 12
populations of 12, rescued only by the fixed split.

**No threshold rescues it.** Sweeping `FIXED_MAX_CV` from 0.12 to 1.00 on a
*validation* split — months 13–15, inside the training period, with the holdout
untouched — every configuration scored worse than the baseline, and loosening
the threshold made it monotonically worse. The best validation setting was
still +2.2 catMAE against the baseline. The constant was not the problem.

**The data has no temporal structure at all.** Lag-1 autocorrelation of monthly
spend per household-category is **−0.07**. Months are independent draws around
a constant mean. There is no trend, no seasonality and no persistence for any
forecaster to exploit — so a model correcting for month length, seasonality,
drift or step changes is correcting for structure that is not there, and every
correction it makes adds variance while removing no bias.

## Why the mean, and why that is not a model

Under an i.i.d. process the sample mean over **all** available history is the
minimum-variance estimator of the next observation. A median over a 6-month
window is handicapped twice: less efficient than the mean for roughly symmetric
noise, and discarding two thirds of the evidence. Replacing it recovers 402 KES
of MAE and 154 of catMAE, and lands essentially on the best constant obtainable
from training history.

This is an estimator chosen to match a measured property of the data, not a
model. Reporting it as a modelling achievement would be dishonest.

**The median remains the right default for real spending.** One anomalous month
moves a mean and not a median, and real M-Pesa data is heavy-tailed in a way
this sandbox is not. `TrailingMedianForecaster` is retained, and the choice
between them should be re-made against any genuinely real extract rather than
inherited from this result.

## What is left

9011.6 against an unreachable 7163.9 means roughly **79% of the remaining error
is irreducible** under any constant-mean model. The gap between the shipped
forecaster and the best constant obtainable from history is now nearly closed.

---

## The budget is a better signal than the history

The largest single improvement in the project, and it comes from a column
rather than a model.

`budget_categories.csv` carries `allocated_kes` — what the household budgeted
for a category. Two properties make it valuable:

- It is **constant** per household-category across all 18 months. 100% of the
  5,399 pairs have a single distinct value, so using it to forecast any month
  reveals nothing about that month. No leakage.
- It correlates **0.80** with actual spend, giving MAE 1,878 against a mean
  actual of 8,366 — on its own, roughly as good as the entire spending history.

So the budget and the history are two independent, noisy estimates of the same
quantity, and averaging two such estimates beats either. Blending them, with
the weight chosen on a validation split (train months 1-12, test 13-15) and
confirmed on the untouched holdout:

| forecaster | MAE | catMAE |
|---|---|---|
| history alone (`trailing_mean_all`) | 9011.6 | 1948.6 |
| **80% history + 20% budget** ← shipped | **8941.2** | **1925.7** |

Paired over 1,500 held-out household-months against history alone:

| | delta | t |
|---|---|---|
| MAE | **−70.4** | **−2.24** |
| category MAE | **−22.9** | **−8.26** |

Both significant. The weight was **not** chosen by reading the holdout:
validation preferred 0.8 for total error and 0.4 for category error, the two
metrics disagreed, and the contract's primary field decided it. The holdout
then reproduced the same preference independently.

### Why this is the direction the data supports

The sandbox models a platform where **households declare budgets and spend
noisily around them**. That is why the budget predicts spend, why history adds
little beyond estimating the same mean, and why no temporal model helps: spend
is generated from a constant, not from a habit.

It also suggests the more useful product is budget *adherence* rather than
forecast. Given `allocated` and `actual`, "you are tracking 12% above your
Groceries budget with nine days left" is computable and actionable. "You will
spend 71,209 next month" is neither, when the honest interval is ±25%.

## Dependants carry no signal

`dependants.csv` holds 1,007 dependants across 401 of the 500 households, one
to four each, with the five relationship types almost perfectly evenly split
(195-209 each). `family_group_id` yields 401 groups, **none spanning more than
one household**, so it duplicates `user_profile_id` in this extract.

It predicts nothing:

```
corr(n_dependants, monthly spend)     -0.0088
corr(n_dependants, declared budget)   -0.0117
```

Every natural hypothesis fails too — has-a-CHILD against School Fees gives
t = 0.95, has-a-PARENT against Medical t = -1.67, has-a-SPOUSE against
Groceries t = -0.11. With 500 households those are indistinguishable from
zero. A household with four dependants does not even *budget* more than one
with none, which is the most generous test available since a budget is a
declared intention rather than a noisy outcome.

This matters less for U-CS 37 than for **U-CS 43 (dependant-costs)**, whose
entire premise is that dependants drive cost. In this sandbox they do not, by
construction.

## The finding that matters most

**The sandbox cannot test this project's central hypothesis.**

U-CS 37 exists because household spending is habitual — that people pay fares
at the same times for the same amounts, that rent recurs, that obligations are
foreseeable. Phase 1 found exactly that in real M-Pesa statements: 7 payees with
fixed monthly obligations, and 130 transport payees forming habitual
category-level spend.

The sandbox contains none of it. Category counts are near-uniform across seven
of the ten populated categories (36,333 to 36,862), `description` is templated
as `"<Category> payment"`, the four payment sources are evenly split, aggregate
monthly spend is almost constant, and lag-1 autocorrelation is zero. It is a
well-formed dataset for exercising the API contract, the schema and the service
— and it is structurally incapable of showing whether spending is predictable,
because its spending was generated without the property being tested.

So three claims must be kept apart in the report:

1. **On the sandbox, no temporal model beats a constant.** Demonstrated here,
   with the autocorrelation measurement as the reason.
2. **The two-shape architecture is unvalidated, not refuted.** It failed on
   data containing none of the structure it was built to capture. That is weak
   evidence against it.
3. **The hypothesis that real household spending is forecastable remains
   untested.** Phase 1's M-Pesa statements are still the only real spending
   data this project has touched, and they were never evaluated for forecast
   accuracy — only for classification.

This is worth raising with both the supervisor and Webmasters. A forecasting
use case evaluated solely on a sandbox with no temporal structure can produce a
working, well-tested service whose central claim has never been examined.

## Recurrence is a timing property, not an amount property

Investigated after the question was raised directly: should recurrence be
judged on timing, payee and history rather than on amount consistency? The
sandbox can answer it, because `budget_categories.csv` carries the platform's
own `is_recurring` label — 4,000 recurring household-category pairs against
1,334 non-recurring.

| detector | precision | recall | F1 |
|---|---|---|---|
| amount CV — what `_is_fixed` used | 0.974 | **0.085** | 0.156 |
| **presence ≥ 90% of months** | **1.000** | **1.000** | **1.000** |
| interval (gap) CV < 0.5 | 1.000 | 0.107 | 0.194 |
| day-of-month concentration > 0.8 | 0.000 | 0.000 | 0.000 |

The amount-based detector finds **8.5%** of recurring obligations. Presence
finds all of them with no false positives: every recurring pair appears in all
18 months, every non-recurring one in at most 14.

The decisive number is the separation itself. Median amount CV is **0.231 for
non-recurring pairs and 0.240 for recurring ones** — indistinguishable. Amount
variability carries no information about whether something recurs. A rent that
changes every month recurs exactly as reliably as one that does not, and the
premise behind the original detector was simply false.

Day-of-month concentration scores zero only because these are *category
aggregates* containing many transactions spread across the month. At payee
grain — Phase 1's problem — it is informative, which is why Phase 1's
`RecurrenceDetector` used interval regularity. **The right timing signal depends
on the grain**, and collapsing a payee-level detector onto category aggregates
without re-deriving it was the original mistake.

`model.py` now separates the two properties, because they answer different
questions and a category may have either, both or neither:

- `_is_recurring` — does it happen every month? Decides **whether** to forecast.
  Rent, Transport and Groceries all qualify.
- `_is_constant` — is the amount steady? Decides **how** to level it. Rent
  qualifies; Transport does not.

### It does not improve the forecast on this data

Gating sporadic categories toward zero, with the threshold chosen on a
validation split and confirmed on the untouched holdout:

| | MAE Δ | t | catMAE Δ | t | breakdown better on |
|---|---|---|---|---|---|
| gate at 25% presence | −76.2 | −3.74 | **+106.0** | **+19.14** | 4.3% |
| gate at 50% presence | −95.2 | −1.61 | **+227.5** | **+21.79** | 5.8% |

A small total-MAE gain bought by badly damaging the breakdown, which is what
U-CS 38 consumes. Rejected.

The reason is the same one that defeats every other model here: knowing a
category is sporadic says nothing about **when** it will occur, because
occurrence in the sandbox is independent month to month. The detector is
correct and the data gives it nothing to exploit.

That distinction matters for the report. This is not evidence that recurrence
detection is useless — it is evidence that it cannot be demonstrated on data
without recurrence structure. On real M-Pesa statements, where Phase 1 found 7
payees with genuine fixed monthly obligations, the same detector has something
to find. **That remains untested.**

## Reproducing

```bash
python -m scripts.fetch_data      # needs .env; data/ is gitignored
pytest -q
```

The autocorrelation and oracle figures come from the analysis in this
document's history rather than a committed script; `scripts/analyse_sandbox.py`
is the follow-up that should make them reproducible.
