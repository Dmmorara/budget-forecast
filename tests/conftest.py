"""Shared fixtures.

The synthetic population is generated once per test session. It is
deterministic for a given seed, so every test in the suite reasons about
exactly the same 28 households and 30 months.
"""

import pytest

from app.synthetic import REFERENCE_LAST_MONTH, generate, monthly_totals


@pytest.fixture(scope="session")
def population():
    """`(records, truth, monthly)` for seed 37 — the seed used in BASELINE.md."""
    records, truth = generate(seed=37, last_month=REFERENCE_LAST_MONTH)
    return records, truth, monthly_totals(records)
