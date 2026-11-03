# Version-control runbook — U-CS 37 `budget-forecast`

Everything needed to stand the repository up and land the work already written
as five reviewed pull requests, each with a green CI check.

Why it is staged rather than pushed in one commit: Section 5.5 asks for
evidence of issues, branches, focused commits, reviews and merge decisions.
One commit containing five units of work can demonstrate none of those. The
work below is genuinely five separable changes, so it lands as five.

**This does not backdate anything.** Every commit is dated when you run it, and
Section 5.5 should say plainly that the earlier model-development phase in
`Wasaa_Lifestyle` predates the partner's workflow rules. That is a true
sentence and a far better one than a fabricated history, which commit
timestamps and the reflog would expose anyway.

Run these in the macOS Terminal (zsh).

---

## 0 · Prerequisites

```bash
brew install gh
gh auth login          # choose GitHub.com → HTTPS → browser
gh auth status
```

**Branch protection on a private repo needs a paid plan.** You are a Strathmore
student, so apply for the GitHub Student Developer Pack at
<https://education.github.com/pack> — it grants GitHub Pro free, which enables
branch protection on private repositories. Until it is approved, do steps 1–8
without protection; the pull-request workflow still works, and step 2 can be
applied retroactively at any time.

---

## 1 · Create the repository and commit the partner's skeleton

The first commit is the skeleton exactly as Webmasters supplied it, so the
history shows clearly which code was given and which is yours.

```bash
cd ~/Documents/ICS2_Project
mkdir budget-forecast && cd budget-forecast

cp -R ../budget-forecast-staging/00-base/. .

git init -b main
git add -A
git commit -m "chore: initialise from the Wasaa Lifestyle budget-forecast skeleton

The service skeleton as supplied by Webmasters Kenya for U-CS 37: the frozen
POST /forecast contract, the FastAPI entrypoint, the contract test, the
Dockerfile and the demo page. No project code yet."

gh repo create budget-forecast --private --source=. --remote=origin --push
```

Add your supervisor and the integration lead:

```bash
gh api -X PUT repos/:owner/budget-forecast/collaborators/<benjamin-github-username> -f permission=push
```

Dr Ochango may prefer read access — use `-f permission=pull` for him. Ask both
for their usernames rather than guessing.

---

## 2 · Protect `main`

```bash
gh api -X PUT repos/:owner/budget-forecast/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["pytest"] },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null
}
JSON
```

`required_approving_review_count` is 0 because you are the only developer and
GitHub will not let you approve your own pull request. The protection still
blocks direct pushes to `main` and still requires CI to pass — which is the
part that matters as evidence. Say exactly this in 5.5.5; a single-developer
project that claims peer review is not credible.

---

## 3 · Create the milestone and the issues

```bash
gh api -X POST repos/:owner/budget-forecast/milestones \
  -f title="Baseline and evaluation" \
  -f description="Steps 1-2 of the partner's order of work: a measured baseline and a time-based evaluation harness."

gh api -X POST repos/:owner/budget-forecast/milestones \
  -f title="Model and integration" \
  -f description="Steps 3-4: a model that beats the baseline, deployed behind the unchanged contract."
```

Then the issues. Milestone 1 is `-m "Baseline and evaluation"`:

```bash
gh issue create -m "Baseline and evaluation" \
  -t "Adopt the issue/branch/PR workflow and add CI" \
  -b "## Outcome
Every change reaches main through an issue, a feature branch and a reviewed pull request with a passing CI check.

## Done when
- [ ] CONTRIBUTING.md records the branch naming and commit convention
- [ ] A pull-request template requires the measured before/after numbers
- [ ] GitHub Actions runs pytest on every pull request
- [ ] CI fails the build if a secret or data extract is ever tracked

## Notes
Produces the evidence for report sections 5.5.2, 5.5.3 and 5.5.5."

gh issue create -m "Baseline and evaluation" \
  -t "Synthetic spending data generator, labelled synthetic" \
  -b "## Outcome
A reproducible synthetic household population the baseline and evaluation can be built against before the staging sandbox is wired up.

## Done when
- [ ] Four household profiles including a volatile one and one with too little history
- [ ] Every row carries is_synthetic = true
- [ ] The generator reports the latent monthly expectation, giving an irreducible noise floor
- [ ] Non-stationary: seasonality, compounding drift, and step changes from rent escalation

## Notes
Project rule: synthetic data is labelled as synthetic, in the code and in the report."

gh issue create -m "Baseline and evaluation" \
  -t "Forecaster interface and trailing-median baseline" \
  -b "## Outcome
The dumbest thing that works, behind an interface that makes leakage impossible.

## Done when
- [ ] A forecaster is a function of (history, user_id, year, month) with no fitted state
- [ ] Per-category trailing median with an empirical interval
- [ ] insufficient_history rather than a confident number on thin history
- [ ] A volatile flag that is right more often than not

## Notes
Step 1 of the partner's mandated order of work. No model may be built before this exists."

gh issue create -m "Baseline and evaluation" \
  -t "Time-based evaluation harness and the measured baseline" \
  -b "## Outcome
The number the model has to beat, measured on held-out months and written down.

## Done when
- [ ] Rolling-origin split by time, not at random
- [ ] A test proves the harness never shows a forecaster the target month
- [ ] MAE, MAPE, per-category MAE and interval coverage reported
- [ ] Declined months reported separately, never scored as zero error
- [ ] BASELINE.md records the figures and the script that reproduces them

## Notes
Step 2 of the order of work. Split by time, not at random, and hold the last part back."

gh issue create -m "Baseline and evaluation" \
  -t "Implement the forecast contract and wire the baseline into the service" \
  -b "## Outcome
POST /forecast validates its input and answers from the measured baseline.

## Done when
- [ ] Request fields required: POST {} is a 422, not a forecast for nobody
- [ ] breakdown sums to estimatedTotal
- [ ] An unknown household is a flag, not a 404
- [ ] Real CSVs in data/ are used when present; synthetic otherwise, flagged
- [ ] The service cannot see the month it is forecasting

## Notes
estimatedTotalLow/High are additive and optional, and need Benjamin's sign-off for the Team Integration Map."
```

