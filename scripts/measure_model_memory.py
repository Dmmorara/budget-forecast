"""
Resident memory of the service with and without the ensemble loaded, for the
512 MB Render free instance.

    python3 -m scripts.measure_model_memory models/ensemble-v1.joblib

Runs two fresh processes, so neither inherits the other's allocations:

  service          answers one POST /forecast through the app, as deployed
  service + model  the same, then loads the artefact, builds one household's
                   features and makes one ensemble prediction

and prints each one's current and peak resident set size. The difference is
what the model costs.

The service reads whatever app.data resolves: the full extract when it is in
data/, otherwise the 60-household slice in data/public/ that Render serves.
Run it where data/ holds only public/ to measure what the deployment would
see; the household it asks for is the first one in the data either way.

RSS is the operating system's figure, so it differs between macOS and the
Linux container Render runs. Say which when quoting it.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys

CHILD = r"""
import json, os, resource, subprocess, sys

def rss_mb():
    if sys.platform.startswith("linux"):
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())],
                         capture_output=True, text=True).stdout
    return int(out.strip()) / 1024

def peak_mb():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024

from fastapi.testclient import TestClient
from app.main import app
from app.data import load_budgets, load_monthly

monthly, _ = load_monthly()
user = sorted(monthly["user_id"].unique())[0]
response = TestClient(app).post(
    "/forecast", json={"userId": user, "month": 10, "year": 2026})
assert response.status_code == 200, response.text
out = {"service_rss": rss_mb(), "service_peak": peak_mb()}

if len(sys.argv) > 1:
    import joblib
    from app.features import features_for
    from scripts.fit_model import predict_ensemble
    bundle = joblib.load(sys.argv[1])
    rows = features_for(monthly, load_budgets(), user, 2026, 10)
    predicted = predict_ensemble(bundle, rows)
    assert len(predicted) and (predicted >= 0).all()
    out.update(model_rss=rss_mb(), model_peak=peak_mb(),
               predicted_total=float(predicted.sum()), categories=len(rows))
print(json.dumps(out))
"""


def run(*args: str) -> dict:
    done = subprocess.run(
        [sys.executable, "-c", CHILD, *args], capture_output=True, text=True
    )
    if done.returncode:
        raise SystemExit(done.stderr)
    return json.loads(done.stdout.strip().splitlines()[-1])


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    artefact = sys.argv[1]
    from app.data import provenance

    alone = run()
    loaded = run(artefact)
    print(
        f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
        f"data: {provenance()}\n"
        f"{'':28s} {'current RSS':>12s} {'peak RSS':>10s}\n"
        f"{'service, one forecast':28s} {alone['service_rss']:9.1f} MB "
        f"{alone['service_peak']:7.1f} MB\n"
        f"{'service + model, one each':28s} {loaded['model_rss']:9.1f} MB "
        f"{loaded['model_peak']:7.1f} MB\n"
        f"{'the model adds':28s} {loaded['model_rss'] - alone['service_rss']:9.1f} MB "
        f"{loaded['model_peak'] - alone['service_peak']:7.1f} MB\n"
        f"(one prediction: {loaded['categories']} categories, "
        f"total {loaded['predicted_total']:,.0f} KES)"
    )


if __name__ == "__main__":
    main()
