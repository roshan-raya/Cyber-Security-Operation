#!/usr/bin/env python3
"""Register Cortex as a TheHive connector.

TheHive 4.x exposed POST /api/v1/connector. TheHive 5.2 (StrangeBee) does not — Cortex is
configured via the container entrypoint (--cortex-hostnames / --cortex-keys). Use:

  make cortex-connect-thehive

which exports CORTEX_API_KEY from cortex_api_key.txt and recreates the thehive service.
"""
import json
import os
import sys
import time

import requests

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
CORTEX_KEY_FILE = os.path.join(os.path.dirname(__file__), "cortex_api_key.txt")
THEHIVE_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)


def read_file(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def thehive_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC"),
    }


def connector_paths():
    """TheHive 5 uses /api/v1; assignment text used /api without v1."""
    base = f"{THEHIVE_URL}/api/v1/connector"
    return base, f"{base}/Cortex/status"


def connector_exists(api_key, session):
    base, _ = connector_paths()
    headers = thehive_headers(api_key)
    r = None
    for attempt in range(12):
        try:
            r = session.get(base, headers=headers, timeout=30)
            break
        except requests.RequestException:
            if attempt == 11:
                print("[FAIL] TheHive unreachable at connector URL after retries.")
                raise
            time.sleep(10)
    if r is None:
        return False, None
    if r.status_code == 404:
        return None, r  # TheHive 5.x: no REST connector API
    if r.status_code != 200:
        return False, r
    try:
        data = r.json()
    except ValueError:
        return False, r
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("connectors") or data.get("data") or []
    else:
        items = []
    for item in items:
        if isinstance(item, dict) and item.get("name") == "Cortex":
            return True, r
    return False, r


def main():
    try:
        cortex_key = read_file(CORTEX_KEY_FILE)
        thehive_key = read_file(THEHIVE_KEY_FILE)
    except OSError as exc:
        print(f"[FAIL] Missing key file: {exc}")
        sys.exit(1)

    session = requests.Session()
    base, status_url = connector_paths()

    exists, list_resp = connector_exists(thehive_key, session)
    if exists is None:
        print(
            "[OK] TheHive 5.x has no /api/v1/connector API; Cortex is set via Docker "
            "(--cortex-hostnames/--cortex-keys). `make cortex-connect-thehive` applies it."
        )
        return

    if exists:
        print("[OK] Cortex connector already present in TheHive.")
    else:
        payload = {
            "name": "Cortex",
            "url": "http://cortex:9001",
            "key": cortex_key,
            "wsConfig": {},
        }
        r = session.post(
            base,
            headers=thehive_headers(thehive_key),
            json=payload,
            timeout=30,
        )
        if r.status_code in (200, 201):
            print("[OK] Cortex registered in TheHive.")
        elif r.status_code == 409:
            print("[OK] Cortex connector already registered (409).")
        else:
            print(f"[FAIL] Register Cortex: HTTP {r.status_code} {r.text[:400]}")
            sys.exit(1)

    sr = session.get(status_url, headers=thehive_headers(thehive_key), timeout=30)
    if sr.status_code == 200:
        print("[OK] Cortex connection verified (GET .../Cortex/status).")
        try:
            print(json.dumps(sr.json(), indent=2)[:800])
        except ValueError:
            pass
    else:
        print(f"[FAIL] Cortex status check: HTTP {sr.status_code} {sr.text[:400]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
