# Working on this repository

The workflow below is the one required by the Wasaa Lifestyle skeleton and by
Section 5.5 of the project report. It is written down so that every change
leaves the same trail, and so the report can describe a real practice rather
than an intention.

## The loop

Every change follows the same five steps. There are no exceptions for small
changes — a one-line fix with an issue and a PR costs two minutes and keeps the
history readable.

1. **Open an issue.** One task, stated as an outcome. Assign it to yourself and
   attach it to the milestone.
2. **Branch from `main`,** named `feature/<issue-number>-<short-slug>`. The
   number is what links the branch, the commits and the pull request back to
   the task.
3. **Commit in focused steps** using the convention below.
4. **Open a pull request.** The description links the issue with
   `Closes #<n>` and records what was measured, not just what was changed.
5. **Merge once CI is green.** `main` is protected; it is never committed to
   directly.

## Branch naming

```
feature/3-trailing-median-baseline
fix/17-month-length-off-by-one
docs/21-chapter-five-evidence
```

Prefix is `feature`, `fix`, `docs`, `test` or `chore`. The issue number comes
first so the branch sorts and greps by task.

## Commit messages

```
<type>(<scope>): <imperative summary>
```

`type` is one of `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.
`scope` is the area touched — `forecast`, `baseline`, `eval`, `data`,
`contract`, `ci`.

```
feat(baseline): add per-category trailing median with empirical interval
test(eval): assert the harness never shows the target month
fix(forecaster): define volatile flag on interval width, not CV
docs(baseline): record the measured baseline in BASELINE.md
```

A commit that changes behaviour and a commit that adds the tests for it are
separate commits. Section 5.5.4 asks for evidence that distinguishes a feature
change from its tests, and that is only possible if they were committed
separately.

## Pull requests

The description is the record of the decision, so it carries numbers:

- what changed, in one paragraph
- the measurement, before and after, when the change touches forecast accuracy
- what you chose not to do, and why

Never merge a red build. If a test is wrong, fix the test in its own commit and
say so in the PR — a test changed quietly to make a build pass is the one thing
that makes the whole suite worthless as evidence.

## What never enters the repository

- `.env`, API tokens, passwords, bearer tokens
- real or staging data extracts — `data/*.csv` is gitignored
- M-Pesa statements, in any format, ever

`.env.example` records the *names* of required configuration without values.
A credential committed once stays in the history after the file is deleted, so
the remedy is rotation on the platform, not a follow-up commit.

## Before pushing

```bash
pytest -q                        # all tests
python3 -m scripts.measure_baseline   # if forecast accuracy changed
```

If accuracy changed, the new numbers go in the PR description and in
`BASELINE.md`. A model is only "better" against a number someone can reproduce.
