"""
Calibrate extratrees-v2's interval by split conformal prediction, and verify
it once on the holdout.

    python3 -m scripts.calibrate_interval analyse           # months 13-15 only; writes nothing
    python3 -m scripts.calibrate_interval write --scale S   # S = absolute | relative
    python3 -m scripts.calibrate_interval verify            # months 16-18, once

Needs the full sandbox extract in data/. Synthetic.

WHY NOT CALIBRATE THE SHIPPED MODEL DIRECTLY
--------------------------------------------
extratrees-v2 was fitted on target months 4-15, so its residuals on 13-15
are in-sample and too small, and its own guard refuses those months. The
calibration model is the same configuration and random_state, fitted on
target months 4-12 for the same 440 households, and its residuals on 13-15
are out-of-sample: 1,320 household-months. It has three fewer months of
training data than the shipped model, so if anything its residuals are
larger than the shipped model's, and the interval errs wide. The 60
deployed households are in neither.

WHAT IS CALIBRATED
------------------
The residual on the monthly total, actual - predicted, signed. The interval
takes the conformal quantiles at 10% and 90% of those residuals, with the
finite-sample correction, and adds them to the point forecast:

  absolute   [pred + q_lo, pred + q_hi]                  in KES
  relative   [pred * (1 + s_lo), pred * (1 + s_hi)]      s = residual / pred

The lower bound is clipped at zero.

ONE LOOK AT THE HOLDOUT
-----------------------
`write` records the chosen scale and, before the holdout is read, the
fallback: if verified coverage falls below 80% for either household group,
the offsets are recomputed from the same 13-15 residuals at a 90% nominal
level and verified once more. `verify` records what it found in the
calibration file and refuses to run again.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from app.data import load_budgets, load_monthly, provenance
from app.evaluate import evaluate
from app.features import FEATURES
from app.forecaster import (
    SHIPPED_ARTEFACT,
    VOLATILE_REL_WIDTH,
    BudgetBlendForecaster,
    ExtraTreesForecaster,
    conformal_bounds,
)
from scripts.build_panel import build, deployed_households, training_panel
from scripts.fit_model import EXTRATREES_V1, HOLDOUT, fit, restrict

NOMINAL = 0.80
FALLBACK_NOMINAL = 0.90
CALIBRATION_FIT = (4, 12)
CALIBRATION_SCORE = (13, 15)
CALIBRATION_FILE = SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".calibration.json")


def conformal_offsets(residuals: np.ndarray, nominal: float) -> tuple[float, float]:
    """
    Lower and upper offsets for a two-sided interval at `nominal`, from the
    order statistics of the calibration residuals with the finite-sample
    correction: the floor((n+1)a/2)-th and ceil((n+1)(1-a/2))-th smallest.
    """
    r = np.sort(np.asarray(residuals, dtype=float))
    n, alpha = len(r), 1.0 - nominal
    lo = max(1, math.floor((n + 1) * alpha / 2))
    hi = min(n, math.ceil((n + 1) * (1 - alpha / 2)))
    return float(r[lo - 1]), float(r[hi - 1])


def _totals(rows: pd.DataFrame, per_row: np.ndarray, monthly: pd.DataFrame) -> pd.DataFrame:
    """Household-month predicted totals beside actual totals."""
    frame = rows[["user_id", "mkey"]].assign(pred=per_row)
    pred = frame.groupby(["user_id", "mkey"], as_index=False)["pred"].sum()
    actual = (
        monthly.assign(mkey=monthly["year"] * 12 + monthly["month"])
        .groupby(["user_id", "mkey"], as_index=False)["amount"].sum()
        .rename(columns={"amount": "actual"})
    )
    return pred.merge(actual, on=["user_id", "mkey"], how="left").fillna({"actual": 0.0})


def tree_spread(model, rows: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    """
    The 10th and 90th percentiles of the 40 trees' individual totals, per
    household-month: the interval the forest's own disagreement implies.
    """
    x = rows[FEATURES].to_numpy(dtype=float)
    per_tree = np.clip(np.stack([t.predict(x) for t in model.estimators_]), 0.0, None)
    keys = rows[["user_id", "mkey"]].reset_index(drop=True)
    tree_totals = (
        pd.DataFrame(per_tree.T).assign(**keys).groupby(["user_id", "mkey"]).sum()
    )
    spread = pd.DataFrame({
        "tree_low": np.percentile(tree_totals.to_numpy(), 10, axis=1),
        "tree_high": np.percentile(tree_totals.to_numpy(), 90, axis=1),
    }, index=tree_totals.index).reset_index()
    return spread


def calibration_set():
    """The 13-15 residuals of the 4-12 calibration model, 440 households."""
    monthly, _ = load_monthly()
    budgets = load_budgets()
    panel = build(monthly, budgets)
    served = set(deployed_households())

    model = fit("extra_trees", EXTRATREES_V1, training_panel(panel, served, *CALIBRATION_FIT))
    rows = training_panel(panel, served, *CALIBRATION_SCORE)
    point = np.clip(model.predict(rows[FEATURES].to_numpy(dtype=float)), 0.0, None)
    totals = _totals(rows, point, monthly).merge(
        tree_spread(model, rows, monthly), on=["user_id", "mkey"]
    )
    totals["residual"] = totals["actual"] - totals["pred"]
    assert totals["user_id"].nunique() == 440 and not set(totals["user_id"]) & served
    return totals


def _covered(actual, low, high) -> np.ndarray:
    return (np.asarray(low) <= np.asarray(actual)) & (np.asarray(actual) <= np.asarray(high))


def analyse(totals: pd.DataFrame) -> dict:
    pred, actual, r = totals["pred"], totals["actual"], totals["residual"]
    rel = r / pred

    abs_off = conformal_offsets(r, NOMINAL)
    rel_off = conformal_offsets(rel, NOMINAL)
    bounds = {
        "absolute": conformal_bounds(pred.to_numpy(), abs_off, "absolute"),
        "relative": conformal_bounds(pred.to_numpy(), rel_off, "relative"),
        "tree spread": (totals["tree_low"].to_numpy(), totals["tree_high"].to_numpy()),
    }

    print(
        f"Calibration: EXTRATREES_V1 fitted on targets {CALIBRATION_FIT}, residuals "
        f"on {CALIBRATION_SCORE}\n{totals['user_id'].nunique()} households, "
        f"{len(totals)} household-months, none of them deployed. SYNTHETIC.\n"
        f"mean predicted total {pred.mean():,.0f}   mean residual {r.mean():+,.1f}\n"
    )

    print("Do errors grow with magnitude? |residual| by predicted-total quintile")
    q = pd.qcut(pred, 5, labels=[f"Q{i}" for i in range(1, 6)])
    by_q = pd.DataFrame({
        "pred": pred.groupby(q, observed=True).mean(),
        "abs_err": r.abs().groupby(q, observed=True).mean(),
        "abs_err_share": (r.abs() / pred).groupby(q, observed=True).mean(),
        "cover_absolute": pd.Series(_covered(actual, *bounds["absolute"])).groupby(q.values, observed=True).mean(),
        "cover_relative": pd.Series(_covered(actual, *bounds["relative"])).groupby(q.values, observed=True).mean(),
    })
    print(by_q.round({"pred": 0, "abs_err": 0, "abs_err_share": 3,
                      "cover_absolute": 3, "cover_relative": 3}).to_string())
    spearman = float(pd.Series(pred).corr(r.abs(), method="spearman"))
    print(f"Spearman(predicted total, |residual|) = {spearman:.3f}\n")

    print(f"Offsets for a nominal {NOMINAL:.0%} interval (conformal quantiles)")
    print(f"  absolute KES      lower {abs_off[0]:+10.1f}   upper {abs_off[1]:+10.1f}")
    print(f"  relative to pred  lower {rel_off[0]:+10.4f}   upper {rel_off[1]:+10.4f}")

    print(f"\nOn months 13-15 (calibration data, so the conformal rows are ~{NOMINAL:.0%} by construction)")
    print(f"  {'interval':14s} {'coverage':>9s} {'width/point':>12s} {'width<=60% share':>17s}")
    for name, (low, high) in bounds.items():
        cover = _covered(actual, low, high).mean()
        share = (np.asarray(high) - np.asarray(low)) / pred.to_numpy()
        print(f"  {name:14s} {cover:9.1%} {np.mean(share):12.3f} "
              f"{np.mean(share <= VOLATILE_REL_WIDTH):17.1%}")

    return {"absolute": abs_off, "relative": rel_off, "spearman": spearman,
            "fallback_absolute": conformal_offsets(r, FALLBACK_NOMINAL),
            "fallback_relative": conformal_offsets(rel, FALLBACK_NOMINAL),
            "n": int(len(totals))}


def git_head() -> tuple[str, bool]:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, check=True).stdout.strip())
    return sha, dirty


def write(scale: str) -> None:
    sha, dirty = git_head()
    if dirty:
        raise SystemExit("Tracked files have uncommitted changes. Commit first.")
    found = analyse(calibration_set())
    manifest = json.loads(
        SHIPPED_ARTEFACT.with_name(SHIPPED_ARTEFACT.stem + ".manifest.json").read_text()
    )
    record = {
        "artefact": SHIPPED_ARTEFACT.name,
        "artefact_sha256": manifest["sha256"],
        "method": "split conformal on the signed residual of the monthly total "
                  "(actual - predicted); lower bound clipped at 0",
        "scale": scale,
        "nominal": NOMINAL,
        "lower": found[scale][0],
        "upper": found[scale][1],
        "both_scales": {
            "absolute_kes": {"lower": found["absolute"][0], "upper": found["absolute"][1]},
            "relative": {"lower": found["relative"][0], "upper": found["relative"][1]},
            "spearman_pred_vs_abs_residual": round(found["spearman"], 3),
        },
        "calibration": {
            "model": f"EXTRATREES_V1 {EXTRATREES_V1}, random_state 37, refitted on "
                     "target months 4-12 (2025-07 to 2026-03) for the 440 training "
                     "households; the shipped model trained on 13-15, so its own "
                     "residuals there would be in-sample",
            "residual_months": "2026-04 to 2026-06",
            "n": found["n"],
            "deployed_households_used": 0,
        },
        "fallback_if_undercovered": {
            "rule": "if verified coverage is below 80% for either household group, "
                    "recompute from the same 13-15 residuals at a 90% nominal level "
                    "and verify once more; fixed before the holdout was read",
            "nominal": FALLBACK_NOMINAL,
            "lower": found[f"fallback_{scale}"][0],
            "upper": found[f"fallback_{scale}"][1],
        },
        "git_head": sha,
        "verification": None,
    }
    CALIBRATION_FILE.write_text(json.dumps(record, indent=2) + "\n")
    print(f"\nwrote {CALIBRATION_FILE.relative_to(CALIBRATION_FILE.parent.parent)} "
          f"(scale {scale}), git_head {sha[:7]}")


def _flag_errors(rows: pd.DataFrame) -> dict:
    scored = rows[~rows["declined"]]
    flagged = scored[scored["risk_flag"] == "volatile"]
    clean = scored[scored["risk_flag"] != "volatile"]
    out = {"fires": int(len(flagged)), "of": int(len(scored))}
    for label, part in (("flagged", flagged), ("clean", clean)):
        out[f"mae_{label}"] = round(float(part["abs_error"].mean()), 1) if len(part) else None
        out[f"mape_{label}"] = round(float(part["ape"].mean() * 100), 2) if len(part) else None
    return out


def _width_share(rows: pd.DataFrame) -> float:
    scored = rows[~rows["declined"] & rows["low"].notna()]
    return float(((scored["high"] - scored["low"]) / scored["predicted_total"]).mean())


def verify() -> None:
    record = json.loads(CALIBRATION_FILE.read_text())
    attempts = (record.get("verification") or {}).get("attempts", [])
    fallback_due = len(attempts) == 1 and attempts[0]["passed"] is False
    if attempts and not fallback_due:
        raise SystemExit("The holdout has already been verified for this calibration.")
    if len(attempts) >= 2:
        raise SystemExit("Both permitted verifications have been used.")

    monthly, _ = load_monthly()
    budgets = load_budgets()
    served = set(deployed_households())
    trained = set(monthly["user_id"]) - served
    nominal_used = FALLBACK_NOMINAL if fallback_due else NOMINAL

    forecaster = ExtraTreesForecaster(budgets=budgets, use_fallback=fallback_due)
    model_rows = evaluate(forecaster, monthly, n_holdout=3)
    blend = evaluate(BudgetBlendForecaster(budgets), monthly, n_holdout=3)

    # Tree spread for the same household-months, from the shipped trees.
    panel = build(monthly, budgets)
    holdout = panel[panel["month_index"].between(*HOLDOUT)]
    spread = tree_spread(forecaster._model, holdout, monthly)

    result = {"nominal": nominal_used, "groups": {}}
    for key, users in (("trained_440", trained), ("deployed_60", served)):
        m = restrict(model_rows, users, "conformal")
        b = restrict(blend, users, "blend")
        mrows = m.rows[~m.rows["declined"]].assign(
            mkey=lambda d: d["year"] * 12 + d["month"])
        t = mrows.merge(spread, on=["user_id", "mkey"])
        tree_cover = float(_covered(t["actual_total"], t["tree_low"], t["tree_high"]).mean())
        tree_share = float(((t["tree_high"] - t["tree_low"]) / t["predicted_total"]).mean())
        tree_flag = t.assign(risk_flag=np.where(
            (t["tree_high"] - t["tree_low"]) / t["predicted_total"] > VOLATILE_REL_WIDTH,
            "volatile", None))
        result["groups"][key] = {
            "n": int(len(mrows)),
            "conformal": {"coverage": round(float(m.rows["covered"].mean()), 4),
                          "width_share": round(_width_share(m.rows), 3),
                          "volatile": _flag_errors(m.rows)},
            "tree_spread": {"coverage": round(tree_cover, 4),
                            "width_share": round(tree_share, 3),
                            "volatile": _flag_errors(tree_flag)},
            "blend": {"coverage": round(float(b.rows["covered"].mean()), 4),
                      "width_share": round(_width_share(b.rows), 3),
                      "volatile": _flag_errors(b.rows)},
        }

    passed = all(g["conformal"]["coverage"] >= NOMINAL for g in result["groups"].values())
    result["passed"] = passed
    attempts.append(result)
    record["verification"] = {"months": "2026-07 to 2026-09", "attempts": attempts}
    CALIBRATION_FILE.write_text(json.dumps(record, indent=2) + "\n")

    print(f"Holdout, months 16-18, verification {len(attempts)} "
          f"(interval nominal {nominal_used:.0%}). SYNTHETIC.\n")
    for key, g in result["groups"].items():
        print(f"── {key} ({g['n']} household-months) ──")
        print(f"  {'interval':12s} {'coverage':>9s} {'width/point':>12s} {'flag fires':>11s} "
              f"{'MAE flagged':>12s} {'MAE clean':>10s} {'MAPE fl':>8s} {'MAPE cl':>8s}")
        for name in ("blend", "conformal", "tree_spread"):
            x = g[name]; v = x["volatile"]
            print(f"  {name:12s} {x['coverage']:9.1%} {x['width_share']:12.3f} "
                  f"{v['fires']:>5d}/{v['of']:<5d} {str(v['mae_flagged']):>12s} "
                  f"{str(v['mae_clean']):>10s} {str(v['mape_flagged']):>8s} "
                  f"{str(v['mape_clean']):>8s}")
    print(f"\nconformal coverage >= {NOMINAL:.0%} in both groups: {passed}")
    if not passed and len(attempts) == 1:
        print("NFR-01 fails. Run `verify` once more to check the pre-registered fallback.")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("analyse")
    w = sub.add_parser("write")
    w.add_argument("--scale", choices=("absolute", "relative"), required=True)
    sub.add_parser("verify")
    args = parser.parse_args()

    if provenance() != "platform-sandbox":
        raise SystemExit("Needs the full sandbox extract in data/.")
    if args.cmd == "analyse":
        analyse(calibration_set())
    elif args.cmd == "write":
        write(args.scale)
    else:
        verify()


if __name__ == "__main__":
    main()
