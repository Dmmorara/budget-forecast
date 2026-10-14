"""
Check that a deployed budget-forecast answers its contract.

    python3 -m scripts.smoke_test https://budget-forecast-xxxx.onrender.com
    python3 -m scripts.smoke_test                      # defaults to localhost:8000

Written to be run against the live URL before telling Benjamin it is ready,
and again after any redeploy. It asserts the shape three other teams depend
on, not merely that the service is up: a 200 from /health says the process is
running, which is not the same claim as "U-CS 38 can integrate against this".

Exits non-zero if anything fails, so it can gate a deploy.
"""

from __future__ import annotations

import sys
import time

import httpx

DEFAULT_URL = "http://localhost:8000"

# Render's free plan sleeps after inactivity and takes roughly 50 seconds to
# wake. A short timeout here would report a working service as broken.
TIMEOUT = 90.0


class Failure(Exception):
    pass


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        raise Failure(label)


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL).rstrip("/")
    print(f"budget-forecast smoke test against {base}\n")

    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)

    try:
        print("health")
        started = time.monotonic()
        response = client.get(f"{base}/health")
        elapsed = time.monotonic() - started
        check("GET /health returns 200", response.status_code == 200, str(response.status_code))
        check("status is ok", response.json().get("status") == "ok", response.text)
        if elapsed > 10:
            print(f"  NOTE  took {elapsed:.0f}s — the instance was asleep (free plan)")

        print("\nvalidation")
        empty = client.post(f"{base}/forecast", json={})
        check(
            "POST /forecast {} is rejected with 422",
            empty.status_code == 422,
            f"got {empty.status_code} — a forecast for nobody should not be a 200",
        )
        bad_month = client.post(
            f"{base}/forecast", json={"userId": "x", "month": 13, "year": 2026}
        )
        check("month 13 is rejected", bad_month.status_code == 422, str(bad_month.status_code))

        print("\ncontract")
        # A household the synthetic population always contains. Once the real
        # extract is loaded this needs a real userId.
        body = {"userId": "steady_tenant-01", "month": 11, "year": 2026}
        response = client.post(f"{base}/forecast", json=body)
        check("POST /forecast returns 200", response.status_code == 200, response.text)
        payload = response.json()

        for field in ("estimatedTotal", "breakdown", "confidence", "riskFlag"):
            check(f"{field} present", field in payload, str(sorted(payload)))

        check(
            "estimatedTotal is a non-negative number",
            isinstance(payload["estimatedTotal"], (int, float))
            and payload["estimatedTotal"] >= 0,
            repr(payload["estimatedTotal"]),
        )
        check(
            "confidence is between 0 and 1",
            0.0 <= payload["confidence"] <= 1.0,
            repr(payload["confidence"]),
        )
        check("breakdown is an object", isinstance(payload["breakdown"], dict))

        if payload["breakdown"]:
            total = sum(payload["breakdown"].values())
            check(
                "breakdown sums to estimatedTotal",
                abs(total - payload["estimatedTotal"]) < 0.5,
                f"{total} vs {payload['estimatedTotal']}",
            )

        low, high = payload.get("estimatedTotalLow"), payload.get("estimatedTotalHigh")
        if low is not None and high is not None:
            check(
                "interval brackets the forecast",
                low <= payload["estimatedTotal"] <= high,
                f"[{low}, {high}] vs {payload['estimatedTotal']}",
            )

        print("\nprovenance")
        if payload.get("isSynthetic"):
            print("  NOTE  isSynthetic is true — this service is answering from")
            print("        generated data. No figure from it describes a real")
            print("        household. Expected until the staging extract is loaded.")
        else:
            print("  NOTE  isSynthetic is false — answering from a real extract.")

        print(f"\n  method: {payload.get('method')}")
        print("\nall checks passed")
        return 0

    except Failure:
        print("\nsmoke test FAILED")
        return 1
    except httpx.HTTPError as error:
        print(f"\n  FAIL  could not reach {base}: {error}")
        print("\nsmoke test FAILED — is the service running and the URL right?")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
