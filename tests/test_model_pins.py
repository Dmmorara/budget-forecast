"""
A dependency bump must not silently change what a shipped model predicts.

An ExtraTrees artefact is a pickle of scikit-learn objects. Loaded under a
different scikit-learn, numpy or pandas it may still load, still pass the
SHA-256 and feature checks, and return different numbers, so nothing at
startup would notice. Each manifest records the versions the model was fitted
under; requirements.txt pins what the image installs. These must agree, so a
PR that moves a pin without refitting fails here instead of in production.

Fix a failure by refitting under the new pins (which writes a new manifest),
or by leaving the pin where it was. Never by editing the manifest by hand.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PINNED = ("scikit-learn", "numpy", "pandas")


def requirement_pins(path: Path) -> dict[str, str]:
    """Exact `name==version` pins, keyed by lower-case name without extras."""
    pins = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(\[[^\]]*\])?\s*==\s*(\S+)", line)
        if match:
            pins[match.group(1).lower()] = match.group(3)
    return pins


MANIFESTS = sorted(MODELS_DIR.glob("*.manifest.json"))


def test_requirements_pin_every_library_a_model_depends_on():
    pins = requirement_pins(ROOT / "requirements.txt")
    for name in PINNED:
        assert name in pins, f"requirements.txt must pin {name} with =="


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.name)
def test_manifest_versions_match_requirements(path):
    pins = requirement_pins(ROOT / "requirements.txt")
    recorded = json.loads(path.read_text()).get("versions", {})
    mismatches = [
        f"{name}: model fitted under {recorded.get(name)}, requirements.txt pins {pins.get(name)}"
        for name in PINNED
        if recorded.get(name) != pins.get(name)
    ]
    assert not mismatches, f"{path.name}\n  " + "\n  ".join(mismatches)


def test_there_is_a_manifest_to_check():
    assert MANIFESTS, "no model manifest in models/"