Milestone 2 — the work still to do:

```bash
gh issue create -m "Model and integration" \
  -t "Load the staging sandbox extract" \
  -b "## Outcome
The service answers from real staging data instead of generated data.

## Done when
- [ ] Credentials in .env, gitignored, never committed
- [ ] The four CSVs in data/, which is gitignored
- [ ] COLUMN_CANDIDATES in app/data.py matches the real schema
- [ ] Baseline re-measured on real data and BASELINE.md updated
- [ ] isSynthetic flips to false

## Notes
Staging data only. Never production, never live M-Pesa."

gh issue create -m "Model and integration" \
  -t "Forecast model that beats the baseline" \
  -b "## Outcome
A model that beats MAE 5137.9 / MAPE 13.79% on the same held-out months.

## Done when
- [ ] Beats the baseline on MAE, MAPE and per-category MAE
- [ ] Interval coverage stays within the honest range
- [ ] The before/after table is in the pull request and in BASELINE.md
- [ ] app/schemas.py is unchanged

## Notes
Only 14.6% of the baseline's error is removable at all — the rest is process noise.
Headroom is concentrated in the steady-tenant profile: rent escalation steps and
seasonality, which a trailing window structurally cannot track. Carries over the
recurrence detector and category rate model from the Phase 1 work in Wasaa_Lifestyle."

gh issue create -m "Model and integration" \
  -t "Containerise, deploy, and send Benjamin the service URL" \
  -b "## Outcome
A live URL that answers POST /forecast.

## Done when
- [ ] docker build and docker run work from a clean clone
- [ ] Deployed, with /health returning ok
- [ ] Benjamin has the URL for BUDGET_FORECAST_SERVICE_URL
- [ ] README documents the deployment so a stranger could repeat it

## Notes
Step 4 of the order of work. Keep the contract identical while the inside changes."
```

Check the numbering before the next step — the commands below assume issues
1 to 8 in the order above:

```bash
gh issue list --limit 20
```

---

## 4 · Land the five pull requests

Each block is identical in shape: branch, copy that step's files, commit, push,
open the PR. **Merge each one in the browser before starting the next** — the
later branches depend on the earlier ones being in `main`.

Wait for the CI tick before merging. Expected test counts, so you can tell a
real failure from a flake: **2 → 10 → 18 → 27 → 33**.

### PR 1 — workflow and CI (Issue #1)

The staging folder holds the CI files under `_github/` rather than `.github/`,
because the tooling that wrote them is not permitted to write into `.github/`
— a sensible restriction, since anything there executes on GitHub's runners.
The rename happens here, locally, so you can read `ci.yml` before it ever runs:

```bash
git switch -c feature/1-workflow-and-ci
cp -R ../budget-forecast-staging/01-workflow/. .
mkdir -p .github && cp -R _github/. .github/ && rm -rf _github

cat .github/workflows/ci.yml    # read it before committing something that runs on push

git add -A
git commit -m "chore(repo): adopt issue/branch/PR workflow and add CI

CONTRIBUTING.md records the branch naming and commit convention. The PR
template requires before/after numbers for any change touching accuracy.
GitHub Actions runs pytest on every pull request and fails the build if a
secret or data extract is ever tracked."
git push -u origin feature/1-workflow-and-ci
gh pr create --fill-first --body "Closes #1

## What changed
Adds the workflow this repository follows and the CI that enforces part of it.
No application code is touched.

## What I chose not to do
No linter yet — it would add failures unrelated to the measured work while the
service is still a stub.

## Checks
- [x] \`pytest -q\` passes locally (2 tests, the skeleton contract test)
- [x] No secrets, .env, or data extracts in the diff"
```

