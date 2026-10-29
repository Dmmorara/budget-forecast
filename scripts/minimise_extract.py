"""
Write a minimal, pseudonymised slice of the sandbox extract to data/public/.

    python3 -m scripts.minimise_extract

WHY THIS EXISTS
---------------
The deployed service builds from the repository, so anything it serves must be
committed — and a Render free-tier URL is public and unauthenticated. Shipping
the sandbox extract as fetched would publish four files, two of which carry
personal names, when the service reads neither of them.

So this writes the smallest thing that still demonstrates the service on real
sandbox shape:

  columns     only the four `app.data` actually reads, plus the budget. Every
              name, description, anomaly flag and platform identifier is left
              behind on the machine that fetched them.
  files       spending records and budgets only. households.csv and
              dependants.csv - the files holding first_name, last_name,
              full_name and relationship - are never read by the service and
              are never written here.
  households  a sample rather than all 500, so the committed file stays a few
              megabytes rather than roughly twenty-five.
  identifiers platform UUIDs are replaced with opaque local ids. The sandbox
              is synthetic, so this is not de-identification of real people -
              it removes the join key that would let anyone holding the sandbox
              link these rows back to the names in households.csv.

The supervisor states the sandbox is synthetic, and that is almost certainly
true. This is written so the claim does not have to carry the whole weight: the
minimisation is cheap, and it is the same discipline this pipeline will need on
the day it carries real M-Pesa data.

The full extract stays in data/, gitignored, and `app.data` prefers it when
present - so local evaluation keeps using all 500 households while the
deployment serves this slice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = DATA_DIR / "public"

DEFAULT_HOUSEHOLDS = 60


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--households", type=int, default=DEFAULT_HOUSEHOLDS)
    parser.add_argument("--seed", type=int, default=37)
    args = parser.parse_args()

    source = DATA_DIR / "spending_records.csv"
    budgets = DATA_DIR / "budget_categories.csv"
    if not source.exists():
        sys.exit(
            f"No {source}. Run `python3 -m scripts.fetch_data` first — this "
            "script slices a local extract, it does not fetch one."
        )

    records = pd.read_csv(source)
    user_col = "user_profile_id" if "user_profile_id" in records.columns else "user_id"

    # A stable, sorted sample so repeated runs produce the same slice and the
    # demo's household ids stay valid between deployments.
    households = sorted(records[user_col].astype(str).unique())
    rng = pd.Series(households).sample(
        n=min(args.households, len(households)), random_state=args.seed
    )
    keep = sorted(rng.tolist())
    alias = {real: f"h{i + 1:03d}" for i, real in enumerate(keep)}

    slim = records[records[user_col].astype(str).isin(alias)].copy()
    slim["user_id"] = slim[user_col].astype(str).map(alias)
    slim = slim[["user_id", "transaction_date", "category", "amount_kes"]]
    slim = slim.sort_values(["user_id", "transaction_date"])

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out_records = PUBLIC_DIR / "spending_records.csv"
    slim.to_csv(out_records, index=False)

    written = [out_records]
    if budgets.exists():
        raw = pd.read_csv(budgets)
        bud_user = "user_profile_id" if "user_profile_id" in raw.columns else "user_id"
        slim_b = raw[raw[bud_user].astype(str).isin(alias)].copy()
        slim_b["user_id"] = slim_b[bud_user].astype(str).map(alias)
        slim_b = (
            slim_b.groupby(["user_id", "category"], as_index=False)["allocated_kes"]
            .median()
        )
        out_budgets = PUBLIC_DIR / "budget_categories.csv"
        slim_b.to_csv(out_budgets, index=False)
        written.append(out_budgets)

    print(f"{len(keep)} households of {len(households)}, "
          f"{len(slim):,} records of {len(records):,}\n")
    for path in written:
        size = path.stat().st_size / 1_000_000
        print(f"  {path.relative_to(ROOT)}  {size:.1f} MB  "
              f"columns: {list(pd.read_csv(path, nrows=0).columns)}")

    print("\nNo names, descriptions, anomaly flags or platform identifiers were written.")
    print("households.csv and dependants.csv were not read.")
    print("\nSample household ids for the demo:")
    for ident in list(alias.values())[:6]:
        print(f"  {ident}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
