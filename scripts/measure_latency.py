"""
Time POST /forecast against a running service, for NFR-07.

    python3 -m scripts.measure_latency https://budget-forecast-e8ad.onrender.com
    python3 -m scripts.measure_latency <url> --requests 300
    python3 -m scripts.measure_latency                  # defaults to localhost:8000

NFR-07: when the service is warm, at least 95% of forecast requests return
within 2 seconds.

WARM IS DEFINED, NOT ASSUMED
----------------------------
Render's free plan sleeps after about 15 minutes idle and takes roughly 50
seconds to wake. The first request is timed and reported on its own as the
wake-up. If it fails, the script keeps trying until one succeeds, then sends a
few more and discards them before any request is counted.
A cold start mixed into the sample would fail the requirement for a reason
NFR-07 explicitly excludes; leaving it out silently would hide how slow the
first request of a demo is. So both are printed, and only the warm sample is
judged.

WHAT A TIMING INCLUDES
----------------------
Wall time on this machine from sending the request to having the whole body,
over one kept-alive HTTPS connection, which is how a browser running the web
app talks to the service. That includes the network both ways, so the figure
depends on where it is measured from; say where when you quote it. A failed
request (non-200 or a timeout) counts as a miss, never as a fast answer.

Households cycle through h001 to h060, the committed slice the deployment
serves, for October 2026. All of it is synthetic.

Exits non-zero if the warm sample misses the requirement.
"""

from __future__ import annotations

import argparse
import math
import platform
import sys
import time
from datetime import datetime, timezone

import httpx

DEFAULT_URL = "http://localhost:8000"
LIMIT_SECONDS = 2.0
REQUIRED_SHARE = 0.95
WARMUP_REQUESTS = 3
WAKE_ATTEMPTS = 4
HOUSEHOLDS = [f"h{n:03d}" for n in range(1, 61)]
MONTH, YEAR = 10, 2026

# Long enough to sit out a free-plan wake-up on the first request.
TIMEOUT = 90.0


def nearest_rank(sorted_values: list[float], share: float) -> float:
    """The smallest value with at least `share` of the sample at or below it."""
    return sorted_values[max(0, math.ceil(share * len(sorted_values)) - 1)]


def timed_forecast(client: httpx.Client, base: str, user: str) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        response = client.post(
            f"{base}/forecast", json={"userId": user, "month": MONTH, "year": YEAR}
        )
        ok = response.status_code == 200
    except httpx.HTTPError:
        ok = False
    return time.perf_counter() - started, ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--requests", type=int, default=200)
    args = parser.parse_args()
    base = args.url.rstrip("/")

    print(
        f"NFR-07 against {base}\n"
        f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, from {platform.node()}\n"
        f"POST /forecast, households h001-h060, {MONTH:02d}/{YEAR}. SYNTHETIC.\n"
    )

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        first, first_ok = timed_forecast(client, base, HOUSEHOLDS[0])
        state = "the service was asleep" if first > 10 else "already awake"
        print(f"first request   {first:7.2f} s  ({state}){'' if first_ok else '  FAILED'}")

        # Until one succeeds, the service is not known to be warm.
        attempts = 1
        while not first_ok and attempts < WAKE_ATTEMPTS:
            elapsed, first_ok = timed_forecast(client, base, HOUSEHOLDS[0])
            attempts += 1
            print(f"  retry         {elapsed:7.2f} s{'' if first_ok else '  FAILED'}")
        if not first_ok:
            print(f"\nNo successful answer in {WAKE_ATTEMPTS} attempts; nothing measured.")
            return 1

        for i in range(WARMUP_REQUESTS):
            timed_forecast(client, base, HOUSEHOLDS[i % len(HOUSEHOLDS)])

        results = [
            timed_forecast(client, base, HOUSEHOLDS[i % len(HOUSEHOLDS)])
            for i in range(args.requests)
        ]

    times = [elapsed for elapsed, _ in results]
    ranked = sorted(times)
    failures = sum(1 for _, ok in results if not ok)
    within = sum(1 for elapsed, ok in results if ok and elapsed <= LIMIT_SECONDS)
    share = within / len(results)

    print(f"warm requests   {len(times)}  (after {WARMUP_REQUESTS} discarded)")
    print(f"  p50           {nearest_rank(ranked, 0.50) * 1000:7.0f} ms")
    print(f"  p95           {nearest_rank(ranked, 0.95) * 1000:7.0f} ms")
    print(f"  max           {ranked[-1] * 1000:7.0f} ms")
    print(f"  failed        {failures}")
    print(f"  within {LIMIT_SECONDS:.0f} s    {within}/{len(times)} = {share:.1%}")

    passed = share >= REQUIRED_SHARE
    print(
        f"\nNFR-07 {'MET' if passed else 'NOT MET'}: "
        f"{share:.1%} within {LIMIT_SECONDS:.0f} s, requirement {REQUIRED_SHARE:.0%}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
