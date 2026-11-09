"""
No household the deployed service serves may be in the shipped model's
training data.

MODEL_ENSEMBLE.md, and the report after it, claim every live forecast is
out-of-sample. That holds only while the households in
data/public/spending_records.csv stay out of the training panel. A refit that
reintroduced them would raise no error anywhere else, so these tests fail
instead.

Three layers, because CI cannot see the real data. The full extract is
gitignored, and mapping the public ids back to platform ids needs it.

  synthetic   runs everywhere. The real slicer (minimise_extract.main) and the
              real selection (build_panel.training_panel) on a small
              generated extract: every household the slicer publishes must be
              absent from the training panel.
  real        runs where data/ holds the full sandbox extract. The actual
              training panel against the actual data/public/ slice, and
              against the counts in the shipped manifest.
  manifests   runs everywhere. Every committed model manifest must record that
              no deployed household was trained on, and must match its
              artefact.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.data import DATA_DIR, PUBLIC_DIR, provenance
from scripts import minimise_extract
from scripts.build_panel import build, deployed_households, training_panel

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
EMPTY_BUDGETS = pd.DataFrame(columns=["user_id", "category", "allocated"])


def _extract(n_households: int = 20, n_months: int = 6) -> pd.DataFrame:
    """Raw records in the sandbox's own column names. Synthetic."""
    rng = np.random.default_rng(37)
    rows = []
    for h in range(n_households):
        for m in range(1, n_months + 1):
            for category in ("Groceries", "Rent"):
                rows.append({
                    "user_profile_id": f"00000000-0000-0000-0000-{h:012d}",
                    "transaction_date": f"2025-{m:02d}-15",
                    "category": category,
                    "amount_kes": float(rng.integers(1_000, 20_000)),
                })
    return pd.DataFrame(rows)


def _monthly(records: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(records["transaction_date"])
    return (
        records.assign(
            user_id=records["user_profile_id"], year=dates.dt.year, month=dates.dt.month
        )
        .groupby(["user_id", "year", "month", "category"], as_index=False)["amount_kes"]
        .sum()
        .rename(columns={"amount_kes": "amount"})
    )


@pytest.fixture
def sliced(tmp_path, monkeypatch):
    """A synthetic extract and the slice minimise_extract publishes from it."""
    records = _extract()
    data_dir, public_dir = tmp_path, tmp_path / "public"
    records.to_csv(data_dir / "spending_records.csv", index=False)
    monkeypatch.setattr(minimise_extract, "DATA_DIR", data_dir)
    monkeypatch.setattr(minimise_extract, "PUBLIC_DIR", public_dir)
    monkeypatch.setattr(minimise_extract, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["minimise_extract", "--households", "5"])
    assert minimise_extract.main() == 0
    return records, data_dir, public_dir


def test_training_panel_excludes_every_household_the_slicer_publishes(sliced):
    records, data_dir, public_dir = sliced
    deployed = deployed_households(data_dir, public_dir)

    published = set(pd.read_csv(public_dir / "spending_records.csv")["user_id"])
    assert published == set(deployed.values()), "every public id maps back"

    panel = build(_monthly(records), EMPTY_BUDGETS)
    trained = set(training_panel(panel, deployed, 4, 6)["user_id"])

    assert len(deployed) == 5
    assert not trained & set(deployed)
    assert trained == set(records["user_profile_id"]) - set(deployed)


def test_a_slice_that_no_longer_matches_refuses_to_fit(sliced):
    _, data_dir, public_dir = sliced
    public = pd.read_csv(public_dir / "spending_records.csv")
    public.iloc[1:].to_csv(public_dir / "spending_records.csv", index=False)

    with pytest.raises(SystemExit, match="does not reproduce"):
        deployed_households(data_dir, public_dir)


@pytest.mark.skipif(
    provenance() != "platform-sandbox",
    reason="needs the full sandbox extract in data/ (gitignored)",
)
def test_real_training_panel_excludes_the_deployed_households():
    pytest.importorskip("sklearn")  # scripts.fit_model needs requirements-train.txt
    from app.data import load_budgets, load_monthly
    from scripts.fit_model import TRAIN

    deployed = deployed_households(DATA_DIR, PUBLIC_DIR)
    published = set(pd.read_csv(PUBLIC_DIR / "spending_records.csv")["user_id"])
    assert published == set(deployed.values()), "every public id maps back"

    monthly, _ = load_monthly()
    trained = training_panel(build(monthly, load_budgets()), deployed, *TRAIN)

    assert not set(trained["user_id"]) & set(deployed)

    # Tie the shipped artefact to this panel, not merely to the function.
    for path in MODELS_DIR.glob("*.manifest.json"):
        manifest = json.loads(path.read_text())
        assert manifest["training_households"] == trained["user_id"].nunique()
        assert manifest["training_rows"] == len(trained)


def test_every_committed_model_records_no_deployed_household_in_training():
    manifests = sorted(MODELS_DIR.glob("*.manifest.json"))
    assert manifests, "no model manifest in models/"
    for path in manifests:
        manifest = json.loads(path.read_text())
        assert manifest.get("deployed_households_in_training") == 0, (
            f"{path.name} does not record a household-disjoint fit"
        )
        # The selection evidence must be there, or an explicit statement of
        # where it lives. A missing or null field reads as missing evidence.
        selection = manifest.get("validation")
        assert isinstance(selection, dict) and selection, (
            f"{path.name} does not record how its configuration was selected"
        )
        artefact = MODELS_DIR / manifest["artefact"]
        digest = hashlib.sha256(artefact.read_bytes()).hexdigest()
        assert digest == manifest["sha256"], f"{artefact.name} does not match its manifest"
