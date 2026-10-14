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

## Reproducing

```bash
python -m scripts.fetch_data      # needs .env; data/ is gitignored
pytest -q
```

The autocorrelation and oracle figures come from the analysis in this
document's history rather than a committed script; `scripts/analyse_sandbox.py`
is the follow-up that should make them reproducible.
