#!/usr/bin/env python3
"""
TheHive + MISP integration smoke test (run from host with both services exposed on localhost).
"""
import os
import sys
import time

import requests

from misp_http_session import MispSession, browser_form_login
from repo_env import load_repo_dotenv

load_repo_dotenv()

THEHIVE_URL = os.environ.get("THEHIVE_URL", "http://localhost:9000").rstrip("/")
MISP_BASEURL = os.environ.get("MISP_BASEURL", "http://localhost:8080").rstrip("/")
THEHIVE_ORG = os.environ.get("THEHIVE_ORG_NAME", "CatnipGamesSOC")
MISP_ADMIN_EMAIL = os.environ.get("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
MISP_ADMIN_PASSWORD = os.environ.get("MISP_ADMIN_PASSWORD", "Nepsoft@321!")

THEHIVE_KEY_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)


def read_thehive_key():
    with open(THEHIVE_KEY_PATH, encoding="utf-8") as handle:
        return handle.read().strip()


def thehive_headers():
    return {
        "Authorization": f"Bearer {read_thehive_key()}",
        "Content-Type": "application/json",
        "X-Organisation": THEHIVE_ORG,
    }


def misp_json_headers():
    return {"Accept": "application/json", "Content-Type": "application/json"}


def create_case():
    payload = {
        "title": "MISP Integration Test - Sprint 2",
        "description": "Automated integration test",
        "severity": 1,
        "tags": ["integration-test", "sprint2"],
        "tlp": 2,
        "pap": 2,
    }
    response = requests.post(
        f"{THEHIVE_URL}/api/v1/case",
        headers=thehive_headers(),
        json=payload,
        timeout=60,
    )
    if response.status_code not in (200, 201):
        return None, response
    try:
        body = response.json()
    except ValueError:
        return None, response
    case_id = body.get("_id") or body.get("id")
    return case_id, response


def add_observable(case_id):
    attempts = [
        (
            f"{THEHIVE_URL}/api/v1/case/{case_id}/observable",
            {
                "dataType": "ip",
                "data": "198.51.100.1",
                "message": "Test IOC for MISP integration",
                "tags": ["test", "misp-lookup"],
                "tlp": 2,
            },
        ),
        (
            f"{THEHIVE_URL}/api/v1/observable",
            {
                "dataType": "ip",
                "data": "198.51.100.1",
                "message": "Test IOC for MISP integration",
                "tags": ["test", "misp-lookup"],
                "tlp": 2,
                "_parent": {"id": case_id, "type": "case", "case": case_id},
            },
        ),
    ]
    last = None
    for url, body in attempts:
        response = requests.post(url, headers=thehive_headers(), json=body, timeout=60)
        last = response
        if response.status_code in (200, 201):
            return True, response
    return False, last


def misp_search(session):
    body = {
        "returnFormat": "json",
        "value": "198.51.100.1",
        "type": "ip-dst",
        "includeEventTags": True,
    }
    response = session.post(
        f"{MISP_BASEURL}/attributes/restSearch",
        headers=misp_json_headers(),
        json=body,
        timeout=120,
    )
    return response


def main():
    start = time.time()
    case_ok = obs_ok = misp_ok = True
    case_id = None
    case_resp = None
    obs_resp = None
    misp_resp = None
    ioc_found = False

    print("TheHive + MISP integration test\n")

    try:
        read_thehive_key()
    except OSError as exc:
        print(f"[FAIL] TheHive API key: {exc}")
        sys.exit(1)

    case_id, case_resp = create_case()
    case_ok = case_id is not None
    print(f"TheHive case created: {'[OK]' if case_ok else '[FAIL]'} id={case_id!r}")
    if not case_ok:
        print(getattr(case_resp, "text", "")[:500])
        sys.exit(1)

    obs_ok, obs_resp = add_observable(case_id)
    print(f"Observable added: {'[OK]' if obs_ok else '[FAIL]'}")
    if not obs_ok:
        print(getattr(obs_resp, "text", "")[:500])

    misp_session = MispSession(MISP_BASEURL)
    if not browser_form_login(misp_session, MISP_BASEURL, MISP_ADMIN_EMAIL, MISP_ADMIN_PASSWORD):
        print("[FAIL] MISP login")
        misp_ok = False
    else:
        misp_resp = misp_search(misp_session)
        misp_ok = misp_resp.status_code in (200, 201)
        print(f"MISP lookup completed: {'[OK]' if misp_ok else '[FAIL]'} HTTP {misp_resp.status_code}")
        if misp_ok:
            try:
                data = misp_resp.json()
            except ValueError:
                data = {}
            if isinstance(data, dict) and data.get("Attribute"):
                attrs = data["Attribute"]
                if isinstance(attrs, list) and len(attrs) > 0:
                    ioc_found = True
                elif isinstance(attrs, dict):
                    ioc_found = True
            elif isinstance(data, list) and len(data) > 0:
                ioc_found = True
        else:
            print(misp_resp.text[:500])

    elapsed = time.time() - start
    print(f"IOC found in MISP: {'[YES]' if ioc_found else '[NO]'}")
    print(f"Round-trip latency: {elapsed:.2f} seconds (limit 300s)")

    # Close the test case (TheHive 5: case status is a CaseStatus value, e.g. TruePositive — not "Resolved")
    close_resp = requests.patch(
        f"{THEHIVE_URL}/api/v1/case/{case_id}",
        headers=thehive_headers(),
        json={
            "status": "TruePositive",
            "summary": "Integration test complete",
            "resolutionComment": "Integration test complete",
        },
        timeout=30,
    )
    if close_resp.status_code in (200, 204):
        print("TheHive case closed: [OK]")
    else:
        print(f"TheHive case closed: [FAIL] ({close_resp.status_code}: {close_resp.text[:200]})")

    if elapsed > 300:
        print("[FAIL] latency exceeded 300 seconds")
        sys.exit(1)
    closed_ok = close_resp.status_code in (200, 204)
    if not (case_ok and obs_ok and misp_ok and closed_ok):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
