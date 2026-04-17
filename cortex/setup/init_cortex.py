#!/usr/bin/env python3
"""Bootstrap Cortex org, admin API key, and SOC users via REST API."""
import os
import sys
import time

import requests

CORTEX_URL = os.getenv("CORTEX_URL", "http://localhost:9001").rstrip("/")
STATUS_URL = f"{CORTEX_URL}/api/status"
MIGRATE_URL = f"{CORTEX_URL}/api/maintenance/migrate"
USER_URL = f"{CORTEX_URL}/api/user"
ORG_URL = f"{CORTEX_URL}/api/organization"
API_KEY_PATH = os.path.join(os.path.dirname(__file__), "cortex_api_key.txt")
ORG_NAME = "CatnipGamesSOC"


def get_json(url, **kwargs):
    r = requests.get(url, timeout=30, **kwargs)
    return r


def post_json(url, payload=None, **kwargs):
    return requests.post(url, json=payload, timeout=60, **kwargs)


def wait_for_cortex_ready(timeout_seconds=300, interval_seconds=10):
    print("Waiting for Cortex /api/status (HTTP 200)...")
    started = time.time()
    while time.time() - started < timeout_seconds:
        try:
            r = get_json(STATUS_URL)
            if r.status_code == 200:
                print("Cortex status endpoint returned 200.")
                return
            print(f"  ... status HTTP {r.status_code}, retry in {interval_seconds}s")
        except requests.RequestException as exc:
            print(f"  ... error: {exc}, retry in {interval_seconds}s")
        time.sleep(interval_seconds)
    print("Timed out waiting for Cortex after 5 minutes.")
    sys.exit(1)


def parse_status(body):
    if not isinstance(body, dict):
        return None, False
    status = (body.get("status") or "").strip()
    orgs = body.get("organisations") or body.get("organizations") or []
    has_orgs = isinstance(orgs, list) and len(orgs) > 0
    return status, has_orgs


def main():
    admin_password = os.getenv("CORTEX_ADMIN_PASSWORD", "Nepsoft@123")
    analyst_password = os.getenv("CORTEX_ANALYST_PASSWORD", "Nepsoft@123")

    wait_for_cortex_ready()

    print("Checking Cortex setup state...")
    r = get_json(STATUS_URL)
    if r.status_code != 200:
        print(f"GET {STATUS_URL} failed: HTTP {r.status_code}")
        sys.exit(1)
    try:
        body = r.json()
    except ValueError:
        print("Non-JSON status response")
        sys.exit(1)

    status, has_orgs = parse_status(body)
    print(f"  status={status!r} organisations={has_orgs}")

    if (status or "").lower() == "init":
        print("Running initial database migration...")
        mr = post_json(MIGRATE_URL)
        if mr.status_code not in (200, 201, 204):
            print(f"Migration HTTP {mr.status_code}: {mr.text[:500]}")
            sys.exit(1)
        print("Migration requested; waiting 30s...")
        time.sleep(30)
    elif (status or "").lower() in ("ok", "ready") and has_orgs:
        print("Cortex reports ready with organisations; skipping migration.")
    else:
        print("Proceeding without migration (state not 'init').")

    print("Creating admin user (if missing)...")
    admin_payload = {
        "login": "admin",
        "name": "SOC Admin",
        "roles": ["superAdmin", "read", "analyze", "orgAdmin"],
        "password": admin_password,
    }
    ar = post_json(USER_URL, admin_payload)
    if ar.status_code in (200, 201):
        print("Admin user created.")
    elif ar.status_code == 409:
        print("Admin user already exists (409).")
    else:
        print(f"Admin user create HTTP {ar.status_code}: {ar.text[:500]}")
        sys.exit(1)

    print("Renewing admin API key...")
    auth = requests.auth.HTTPBasicAuth("admin", admin_password)
    kr = post_json(f"{CORTEX_URL}/api/user/admin/key/renew", auth=auth)
    if kr.status_code not in (200, 201):
        print(f"Key renew HTTP {kr.status_code}: {kr.text[:500]}")
        sys.exit(1)
    try:
        key_body = kr.json()
    except ValueError:
        key_body = {}
    api_key = ""
    if isinstance(key_body, dict):
        api_key = (
            key_body.get("key")
            or key_body.get("apiKey")
            or key_body.get("value")
            or ""
        )
    if not api_key and kr.text.strip():
        api_key = kr.text.strip().strip('"')
    if not api_key:
        print("Could not parse API key from renew response.")
        sys.exit(1)

    with open(API_KEY_PATH, "w", encoding="utf-8") as fh:
        fh.write(api_key + "\n")
    print("Cortex admin API key (store securely):")
    print(f"  {api_key}")
    print(f"Saved to {API_KEY_PATH}")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print("Creating SOC organisation...")
    org_payload = {
        "name": ORG_NAME,
        "description": "Catnip Games International SOC",
        "status": "Active",
    }
    orgr = post_json(ORG_URL, org_payload, headers=headers)
    if orgr.status_code in (200, 201):
        print(f"Organisation {ORG_NAME} created.")
    elif orgr.status_code == 409:
        print(f"Organisation {ORG_NAME} already exists (409).")
    else:
        print(f"Organisation create HTTP {orgr.status_code}: {orgr.text[:500]}")
        sys.exit(1)

    print("Creating analyst user...")
    analyst_payload = {
        "login": "soc.analyst",
        "name": "SOC Analyst",
        "roles": ["read", "analyze"],
        "organization": ORG_NAME,
        "password": analyst_password,
    }
    ur = post_json(USER_URL, analyst_payload, headers=headers)
    if ur.status_code in (200, 201):
        print("Analyst user created.")
    elif ur.status_code == 409:
        print("Analyst user already exists (409).")
    else:
        print(f"Analyst create HTTP {ur.status_code}: {ur.text[:500]}")
        sys.exit(1)

    print()
    print("=== Cortex bootstrap complete ===")
    print(f"  URL:           {CORTEX_URL}")
    print("  Admin login:   admin / (CORTEX_ADMIN_PASSWORD)")
    print(f"  API key file:  {API_KEY_PATH}")
    print(f"  Organisation: {ORG_NAME}")


if __name__ == "__main__":
    main()
