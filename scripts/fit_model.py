"""
Fit the Ridge / ExtraTrees / HistGradientBoosting ensemble and score it against
the shipped blend. Reproduces every number in MODEL_ENSEMBLE.md.

    pip install -r requirements-train.txt
    python3 -m scripts.fit_model            # unconstrained -> models/ensemble-v1.*
    python3 -m scripts.fit_model --capped   # tree size capped -> models/ensemble-v1-capped.*
    python3 -m scripts.fit_model --targets fixed --validate-only [--capped]
                                            # months 13-15 only; nothing written
    python3 -m scripts.fit_model --model extratrees
                                            # all 500 households -> models/extratrees-v1.*
    python3 -m scripts.fit_model --model extratrees --disjoint
                                            # 440, deployed slice held out -> extratrees-v2.*

--targets chooses what Ridge and HistGB estimate. `current` (the default, and
what MODEL_ENSEMBLE.md reports) fits Ridge on log1p(spend) and HistGB with
absolute error: a geometric-mean-like and a median estimate, both below the
mean on right-skewed spend, so the ensemble forecasts low. `fixed` fits Ridge
on the raw target and HistGB with squared error, which both estimate the mean.
--validate-only stops after the selection split: no final fit, no artefact,
and months 16-18 are never scored.

Needs the full sandbox extract in data/ (500 households, 18 months). Synthetic.

THREE SPLITS, AND ONLY ONE LOOK AT THE LAST
-------------------------------------------
Target months are numbered from the first month of data (1 = Apr 2025).

  select    fit on targets 4-12, score 13-15.  Every configuration choice.
  final     refit the chosen configuration on targets 4-15.
  holdout   score targets 16-18, once, against the blend.

`select_config` is never handed a row from months 16-18; the holdout rows are
cut out of the panel before it is called. Months 16-18 have nonetheless been
scored many times in this project (SANDBOX_RESULTS.md), including to confirm
the blend's weight, so a narrow win there is weaker evidence than its t
statistic suggests.

Both the validation and the holdout scores go through app.evaluate.evaluate,
with the same rolling origin, the same rows and the same metrics as every
other figure in the project. Each learner is wrapped as a Forecaster whose
answers were precomputed from the panel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.data import load_budgets, load_monthly, provenance
from app.evaluate import HEADER, Result, _month_keys, evaluate
from app.forecaster import (
    MIN_MONTHS_FOR_FORECAST,
    BudgetBlendForecaster,
    Forecast,
)
from scripts.build_panel import FEATURES, build, deployed_households, training_panel

RANDOM_STATE = 37
TRAIN = (4, 15)
SELECT_FIT, SELECT_SCORE = (4, 12), (13, 15)
HOLDOUT = (16, 18)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
LEARNERS = ("ridge", "extra_trees", "hist_gb")

# The candidates `select_config` chooses between. Small on purpose: three
# months of validation cannot separate a large grid from luck.
GRID: dict[str, list[dict]] = {
    "ridge": [{"alpha": a} for a in (0.1, 1.0, 10.0, 100.0)],
    "extra_trees": [
        {"n_estimators": 100, "min_samples_leaf": leaf, "max_features": mf}
        for leaf in (1, 5, 20)
        for mf in (1.0, 0.5)
    ],
    "hist_gb": [
        {"learning_rate": lr, "max_iter": it}
        for lr in (0.05, 0.1)
        for it in (200, 500)
    ],
}

# --capped: limits on tree count and depth for a memory budget. Fixed here,
# not chosen on any split.
CAPS = {
    "extra_trees": {"n_estimators": 40, "max_depth": 12},
    "hist_gb": {"max_depth": 6},
}

# What ships: ExtraTrees alone, capped, on the raw target. Chosen on months
# 13-15 (MODEL_ENSEMBLE.md), where it matched the bias-corrected ensemble on
# category MAE and beat it on MAE, with a mean signed error of +346.7.
EXTRATREES_V1 = {
    "n_estimators": 40, "max_depth": 12, "min_samples_leaf": 20, "max_features": 1.0,
}

# The evidence EXTRATREES_V1 was selected on, as extratrees-v1's manifest
# recorded it (written at dc48878, committed in 87b9a0a). extratrees-v2 reuses
# the configuration without re-selecting it, and its manifest says so rather
# than leaving the selection out.
EXTRATREES_V1_SELECTION = {
    "reselected": False,
    "statement": (
        "Configuration fixed by extratrees-v1's validation run and not "
        "re-selected for this fit. It was chosen as ExtraTrees alone, capped "
        "(variant C), fitted on target months 4-12 and scored on 13-15 with "
        "all 500 households, alongside the bias-corrected ensemble (variant B) "
        "it was compared with. See MODEL_ENSEMBLE.md."
    ),
    "selected_by": "extratrees-v1: git_head dc48878, manifest committed in 87b9a0a",
    "months": "2026-04 to 2026-06",
    "mae": 7848.5,
    "cat_mae": 1779.4,
    "signed_error": 346.7,
}

TARGETS = {
    "current": {"ridge_log": True, "hist_gb_loss": "absolute_error"},
    "fixed": {"ridge_log": False, "hist_gb_loss": "squared_error"},
}


def make(learner: str, params: dict, targets: str = "current"):
    if learner == "ridge":
        return make_pipeline(
            StandardScaler(), Ridge(random_state=RANDOM_STATE, **params)
        )
    if learner == "extra_trees":
        return ExtraTreesRegressor(random_state=RANDOM_STATE, n_jobs=-1, **params)
    if learner == "hist_gb":
        # early_stopping would hold out a RANDOM tenth of the rows, mixing
        # months; max_iter is chosen on the time split instead.
        return HistGradientBoostingRegressor(
            loss=TARGETS[targets]["hist_gb_loss"],
            early_stopping=False,
            random_state=RANDOM_STATE,
            **params,
        )
    raise ValueError(learner)


def _log_target(learner: str, targets: str) -> bool:
    return learner == "ridge" and TARGETS[targets]["ridge_log"]


def fit(learner: str, params: dict, rows: pd.DataFrame, targets: str = "current"):
    x = rows[FEATURES].to_numpy()
    y = rows["target"].to_numpy()
    # With targets="current", Ridge is fitted on log1p(target) so a few rent
    # payments do not dominate it, at the price of estimating below the mean.
    log = _log_target(learner, targets)
    return make(learner, params, targets).fit(x, np.log1p(y) if log else y)


def predict(
    learner: str, model, rows: pd.DataFrame, targets: str = "current"
) -> np.ndarray:
    raw = model.predict(rows[FEATURES].to_numpy())
    return np.clip(np.expm1(raw) if _log_target(learner, targets) else raw, 0.0, None)


def predict_ensemble(bundle: dict, rows: pd.DataFrame) -> np.ndarray:
    """
    Equal-weight mean of the bundle's learners, on the original scale. A
    bundle with one learner, as extratrees-v1 has, returns that learner's
    prediction.
    """
    targets = bundle.get("targets", "current")
    return np.mean(
        [predict(name, model, rows, targets) for name, model in bundle["learners"].items()],
        axis=0,
    )


def signed_error(result: Result) -> float:
    """Mean of predicted minus actual total. Negative = forecasts low."""
    scored = result.rows[~result.rows["declined"]]
    return float((scored["predicted_total"] - scored["actual_total"]).mean())


class PanelForecaster:
    """
    Answers `evaluate` from predictions already made on the panel. Declines,
    as the blend does, below MIN_MONTHS_FOR_FORECAST months of history, so
    both are scored on the same household-months.
    """

    def __init__(self, name: str, rows: pd.DataFrame, predicted: np.ndarray):
        self.name = name
        frame = rows[["user_id", "mkey", "category", "n_history"]].assign(
            predicted=predicted
        )
        self._answers = {
            key: group for key, group in frame.groupby(["user_id", "mkey"])
        }

    def forecast(self, history, user_id: str, year: int, month: int) -> Forecast:
        group = self._answers.get((user_id, year * 12 + month))
        if group is None or group["n_history"].iloc[0] < MIN_MONTHS_FOR_FORECAST:
            return Forecast(
                total=0.0, breakdown={}, risk_flag="insufficient_history",
                method=self.name,
            )
        breakdown = {
            c: round(float(v), 2)
            for c, v in zip(group["category"], group["predicted"])
            if v > 0.005
        }
        return Forecast(
            total=round(sum(breakdown.values()), 2), breakdown=breakdown,
            method=self.name,
        )


def months(panel: pd.DataFrame, span: tuple[int, int]) -> pd.DataFrame:
    return panel[panel["month_index"].between(*span)]


def through(monthly: pd.DataFrame, last_index: int) -> pd.DataFrame:
    """The monthly frame cut after target month `last_index`."""
    keys = _month_keys(monthly)
    return monthly[keys <= keys.min() + last_index - 1]


def select_config(
    train_panel: pd.DataFrame,
    monthly_train: pd.DataFrame,
    caps: dict,
    log: list,
    targets: str = "current",
):
    """
    Choose each learner's configuration by total MAE on months 13-15, fitted on
    4-12. Never sees months 16-18: both frames stop at month 15. `caps`
    override the grid's values, for --capped.

    Returns the chosen configurations, each chosen learner's validation
    result, and the ensemble of them and the shipped blend scored on the same
    months, so the ensemble can be compared with its parts and with the blend
    without looking at the holdout.
    """
    assert train_panel["month_index"].max() <= TRAIN[1]
    assert monthly_train["year"].mul(12).add(monthly_train["month"]).nunique() <= TRAIN[1]

    fit_rows = months(train_panel, SELECT_FIT)
    score_rows = months(train_panel, SELECT_SCORE)
    chosen: dict[str, dict] = {}
    validation: dict[str, np.ndarray] = {}
    alone: dict[str, Result] = {}
    for learner, candidates in GRID.items():
        best = None
        for params in candidates:
            params = {**params, **caps.get(learner, {})}
            model = fit(learner, params, fit_rows, targets)
            predicted = predict(learner, model, score_rows, targets)
            result = evaluate(
                PanelForecaster(learner, score_rows, predicted),
                monthly_train, n_holdout=3,
            )
            log.append((learner, params, result.mae_total, result.mae_category,
                        signed_error(result)))
            if best is None or result.mae_total < best[0]:
                best = (result.mae_total, params, predicted, result)
        chosen[learner] = best[1]
        validation[learner] = best[2]
        alone[learner] = best[3]

    ensemble = evaluate(
        PanelForecaster(
            "ensemble", score_rows, np.mean([validation[n] for n in LEARNERS], axis=0)
        ),
        monthly_train, n_holdout=3,
    )
    blend = evaluate(BudgetBlendForecaster(load_budgets()), monthly_train, n_holdout=3)
    return chosen, alone, ensemble, blend


@dataclass
class Paired:
    name: str
    result: Result
    d_mae: float
    t_mae: float
    d_mape: float
    t_mape: float
    d_cat: float
    t_cat: float
    wins: int
    n: int


def paired(result: Result, base: Result) -> Paired:
    keys = ["user_id", "year", "month"]
    a = result.rows[~result.rows["declined"]].set_index(keys)
    b = base.rows[~base.rows["declined"]].set_index(keys)
    common = a.index.intersection(b.index)
    a, b = a.loc[common], b.loc[common]

    def stat(col: str) -> tuple[float, float]:
        d = (a[col] - b[col]).astype(float).dropna().to_numpy()
        sd = d.std(ddof=1)
        return float(d.mean()), float(d.mean() / (sd / np.sqrt(len(d)))) if sd else 0.0

    d_mae, t_mae = stat("abs_error")
    d_mape, t_mape = stat("ape")
    d_cat, t_cat = stat("cat_mae")
    wins = int((a["abs_error"] < b["abs_error"]).sum())
    return Paired(result.name, result, d_mae, t_mae, d_mape * 100, t_mape,
                  d_cat, t_cat, wins, len(common))


def git_head() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    return sha, dirty


def month_label(monthly: pd.DataFrame, index: int) -> str:
    year, month = divmod(int(_month_keys(monthly).min()) + index - 1, 12)
    if month == 0:
        year, month = year - 1, 12
    return f"{year:04d}-{month:02d}"


def ship_extratrees() -> None:
    """
    Fit EXTRATREES_V1 on targets 4-15, score it once on 16-18 against the
    blend, and write models/extratrees-v1.*. Nothing else is scored on the
    holdout. Refuses a dirty tree, so the manifest's git_head is the commit
    that produced the artefact.
    """
    sha, dirty = git_head()
    if dirty:
        raise SystemExit("Tracked files have uncommitted changes. Commit first.")

    tag = "extratrees-v1"
    monthly, _ = load_monthly()
    budgets = load_budgets()
    panel = build(monthly, budgets)
    assert panel["month_index"].max() == HOLDOUT[1], "expected 18 months of data"
    train_panel = months(panel, TRAIN)
    monthly_train = through(monthly, TRAIN[1])
    holdout_rows = months(panel, HOLDOUT)

    print(
        f"SYNTHETIC — platform sandbox, {monthly['user_id'].nunique()} households. "
        f"{tag}: ExtraTrees {EXTRATREES_V1}, raw target\n"
    )

    # The same configuration on the selection split, for continuity with the
    # table it was chosen from. Months 13-15 only.
    score_rows = months(train_panel, SELECT_SCORE)
    early = fit("extra_trees", EXTRATREES_V1, months(train_panel, SELECT_FIT))
    validated = evaluate(
        PanelForecaster(tag, score_rows, predict("extra_trees", early, score_rows)),
        monthly_train, n_holdout=3,
    )
    print(
        f"validation, months 13-15: MAE {validated.mae_total:.1f}  "
        f"catMAE {validated.mae_category:.1f}  "
        f"signed error {signed_error(validated):+.1f}"
    )

    model = fit("extra_trees", EXTRATREES_V1, train_panel)
    bundle = {"features": FEATURES, "learners": {"extra_trees": model}}
    MODELS_DIR.mkdir(exist_ok=True)
    artefact = MODELS_DIR / f"{tag}.joblib"
    joblib.dump(bundle, artefact)
    digest = hashlib.sha256(artefact.read_bytes()).hexdigest()

    # ── the one look at months 16-18, for this model only ──
    blend = evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3)
    result = evaluate(
        PanelForecaster(tag, holdout_rows, predict_ensemble(bundle, holdout_rows)),
        monthly, n_holdout=3,
    )
    p = paired(result, blend)

    print(f"\nHoldout, months {HOLDOUT[0]}-{HOLDOUT[1]}\n{HEADER}\n{'─' * len(HEADER)}")
    print(blend.line())
    print(result.line())
    print(
        f"\nmean signed error   blend {signed_error(blend):+.1f}   "
        f"{tag} {signed_error(result):+.1f}"
    )
    print(
        f"\npaired against the blend over {p.n} household-months "
        f"(negative = better)\n"
        f"  MAE     {p.d_mae:+8.1f}  t {p.t_mae:6.2f}\n"
        f"  MAPE    {p.d_mape:+8.2f} pp  t {p.t_mape:6.2f}\n"
        f"  catMAE  {p.d_cat:+8.1f}  t {p.t_cat:6.2f}\n"
        f"  wins    {p.wins}/{p.n}"
    )

    by_month = []
    print(f"\nby month        {'MAE Δ':>8s} {'catMAE Δ':>9s} {'signed err':>11s} {'blend':>8s}")
    for (y, m), rows in result.rows.groupby(["year", "month"]):
        base = blend.rows[(blend.rows["year"] == y) & (blend.rows["month"] == m)]
        row = {
            "month": f"{y}-{m:02d}",
            "mae_delta": round(rows["abs_error"].mean() - base["abs_error"].mean(), 1),
            "cat_mae_delta": round(rows["cat_mae"].mean() - base["cat_mae"].mean(), 1),
            "signed_error": round(
                (rows["predicted_total"] - rows["actual_total"]).mean(), 1),
            "blend_signed_error": round(
                (base["predicted_total"] - base["actual_total"]).mean(), 1),
        }
        by_month.append(row)
        print(f"  {row['month']}      {row['mae_delta']:8.1f} {row['cat_mae_delta']:9.1f} "
              f"{row['signed_error']:+11.1f} {row['blend_signed_error']:+8.1f}")

    manifest = {
        "artefact": artefact.name,
        "sha256": digest,
        "size_bytes": artefact.stat().st_size,
        "model": "ExtraTreesRegressor, raw target, predictions clipped at 0",
        "params": EXTRATREES_V1,
        "trained_through": month_label(monthly, TRAIN[1]),
        "training_target_months": f"{month_label(monthly, TRAIN[0])} to "
        f"{month_label(monthly, TRAIN[1])}",
        "training_rows": int(len(train_panel)),
        "features": FEATURES,
        "random_state": RANDOM_STATE,
        "versions": {
            pkg: version(pkg) for pkg in ("scikit-learn", "pandas", "numpy", "joblib")
        },
        "git_head": sha,
        "git_tracked_changes_uncommitted": dirty,
        "data": "SYNTHETIC platform sandbox, data/spending_records.csv",
        "validation": {
            "months": f"{month_label(monthly, SELECT_SCORE[0])} to "
            f"{month_label(monthly, SELECT_SCORE[1])}",
            "mae": round(validated.mae_total, 1),
            "cat_mae": round(validated.mae_category, 1),
            "signed_error": round(signed_error(validated), 1),
        },
        "holdout": {
            "months": f"{month_label(monthly, HOLDOUT[0])} to "
            f"{month_label(monthly, HOLDOUT[1])}",
            "n": p.n,
            "mae": round(result.mae_total, 1),
            "mape_pct": round(result.mape_total * 100, 2),
            "median_ape_pct": round(result.median_ape_total * 100, 2),
            "cat_mae": round(result.mae_category, 1),
            "signed_error": round(signed_error(result), 1),
            "blend_mae": round(blend.mae_total, 1),
            "blend_cat_mae": round(blend.mae_category, 1),
            "paired_vs_blend": {
                "mae_delta": round(p.d_mae, 1), "mae_t": round(p.t_mae, 2),
                "mape_delta_pp": round(p.d_mape, 2), "mape_t": round(p.t_mape, 2),
                "cat_mae_delta": round(p.d_cat, 1), "cat_mae_t": round(p.t_cat, 2),
                "wins": p.wins,
            },
            "by_month": by_month,
        },
    }
    (MODELS_DIR / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"\nwrote models/{artefact.name} ({artefact.stat().st_size / 1e6:.1f} MB, "
        f"sha256 {digest[:12]}...) and models/{tag}.manifest.json, git_head {sha[:7]}"
    )


def restrict(result: Result, users: set[str], name: str) -> Result:
    """`result` scored over `users` only, with evaluate's own definitions."""
    rows = result.rows[result.rows["user_id"].astype(str).isin(users)]
    scored = rows[~rows["declined"]]
    return Result(
        name=name,
        n_forecasts=int(len(scored)),
        n_declined=int(rows["declined"].sum()),
        mae_total=float(scored["abs_error"].mean()),
        mape_total=float(scored["ape"].mean(skipna=True)),
        median_ape_total=float(scored["ape"].median(skipna=True)),
        mae_category=float(scored["cat_mae"].mean()),
        coverage=None,
        mean_confidence=None,
        rows=rows,
    )


