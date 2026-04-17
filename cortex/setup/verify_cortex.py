#!/usr/bin/env python3
"""Verify Cortex + TheHive integration."""
import os
import sys

import requests

CORTEX_URL = os.getenv("CORTEX_URL", "http://localhost:9001").rstrip("/")
THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = "CatnipGamesSOC"
CORTEX_KEY_FILE = os.path.join(os.path.dirname(__file__), "cortex_api_key.txt")
THEHIVE_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)


def ok(msg):
    print(f"[OK] {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")


def read_strip(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def main():
    admin_password = os.getenv("CORTEX_ADMIN_PASSWORD", "Nepsoft@123")
    failed = False

    r = requests.get(f"{CORTEX_URL}/api/status", timeout=15)
    if r.status_code == 200:
        ok("Cortex API reachable (GET /api/status)")
    else:
        fail(f"Cortex /api/status HTTP {r.status_code}")
        failed = True

    r2 = requests.get(
        f"{CORTEX_URL}/api/status",
        auth=("admin", admin_password),
        timeout=15,
    )
    if r2.status_code == 200:
        ok("Admin basic auth against /api/status")
    else:
        fail(f"Admin auth /api/status HTTP {r2.status_code}")
        failed = True

    try:
        ck = read_strip(CORTEX_KEY_FILE)
    except OSError:
        ck = ""
    if ck:
        ok("cortex_api_key.txt exists and is non-empty")
    else:
        fail("cortex_api_key.txt missing or empty")
        failed = True

    org_ok = False
    if ck:
        r3 = requests.get(
            f"{CORTEX_URL}/api/organization",
            headers={"Authorization": f"Bearer {ck}"},
            timeout=30,
        )
        if r3.status_code == 200:
            try:
                orgs = r3.json()
            except ValueError:
                orgs = []
            rows = orgs if isinstance(orgs, list) else orgs.get("organisations", [])
            for row in rows:
                if isinstance(row, dict) and row.get("name") == ORG:
                    org_ok = True
                    break
        if org_ok:
            ok(f"Organisation {ORG} exists")
        else:
            fail(f"Organisation {ORG} not found in Cortex")
            failed = True

    def analyser_linked_to_org(row, org):
        if not isinstance(row, dict):
            return False
        for key in ("organizations", "organisations", "orgs"):
            val = row.get(key)
            if isinstance(val, list):
                for o in val:
                    if isinstance(o, dict) and o.get("name") == org:
                        return True
                    if isinstance(o, str) and o == org:
                        return True
            if isinstance(val, dict) and org in val:
                return True
        return row.get("organisation") == org or row.get("organization") == org

    analyser_ok = False
    if ck:
        r4 = requests.get(
            f"{CORTEX_URL}/api/analyzer",
            headers={"Authorization": f"Bearer {ck}"},
            timeout=60,
        )
        if r4.status_code == 200:
            try:
                data = r4.json()
            except ValueError:
                data = []
            rows = data if isinstance(data, list) else data.get("analyzers", [])
            for row in rows:
                if analyser_linked_to_org(row, ORG):
                    analyser_ok = True
                    break
        if analyser_ok:
            ok("At least one analyser enabled for SOC org")
        else:
            fail("No enabled analysers detected for organisation (run make cortex-analysers)")
            failed = True

    try:
        th_key = read_strip(THEHIVE_KEY_FILE)
    except OSError:
        th_key = ""
    th_headers = {
        "Authorization": f"Bearer {th_key}",
        "Content-Type": "application/json",
        "X-Organisation": os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC"),
    }
    r5 = requests.get(f"{THEHIVE_URL}/api/v1/connector", headers=th_headers, timeout=30)
    cortex_reg = False
    if r5.status_code == 200:
        try:
            items = r5.json()
        except ValueError:
            items = []
        if isinstance(items, list):
            lst = items
        elif isinstance(items, dict):
            lst = items.get("connectors") or items.get("data") or []
        else:
            lst = []
        for it in lst:
            if isinstance(it, dict) and it.get("name") == "Cortex":
                cortex_reg = True
                break
    if cortex_reg:
        ok("Cortex registered in TheHive (connector list)")
    else:
        fail("Cortex not found in TheHive connectors (run make cortex-connect-thehive)")
        failed = True

    if failed:
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
