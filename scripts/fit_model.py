"""
Fit the Ridge / ExtraTrees / HistGradientBoosting ensemble and score it against
the shipped blend. Reproduces every number in MODEL_ENSEMBLE.md.

    pip install -r requirements-train.txt
    python3 -m scripts.fit_model            # unconstrained -> models/ensemble-v1.*
    python3 -m scripts.fit_model --capped   # tree size capped -> models/ensemble-v1-capped.*

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
from scripts.build_panel import FEATURES, build

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


def make(learner: str, params: dict):
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
            loss="absolute_error",
            early_stopping=False,
            random_state=RANDOM_STATE,
            **params,
        )
    raise ValueError(learner)


def fit(learner: str, params: dict, rows: pd.DataFrame):
    x = rows[FEATURES].to_numpy()
    y = rows["target"].to_numpy()
    # Ridge is fitted on log1p(target): spend is right-skewed and a linear
    # model on the raw scale is dominated by a few rent payments.
    return make(learner, params).fit(x, np.log1p(y) if learner == "ridge" else y)


def predict(learner: str, model, rows: pd.DataFrame) -> np.ndarray:
    raw = model.predict(rows[FEATURES].to_numpy())
    return np.clip(np.expm1(raw) if learner == "ridge" else raw, 0.0, None)


def predict_ensemble(bundle: dict, rows: pd.DataFrame) -> np.ndarray:
    """Equal-weight mean of the three learners, on the original scale."""
    return np.mean(
        [predict(name, bundle["learners"][name], rows) for name in LEARNERS], axis=0
    )


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
    train_panel: pd.DataFrame, monthly_train: pd.DataFrame, caps: dict, log: list
):
    """
    Choose each learner's configuration by total MAE on months 13-15, fitted on
    4-12. Never sees months 16-18: both frames stop at month 15. `caps`
    override the grid's values, for --capped.

    Returns the chosen configurations, the ensemble of them and the shipped
    blend, both scored on the same validation months, so the ensemble can be
    compared with its parts and with the blend without looking at the
    holdout.
    """
    assert train_panel["month_index"].max() <= TRAIN[1]
    assert monthly_train["year"].mul(12).add(monthly_train["month"]).nunique() <= TRAIN[1]

    fit_rows = months(train_panel, SELECT_FIT)
    score_rows = months(train_panel, SELECT_SCORE)
    chosen: dict[str, dict] = {}
    validation: dict[str, np.ndarray] = {}
    for learner, candidates in GRID.items():
        best = None
        for params in candidates:
            params = {**params, **caps.get(learner, {})}
            model = fit(learner, params, fit_rows)
            result = evaluate(
                PanelForecaster(learner, score_rows, predict(learner, model, score_rows)),
                monthly_train, n_holdout=3,
            )
            log.append((learner, params, result.mae_total, result.mae_category))
            if best is None or result.mae_total < best[0]:
                best = (result.mae_total, params, predict(learner, model, score_rows))
        chosen[learner] = best[1]
        validation[learner] = best[2]

    ensemble = evaluate(
        PanelForecaster(
            "ensemble", score_rows, np.mean([validation[n] for n in LEARNERS], axis=0)
        ),
        monthly_train, n_holdout=3,
    )
    blend = evaluate(BudgetBlendForecaster(load_budgets()), monthly_train, n_holdout=3)
    return chosen, ensemble, blend


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capped", action="store_true")
    args = parser.parse_args()

    if provenance() != "platform-sandbox":
        raise SystemExit(
            "The full sandbox extract is not in data/. Run `python -m scripts.fetch_data`."
        )

    tag = "ensemble-v1-capped" if args.capped else "ensemble-v1"
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
        f"{tag}\n"
        f"select: fit {SELECT_FIT}, score {SELECT_SCORE}   final fit: {TRAIN}   "
        f"holdout: {HOLDOUT} ({month_label(monthly, HOLDOUT[0])} to "
        f"{month_label(monthly, HOLDOUT[1])})\n"
    )

    chosen, validated, validated_blend = select_config(
        train_panel, monthly_train, CAPS if args.capped else {}, log
    )
    print("Configuration, chosen on months 13-15 (total MAE; catMAE alongside)")
    for learner, params, mae, cat in log:
        mark = "  <-" if params == chosen[learner] else ""
        print(f"  {learner:12s} {str(params):70s} {mae:8.1f} {cat:8.1f}{mark}")
    print(
        f"  {'blend':12s} {'the shipped forecaster, for reference':70s} "
        f"{validated_blend.mae_total:8.1f} {validated_blend.mae_category:8.1f}"
    )
    print(
        f"  {'ensemble':12s} {'equal-weight mean of the three marked':70s} "
        f"{validated.mae_total:8.1f} {validated.mae_category:8.1f}"
    )

    bundle = {
        "features": FEATURES,
        "ridge_target": "log1p",
        "learners": {
            name: fit(name, chosen[name], train_panel) for name in LEARNERS
        },
    }

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
                            predict(name, bundle["learners"][name], holdout_rows)),
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
        "ridge_target": "log1p (predictions expm1)",
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