### PR 2 — synthetic generator (Issue #2)

```bash
git switch main && git pull
git switch -c feature/2-synthetic-data-generator
cp -R ../budget-forecast-staging/02-synthetic/. .
git add -A
git commit -m "feat(data): add synthetic household generator with known ground truth

Four profiles: steady tenant, student, volatile, and a new user with two
months of history. Every row carries is_synthetic. The generator also returns
the latent monthly expectation each household-month was drawn from, which
gives an irreducible noise floor for the evaluation.

Deliberately non-stationary. A first version drew from fixed parameters and
the trailing median saturated it completely, because a trailing median is the
optimal estimator of a stationary process. Seasonality, compounding drift and
step changes from rent escalation are what a trailing window cannot track."
git push -u origin feature/2-synthetic-data-generator
gh pr create --fill-first --body "Closes #2

## What changed
A reproducible synthetic population so the baseline and evaluation can be
built before the staging sandbox is available. 67,123 transactions, 28
households, 30 months.

30 months rather than 18 so that December appears more than once: a seasonal
effect observed a single time is indistinguishable from a one-off event.

## What I chose not to do
No real data yet. Issue #6 covers the sandbox extract, and isSynthetic stays
true until then.

## Checks
- [x] \`pytest -q\` passes locally (10 tests)
- [x] No secrets, .env, or data extracts in the diff"
```

### PR 3 — forecaster and baseline (Issue #3)

```bash
git switch main && git pull
git switch -c feature/3-trailing-median-baseline
cp -R ../budget-forecast-staging/03-forecaster/. .
git add -A
git commit -m "feat(baseline): add stateless forecaster interface and two baselines

A forecaster is a function of (history, user_id, year, month) where history
holds only months strictly before the target. It is not an object fitted once
and then queried, which makes leakage structurally impossible rather than
merely avoided.

LastMonthForecaster is the bar the project README sets. TrailingMedianForecaster
is the baseline the supervisor asked for: the median rather than the mean
because one outlying month drags a mean far enough to make the next forecast
useless."
git push -u origin feature/3-trailing-median-baseline
gh pr create --fill-first --body "Closes #3

## What changed
Step 1 of the order of work. Per-category trailing median with an empirical
10th-90th percentile interval, insufficient_history on thin history, and a
volatile flag.

Neither baseline corrects for month length, intentionally: a 28-day February
contains fewer commuting days than a 31-day March, so that correction becomes
measured lift for the model rather than being quietly absorbed here.

## What I chose not to do
The volatile flag is defined on interval width, not a coefficient of variation.
The CV version could not fire — no household exceeded any workable threshold,
because a large steady rent dilutes the CV of a total and makes erratic
spenders look calm.

## Checks
- [x] \`pytest -q\` passes locally (18 tests)
- [x] No secrets, .env, or data extracts in the diff"
```

### PR 4 — evaluation and the measured baseline (Issue #4)

```bash
git switch main && git pull
git switch -c feature/4-time-based-evaluation
cp -R ../budget-forecast-staging/04-evaluation/. .
cp -R _github/. .github/ && rm -rf _github    # adds the baseline step to CI

git add -A
git commit -m "feat(eval): add rolling-origin time split and record the baseline

Split by time, not at random. A random split over monthly rows would let a
household's June sit in training while May and July sit in test, and monthly
spend is strongly autocorrelated enough for a model to reach a flattering
score by interpolating between two months it had already seen.

Reports MAE, MAPE, per-category MAE and interval coverage, with declined
months counted separately so that a service answering nothing cannot record a
perfect zero error."
git commit --allow-empty -m "docs(baseline): record the measured baseline in BASELINE.md

trailing_median_6m: MAE 5137.9, MAPE 13.79%, coverage 80.0%.
Irreducible noise floor: MAE 4389.7, MAPE 12.74%.

Only 748.2 KES - 14.6% of the baseline's error - is removable at all. A model
reaching 4400 has extracted essentially all available signal; one reporting
2000 has a leak."
git push -u origin feature/4-time-based-evaluation
gh pr create --fill-first --body "Closes #4

## What changed
Step 2 of the order of work, and the number the model must beat.

## Measurement

| forecaster | MAE | MAPE | category MAE | coverage |
|---|---|---|---|---|
| last_month | 6158.5 | 18.35% | 2153.3 | — |
| trailing_median_3m | 5802.1 | 14.96% | 1923.9 | 81.3% |
| **trailing_median_6m** | **5137.9** | **13.79%** | **1718.9** | **80.0%** |
| noise floor | 4389.7 | 12.74% | — | — |

CI now reproduces these on every pull request, so they cannot go stale silently.

## What I chose not to do
Did not resolve 3m versus 6m. The 6-month window wins on the mean, the 3-month
on the median APE - it is more accurate for the typical household and less
robust in the tail. Which matters depends on how U-CS 38 uses it.

## Checks
- [x] \`pytest -q\` passes locally (27 tests)
- [x] BASELINE.md records the measured numbers
- [x] No secrets, .env, or data extracts in the diff"
```