def ship_extratrees_disjoint() -> None:
    """
    EXTRATREES_V1's configuration, refitted on targets 4-15 for the 440
    households NOT in the deployed slice, so no household the service serves
    was in training. Scored on 16-18 for the 440 (out-of-month) and for the 60
    (out-of-month and out-of-household), each paired against the blend, and
    on the 440 against extratrees-v1 to show what dropping 60 households
    costs. Nothing is re-tuned. Writes models/extratrees-v2.*.
    """
    sha, dirty = git_head()
    if dirty:
        raise SystemExit("Tracked files have uncommitted changes. Commit first.")

    tag = "extratrees-v2"
    deployed = deployed_households()
    monthly, _ = load_monthly()
    budgets = load_budgets()
    panel = build(monthly, budgets)
    assert panel["month_index"].max() == HOLDOUT[1], "expected 18 months of data"
    everyone = set(monthly["user_id"].astype(str))
    served = set(deployed)
    trained = everyone - served
    assert served <= everyone and len(served) == 60

    train_panel = training_panel(panel, served, *TRAIN)
    assert set(train_panel["user_id"]) == trained
    holdout_rows = months(panel, HOLDOUT)

    # extratrees-v1, the all-500 fit, refitted here rather than read from
    # models/: it is deterministic, and v2 replaces it in the repository.
    v1 = {
        "features": FEATURES,
        "learners": {
            "extra_trees": fit("extra_trees", EXTRATREES_V1, months(panel, TRAIN))
        },
    }

    print(
        f"SYNTHETIC — platform sandbox. {tag}: ExtraTrees {EXTRATREES_V1}, raw target\n"
        f"trained on {len(trained)} households, targets {TRAIN}; the {len(served)} "
        f"deployed households (data/public/, checked record for record) excluded\n"
    )

    model = fit("extra_trees", EXTRATREES_V1, train_panel)
    bundle = {"features": FEATURES, "learners": {"extra_trees": model}}
    MODELS_DIR.mkdir(exist_ok=True)
    artefact = MODELS_DIR / f"{tag}.joblib"
    joblib.dump(bundle, artefact)
    digest = hashlib.sha256(artefact.read_bytes()).hexdigest()

    # ── months 16-18: v2, and v1 and the blend as the comparisons ──
    blend = evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3)
    v2_all = evaluate(
        PanelForecaster(tag, holdout_rows, predict_ensemble(bundle, holdout_rows)),
        monthly, n_holdout=3,
    )
    v1_all = evaluate(
        PanelForecaster("extratrees-v1", holdout_rows, predict_ensemble(v1, holdout_rows)),
        monthly, n_holdout=3,
    )

    summary = {}
    groups = [
        ("trained_440", trained, "the 440 training households: out-of-month, in-household"),
        ("deployed_60", served, "the 60 deployed households: out-of-month AND out-of-household"),
    ]
    for key, users, label in groups:
        b = restrict(blend, users, blend.name)
        two = restrict(v2_all, users, tag)
        one = restrict(v1_all, users, "extratrees-v1 (all 500)")
        print(f"\n── {label} ──\n{HEADER}\n{'─' * len(HEADER)}")
        for r in (b, two, one):
            print(r.line())
        print(
            f"mean signed error   blend {signed_error(b):+.1f}   {tag} "
            f"{signed_error(two):+.1f}   extratrees-v1 {signed_error(one):+.1f}"
        )
        vs_blend = paired(two, b)
        vs_v1 = paired(two, one)
        for title, pr in ((f"{tag} vs blend", vs_blend), (f"{tag} vs extratrees-v1", vs_v1)):
            print(
                f"  {title:28s} MAE {pr.d_mae:+8.1f} (t {pr.t_mae:6.2f})  "
                f"MAPE {pr.d_mape:+6.2f} pp (t {pr.t_mape:6.2f})  "
                f"catMAE {pr.d_cat:+7.1f} (t {pr.t_cat:6.2f})  wins {pr.wins}/{pr.n}"
            )
        summary[key] = {
            "households": len(users),
            "n": vs_blend.n,
            "mae": round(two.mae_total, 1),
            "mape_pct": round(two.mape_total * 100, 2),
            "median_ape_pct": round(two.median_ape_total * 100, 2),
            "cat_mae": round(two.mae_category, 1),
            "signed_error": round(signed_error(two), 1),
            "blend": {"mae": round(b.mae_total, 1), "cat_mae": round(b.mae_category, 1),
                      "signed_error": round(signed_error(b), 1)},
            "vs_blend": {
                "mae_delta": round(vs_blend.d_mae, 1), "mae_t": round(vs_blend.t_mae, 2),
                "mape_delta_pp": round(vs_blend.d_mape, 2), "mape_t": round(vs_blend.t_mape, 2),
                "cat_mae_delta": round(vs_blend.d_cat, 1), "cat_mae_t": round(vs_blend.t_cat, 2),
                "wins": vs_blend.wins,
            },
            "vs_extratrees_v1": {
                "mae_delta": round(vs_v1.d_mae, 1), "mae_t": round(vs_v1.t_mae, 2),
                "cat_mae_delta": round(vs_v1.d_cat, 1), "cat_mae_t": round(vs_v1.t_cat, 2),
            },
        }

    manifest = {
        "artefact": artefact.name,
        "sha256": digest,
        "size_bytes": artefact.stat().st_size,
        "model": "ExtraTreesRegressor, raw target, predictions clipped at 0",
        "params": EXTRATREES_V1,
        "trained_through": month_label(monthly, TRAIN[1]),
        "training_target_months": f"{month_label(monthly, TRAIN[0])} to "
        f"{month_label(monthly, TRAIN[1])}",
        "training_households": len(trained),
        "training_rows": int(len(train_panel)),
        "excluded_households": (
            f"the {len(served)} in data/public/, selected by "
            "scripts.minimise_extract.slice_alias and checked record for record"
        ),
        "deployed_households_in_training": 0,
        "validation": EXTRATREES_V1_SELECTION,
        "features": FEATURES,
        "random_state": RANDOM_STATE,
        "versions": {
            pkg: version(pkg) for pkg in ("scikit-learn", "pandas", "numpy", "joblib")
        },
        "git_head": sha,
        "git_tracked_changes_uncommitted": dirty,
        "data": "SYNTHETIC platform sandbox, data/spending_records.csv",
        "holdout": {
            "months": f"{month_label(monthly, HOLDOUT[0])} to "
            f"{month_label(monthly, HOLDOUT[1])}",
            **summary,
        },
    }
    (MODELS_DIR / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"\nwrote models/{artefact.name} ({artefact.stat().st_size / 1e6:.1f} MB, "
        f"sha256 {digest[:12]}...) and models/{tag}.manifest.json, git_head {sha[:7]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("ensemble", "extratrees"), default="ensemble")
    parser.add_argument("--capped", action="store_true")
    parser.add_argument("--targets", choices=sorted(TARGETS), default="current")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--disjoint", action="store_true")
    args = parser.parse_args()

    if provenance() != "platform-sandbox":
        raise SystemExit(
            "The full sandbox extract is not in data/. Run `python -m scripts.fetch_data`."
        )
    if args.model == "extratrees":
        if args.capped or args.targets != "current" or args.validate_only:
            raise SystemExit("--model extratrees takes no other options; it is fixed.")
        ship_extratrees_disjoint() if args.disjoint else ship_extratrees()
        return
    if args.disjoint:
        raise SystemExit("--disjoint applies to --model extratrees only.")

    tag = "ensemble-v1" if args.targets == "current" else "ensemble-v2"
    tag += "-capped" if args.capped else ""
    log: list = []

    monthly, _ = load_monthly()
    budgets = load_budgets()
    panel = build(monthly, budgets)
    assert panel["month_index"].max() == HOLDOUT[1], "expected 18 months of data"

    # The holdout is cut off here, before anything is chosen or fitted.
    train_panel = months(panel, TRAIN)
    monthly_train = through(monthly, TRAIN[1])
    holdout_rows = months(panel, HOLDOUT)

    print(
        f"SYNTHETIC — platform sandbox, {monthly['user_id'].nunique()} households. "
        f"{tag}, targets={args.targets} {TARGETS[args.targets]}\n"
        f"select: fit {SELECT_FIT}, score {SELECT_SCORE}   final fit: {TRAIN}   "
        f"holdout: {HOLDOUT} ({month_label(monthly, HOLDOUT[0])} to "
        f"{month_label(monthly, HOLDOUT[1])})\n"
    )

    chosen, alone, validated, validated_blend = select_config(
        train_panel, monthly_train, CAPS if args.capped else {}, log, args.targets
    )
    print(
        "Configuration, chosen on months 13-15 by total MAE "
        "(MAE, catMAE, mean signed error on the total)"
    )
    for learner, params, mae, cat, bias in log:
        mark = "  <-" if params == chosen[learner] else ""
        print(f"  {learner:12s} {str(params):70s} {mae:8.1f} {cat:8.1f} {bias:9.1f}{mark}")
    print(
        f"  {'blend':12s} {'the shipped forecaster, for reference':70s} "
        f"{validated_blend.mae_total:8.1f} {validated_blend.mae_category:8.1f} "
        f"{signed_error(validated_blend):9.1f}"
    )
    print(
        f"  {'ensemble':12s} {'equal-weight mean of the three marked':70s} "
        f"{validated.mae_total:8.1f} {validated.mae_category:8.1f} "
        f"{signed_error(validated):9.1f}"
    )

    print(f"\nValidation summary, months 13-15 ({tag})")
    print(f"  {'':24s} {'MAE':>8s} {'catMAE':>8s} {'signed err':>11s}")
    rows = [("blend (shipped)", validated_blend),
            *[(f"{n} alone", alone[n]) for n in LEARNERS],
            ("ensemble", validated)]
    for label, r in rows:
        print(f"  {label:24s} {r.mae_total:8.1f} {r.mae_category:8.1f} "
              f"{signed_error(r):11.1f}")

    if args.validate_only:
        print("\n--validate-only: stopped before the final fit. Months 16-18 not scored.")
        return

    bundle = {
        "features": FEATURES,
        "ridge_target": "log1p" if TARGETS[args.targets]["ridge_log"] else "raw",
        "learners": {
            name: fit(name, chosen[name], train_panel, args.targets)
            for name in LEARNERS
        },
    }
    # Only recorded when not the default, so the v1 artefacts stay
    # byte-identical to the ones MODEL_ENSEMBLE.md reports.
    if args.targets != "current":
        bundle["targets"] = args.targets

    # Impurity importances from the training fit: where the trees split, not
    # a causal ranking, and nothing here reads the holdout.
    importances = pd.Series(
        bundle["learners"]["extra_trees"].feature_importances_, index=FEATURES
    ).sort_values(ascending=False)
    print("\nExtraTrees importances, top 6 (training fit)")
    for name, value in importances.head(6).items():
        print(f"  {name:22s} {value:.3f}")

    MODELS_DIR.mkdir(exist_ok=True)
    artefact = MODELS_DIR / f"{tag}.joblib"
    joblib.dump(bundle, artefact)
    digest = hashlib.sha256(artefact.read_bytes()).hexdigest()

    # ── the one look at months 16-18 ──
    blend = evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3)
    results = [
        evaluate(
            PanelForecaster(name, holdout_rows,
                            predict(name, bundle["learners"][name], holdout_rows,
                                    args.targets)),
            monthly, n_holdout=3,
        )
        for name in LEARNERS
    ]
    results.append(
        evaluate(
            PanelForecaster("ensemble (equal weight)", holdout_rows,
                            predict_ensemble(bundle, holdout_rows)),
            monthly, n_holdout=3,
        )
    )

    print(f"\nHoldout, months {HOLDOUT[0]}-{HOLDOUT[1]}\n{HEADER}\n{'─' * len(HEADER)}")
    print(blend.line())
    for r in results:
        print(r.line())

    print(
        "\nPaired against the blend, per household-month. Negative = better than "
        "the blend.\n"
        f"{'':26s} {'MAE Δ':>8s} {'t':>7s}  {'MAPE Δpp':>8s} {'t':>7s}  "
        f"{'catMAE Δ':>8s} {'t':>7s}  {'wins':>10s}"
    )
    comparisons = [paired(r, blend) for r in results]
    for p in comparisons:
        print(
            f"{p.name:26s} {p.d_mae:8.1f} {p.t_mae:7.2f}  {p.d_mape:8.2f} "
            f"{p.t_mape:7.2f}  {p.d_cat:8.1f} {p.t_cat:7.2f}  {p.wins:5d}/{p.n}"
        )

    # MAE hides direction. A learner that under-forecasts every total loses on
    # MAE while still placing spend in the right categories.
    print("\nMean signed error on the total (predicted - actual), holdout")
    for r in [blend, *results]:
        scored = r.rows[~r.rows["declined"]]
        bias = (scored["predicted_total"] - scored["actual_total"]).mean()
        print(f"  {r.name:30s} {bias:9.1f}")

    ensemble = results[-1]
    print("\nEnsemble minus blend, MAE by holdout month")
    for (y, m), rows in ensemble.rows.groupby(["year", "month"]):
        base = blend.rows[(blend.rows["year"] == y) & (blend.rows["month"] == m)]
        print(f"  {y}-{m:02d}  {rows['abs_error'].mean() - base['abs_error'].mean():8.1f}")

    sha, dirty = git_head()
    manifest = {
        "artefact": artefact.name,
        "sha256": digest,
        "size_bytes": artefact.stat().st_size,
        "trained_through": month_label(monthly, TRAIN[1]),
        "training_target_months": f"{month_label(monthly, TRAIN[0])} to "
        f"{month_label(monthly, TRAIN[1])}",
        "training_rows": int(len(train_panel)),
        "features": FEATURES,
        "learners": {name: chosen[name] for name in LEARNERS},
        "ensemble": "equal-weight mean of the three, original scale, clipped at 0",
        "targets": args.targets,
        "ridge_target": (
            "log1p (predictions expm1)"
            if TARGETS[args.targets]["ridge_log"] else "raw"
        ),
        "hist_gb_loss": TARGETS[args.targets]["hist_gb_loss"],
        "random_state": RANDOM_STATE,
        "capped": args.capped,
        "versions": {
            pkg: version(pkg) for pkg in ("scikit-learn", "pandas", "numpy", "joblib")
        },
        "git_head": sha,
        "git_tracked_changes_uncommitted": dirty,
        "data": "SYNTHETIC platform sandbox, data/spending_records.csv",
        "holdout": {
            "months": f"{month_label(monthly, HOLDOUT[0])} to "
            f"{month_label(monthly, HOLDOUT[1])}",
            "blend_mae": round(blend.mae_total, 1),
            "ensemble_mae": round(ensemble.mae_total, 1),
            "ensemble_cat_mae": round(ensemble.mae_category, 1),
        },
    }
    (MODELS_DIR / f"{tag}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"\nwrote models/{artefact.name} ({artefact.stat().st_size / 1e6:.1f} MB, "
        f"sha256 {digest[:12]}...) and models/{tag}.manifest.json"
    )


if __name__ == "__main__":
    main()
