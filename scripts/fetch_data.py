"""
Fetch the staging extract into data/.

    python3 -m scripts.fetch_data              # log in, find the datasets, save them
    python3 -m scripts.fetch_data --discover   # just report what the API exposes

Credentials come from .env, which is gitignored. They are never printed, never
logged, and never written to disk by this script. The bearer token is shown
only as a masked prefix so you can confirm login worked.

WHY THIS IS A SCRIPT AND NOT A FEW CURL COMMANDS
------------------------------------------------
Section 5.5.6 of the report asks whether a stranger could reproduce the setup.
"Run this script" answers that; "I ran some curl commands once in October"
does not. It also means the extract can be refreshed without anyone
remembering the exact sequence, which matters because the forecast is only as
fresh as its last refresh.

ON TLS FAILURES — CHECK THE ISSUER BEFORE TRUSTING ANYTHING
------------------------------------------------------------
On 14 October 2026 this script failed with "unable to get local issuer
certificate", and the first diagnosis was that the staging host served an
incomplete chain. That was wrong. The issuer was:

    O=Fortinet, OU=Certificate Authority, CN=FG9H1GTB24901371

which is a FortiGate firewall on the network path, intercepting TLS and
re-signing it. The server was fine; the network was not.

The lesson is procedural: a certificate error says a connection could not be
verified, NOT that the far end is misconfigured. Always read the issuer before
deciding what to do about it. Pinning the certificate that appeared would have
hard-coded trust in the interceptor and hidden the problem permanently.

WASAA_API_CA_BUNDLE therefore exists for one legitimate case: pointing at a CA
certificate your institution publishes for its own inspecting proxy, which you
obtained from the institution rather than scraped off the wire. It is not for
trusting whatever certificate happens to arrive.

What this script will NOT do is disable verification. Sending a password over
a connection nobody has authenticated is exactly the attack the certificate
exists to prevent, and "it is only staging" does not change that the password
is real.

Staging only. Never production, never live M-Pesa.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
DATA_DIR = ROOT / "data"

DATASETS = ["spending_records", "budget_categories", "households", "dependants"]

# Endpoints that commonly describe an API. Checked first, because one hit here
# removes all the guesswork below.
DISCOVERY_PATHS = [
    "/api/v1/datasets",
    "/api/v1",
    "/openapi.json",
    "/swagger.json",
    "/api-docs",
    "/api/v1/docs",
    "/docs/json",
]

# Tried in order for each dataset if discovery finds nothing. Deliberately a
# short list of conventional REST shapes rather than a broad sweep: this is a
# sandbox we are authorised to use, and hammering it with guesses is neither
# polite nor likely to work.
PATH_TEMPLATES = [
    # The exact path, confirmed by the Webmasters supervisor on 14 Oct 2026.
    # The rest are fallbacks kept in case the sandbox is reorganised.
    "/api/v1/sandbox/dataset/{name}.csv",
    "/api/v1/datasets/{name}.csv",
    "/api/v1/datasets/{name}",
    "/api/v1/data/{name}.csv",
    "/api/v1/{name}.csv",
    "/api/v1/{name}",
    "/api/v1/export/{name}.csv",
]

TOKEN_KEYS = {
    "token", "access_token", "accessToken", "jwt", "idToken",
    "id_token", "authToken", "bearer",
}


def read_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        sys.exit(
            f"No .env at {ENV_FILE}.\n"
            "Copy .env.example to .env and fill in the three WASAA_ values.\n"
            ".env is gitignored and must stay that way."
        )
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def find_token(payload) -> str | None:
    """
    Search the login response for a token, whatever it is called.

    Login responses nest the token differently from one platform to the next —
    at the top level, under `data`, under `result`. Guessing one shape and
    getting `None` produces a 401 later that reads like a credentials problem,
    so the whole structure is searched instead.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in TOKEN_KEYS and isinstance(value, str) and len(value) > 20:
                return value
        for value in payload.values():
            found = find_token(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_token(item)
            if found:
                return found
    return None


def login(client: httpx.Client, base: str, email: str, password: str) -> str:
    url = f"{base}/api/v1/auth/login"
    print(f"POST {url}")

    # Some APIs want `email`, some `username`. Try the documented one first.
    for body in ({"email": email, "password": password},
                 {"username": email, "password": password}):
        response = client.post(url, json=body)
        if response.status_code == 200:
            break
        print(f"  {response.status_code} with keys {sorted(body)}")
    else:
        sys.exit(
            f"Login failed ({response.status_code}).\n"
            f"Response: {response.text[:400]}\n"
            "Check WASAA_API_BASE_URL and the credentials in .env."
        )

    try:
        payload = response.json()
    except json.JSONDecodeError:
        sys.exit(f"Login returned non-JSON: {response.text[:400]}")

    token = find_token(payload)
    if not token:
        sys.exit(
            "Logged in, but no token found in the response.\n"
            f"Top-level keys: {sorted(payload) if isinstance(payload, dict) else type(payload)}\n"
            "Add the right key name to TOKEN_KEYS in scripts/fetch_data.py."
        )

    print(f"  ok — token {token[:8]}…{token[-4:]} ({len(token)} chars)")
    return token


def discover(client: httpx.Client, base: str, headers: dict) -> None:
    print("\nLooking for an API description")
    for path in DISCOVERY_PATHS:
        try:
            response = client.get(f"{base}{path}", headers=headers)
        except httpx.HTTPError as error:
            print(f"  {path:28s} error: {error}")
            continue
        marker = "<-- look here" if response.status_code == 200 else ""
        print(f"  {response.status_code}  {path:28s} {marker}")
        if response.status_code == 200:
            body = response.text
            print(f"      {body[:600]}")
            if len(body) > 600:
                print("      …")


def save(name: str, content: bytes, content_type: str) -> pd.DataFrame | None:
    DATA_DIR.mkdir(exist_ok=True)
    target = DATA_DIR / f"{name}.csv"

    if "json" in content_type:
        payload = json.loads(content)
        # Unwrap the usual envelopes: {"data": [...]} or {"results": [...]}.
        if isinstance(payload, dict):
            for key in ("data", "results", "items", "records"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        frame = pd.DataFrame(payload)
    else:
        frame = pd.read_csv(io.BytesIO(content))

    frame.to_csv(target, index=False)
    return frame


def fetch(client: httpx.Client, base: str, headers: dict, name: str) -> bool:
    attempts: list[str] = []
    for template in PATH_TEMPLATES:
        path = template.format(name=name)
        url = f"{base}{path}"
        try:
            response = client.get(url, headers=headers)
        except httpx.HTTPError as error:
            attempts.append(f"      err  {path}  {error}")
            continue

        if response.status_code != 200:
            # Record the status rather than swallowing it. A 404 means the
            # path is wrong; a 401 or 403 means the path is RIGHT and the
            # token or permissions are not. Collapsing both into "MISS" sent
            # us looking for the wrong problem once already.
            attempts.append(f"      {response.status_code}  {path}")
            continue

        content_type = response.headers.get("content-type", "")
        try:
            frame = save(name, response.content, content_type)
        except Exception as error:  # noqa: BLE001 - report and keep trying
            print(f"  200 but unparseable at {url}: {error}")
            continue

        print(f"  OK  {name}: {len(frame):,} rows x {len(frame.columns)} cols  <- {url}")
        print(f"      columns: {list(frame.columns)}")
        return True

    print(f"  MISS  {name}: no candidate path returned 200")
    for line in attempts:
        print(line)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true",
                        help="only report what the API exposes, fetch nothing")
    args = parser.parse_args()

    env = read_env()
    base = env.get("WASAA_API_BASE_URL", "").rstrip("/")
    email = env.get("WASAA_API_EMAIL", "")
    password = env.get("WASAA_API_PASSWORD", "")

    missing = [k for k, v in {
        "WASAA_API_BASE_URL": base,
        "WASAA_API_EMAIL": email,
        "WASAA_API_PASSWORD": password,
    }.items() if not v]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")

    print(f"budget-forecast data fetch — {base}\n")

    # Verification target: the system roots by default, or a pinned PEM when
    # the host serves an incomplete or self-signed chain. Never False.
    bundle = env.get("WASAA_API_CA_BUNDLE", "").strip()
    verify: object = True
    if bundle:
        path = (ROOT / bundle) if not Path(bundle).is_absolute() else Path(bundle)
        if not path.exists():
            sys.exit(f"WASAA_API_CA_BUNDLE points at {path}, which does not exist.")
        verify = str(path)
        print(f"verifying against pinned certificate {path.name}")
        print("  (the staging host serves an incomplete chain — see the module docstring)\n")

    with httpx.Client(timeout=60.0, follow_redirects=True, verify=verify) as client:
        token = login(client, base, email, password)
        headers = {"Authorization": f"Bearer {token}"}

        discover(client, base, headers)
        if args.discover:
            print("\n--discover: stopping before fetching.")
            return 0

        print("\nFetching datasets")
        found = [name for name in DATASETS if fetch(client, base, headers, name)]

    print(f"\n{len(found)}/{len(DATASETS)} datasets saved to {DATA_DIR}")
    if len(found) < len(DATASETS):
        print(
            "\nFor the ones that missed, the path is not a shape this script\n"
            "guesses. Ask Benjamin for the exact URL and add it to\n"
            "PATH_TEMPLATES — or paste the --discover output and I will."
        )
    if found:
        print(
            "\ndata/ is gitignored. Next: check the columns above against\n"
            "COLUMN_CANDIDATES in app/data.py, then re-measure the baseline."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