### PR 5 — contract and service (Issue #5)

```bash
git switch main && git pull
git switch -c feature/5-forecast-contract-and-service
cp -R ../budget-forecast-staging/05-contract-service/. .
git add -A
git commit -m "feat(contract): validate the request and wire the baseline into /forecast

The skeleton accepted POST /forecast {} with a 200 and returned a forecast for
nobody. Request fields are now required, so a missing or misspelled userId
fails at the boundary rather than producing a number another team displays to
a user. Unknown extra fields are still ignored, so a caller adding metadata
cannot break us.

The service honours the same no-leakage rule as the evaluation harness: it
only ever reads months strictly before the one being forecast."
git push -u origin feature/5-forecast-contract-and-service
gh pr create --fill-first --body "Closes #5

## What changed
POST /forecast answers from the measured baseline. FORECASTER in app/service.py
is the single swap point for the model, so the contract stays identical while
the inside changes completely.

## Contract change needing sign-off
estimatedTotalLow and estimatedTotalHigh are **additive and optional** -
invisible to any consumer not looking for them. They exist because the frozen
contract carries confidence as a scalar, and a scalar cannot express a range
while \"the confidence range is honest\" is in the done-when.

**This is a change to the published shape and needs Benjamin's confirmation
for the Team Integration Map before U-CS 38, 43 and 46 integrate.**

## What I chose not to do
No real data yet - see Issue #6.

## Checks
- [x] \`pytest -q\` passes locally (33 tests)
- [x] No secrets, .env, or data extracts in the diff"
```

---

## 5 · Capture the evidence

Take these as you go. A screenshot of the repository after everything is
merged cannot show a pull request under review.

| Report section | Screenshot | Capture it after |
|---|---|---|
| 5.5.1 Repository setup | Repository overview — name, file list, README rendered | step 1 |
| 5.5.2 Task planning | Issue list grouped by milestone, with assignee | step 3 |
| 5.5.2 Task planning | One issue in full — #4, which has the measurable done-when | step 3 |
| 5.5.3 Branching | Branch list showing `feature/<n>-<slug>` names | during step 4 |
| 5.5.4 Commits | Commit history for one feature — PR 4 has the feature and its docs commit separately | after PR 4 |
| 5.5.5 Review and integration | PR 4 showing the before/after table, the green `pytest` check, and the merge | before merging PR 4 |
| 5.5.6 Organisation | Folder tree plus the CONTRIBUTING.md excerpt on conventions | after PR 5 |
| 5.5.7 Hosting | Deployment status and `/health` returning ok at the live URL | Issue #8 |

Four to six screenshots is the limit, so the strongest set is: repository
overview, the issue list, **PR 4 with its green check and measurement table**,
and the deployed `/docs` page. The rest go in an appendix.

PR 4 is the single most valuable screenshot in the section. It shows an issue
link, a descriptive branch, separate commits, a measured before/after, a
passing automated check and a merge decision — six of the seven subsections in
one image.

### What to say about the earlier phase

5.5.4 should state plainly that model development in `Wasaa_Lifestyle`
(parser, Naive Bayes classifier, HMM recurrence detection; 158 tests) was
committed in bulk before the partner issued its workflow rules, that the
practice changed when `budget-forecast` began, and that no credential or
personal data ever entered either history — verified across all refs.

Examiners read far more generously than people expect when a limitation is
named and bounded. Slide 16 asks for exactly this honesty.

---

## 6 · The Phase 1 repository

`Wasaa_Lifestyle` stays as the Phase 1 archive. Two small honest commits are
worth making there, through a pull request so the workflow is consistent:

- a README note that the project moved to `budget-forecast`, saying which parts
  carried over (the recurrence detector and category rate model) and which were
  scoped out when the partner removed statement parsing (the parser, the
  merchant dictionary and the Naive Bayes classifier)
- move `data_README.md` to `model/data/README.md`, where it belongs

Neither is cosmetic: 5.5.6 asks you to explain each folder's responsibility,
and a loose `data_README.md` at the root is the one thing in that tree you
cannot explain.
