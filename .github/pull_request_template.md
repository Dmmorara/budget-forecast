Closes #

## What changed

<!-- One paragraph. What a reviewer needs to know before reading the diff. -->

## Measurement

<!--
Required when this touches forecast accuracy. Delete the table only if the
change cannot affect it (docs, CI, naming).

Reproduce with: python3 -m scripts.measure_baseline
-->

| | MAE | MAPE | category MAE | coverage |
|---|---|---|---|---|
| before | | | | |
| after | | | | |
| noise floor | 4389.7 | 12.74% | — | — |

Baseline to beat: **MAE 5137.9 / MAPE 13.79%** (see `BASELINE.md`).

## What I chose not to do

<!-- Scope deliberately left out, and why. Keeps the next reader from
     assuming it was missed. -->

## Checks

- [ ] `pytest -q` passes locally
- [ ] No secrets, `.env`, or data extracts in the diff
- [ ] Contract in `app/schemas.py` unchanged, **or** the change is additive and
      Benjamin has been told for the Team Integration Map
- [ ] `BASELINE.md` updated if the measured numbers moved
