#!/usr/bin/env python3
"""Enable selected Cortex analysers for CatnipGamesSOC."""
import os
import sys

import requests

CORTEX_URL = os.getenv("CORTEX_URL", "http://localhost:9001").rstrip("/")
ORG = "CatnipGamesSOC"
API_KEY_FILE = os.path.join(os.path.dirname(__file__), "cortex_api_key.txt")

ANALYSERS = [
    {
        "name": "AbuseIPDB",
        "configuration": {
            "key": os.getenv("ABUSEIPDB_API_KEY", "demo_key"),
            "max_age": 90,
        },
    },
    {
        "name": "MaxMind_GeoIP",
        "configuration": {"path": "/var/lib/GeoIP"},
    },
    {
        "name": "VirusTotal_GetReport",
        "configuration": {
            "key": os.getenv("VT_API_KEY", "demo_key"),
            "polling_interval": 60,
        },
    },
    {
        "name": "Shodan_Host",
        "configuration": {"key": os.getenv("SHODAN_API_KEY", "demo_key")},
    },
    {
        "name": "MISP_2_1",
        "configuration": {
            "url": "http://misp:80",
            "key": os.getenv("MISP_THEHIVE_API_KEY", ""),
            "verifyssl": False,
            "cert_check": False,
        },
    },
]


def read_api_key():
    if not os.path.isfile(API_KEY_FILE):
        print(f"Missing {API_KEY_FILE}. Run: make cortex-init")
        sys.exit(1)
    key = open(API_KEY_FILE, encoding="utf-8").read().strip()
    if not key:
        print("Cortex API key file is empty.")
        sys.exit(1)
    return key


def list_analysers(headers):
    r = requests.get(f"{CORTEX_URL}/api/analyzer", headers=headers, timeout=60)
    if r.status_code != 200:
        print(f"GET /api/analyzer failed: HTTP {r.status_code} {r.text[:300]}")
        sys.exit(1)
    try:
        data = r.json()
    except ValueError:
        print("Non-JSON from /api/analyzer")
        sys.exit(1)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "analyzers" in data:
        return data["analyzers"]
    return []


def find_analyzer_id(analyzers, want_name):
    for row in analyzers:
        if not isinstance(row, dict):
            continue
        if row.get("name") == want_name:
            return row.get("id") or row.get("_id") or row.get("analyzerDefinitionId")
    return None


def enable_analyzer(headers, analyzer_id, configuration):
    url = f"{CORTEX_URL}/api/analyzer/{analyzer_id}/organization/{ORG}"
    payload = {"configuration": configuration}
    return requests.post(url, headers=headers, json=payload, timeout=60)


def main():
    api_key = read_api_key()
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    # Do not send Content-Type on GET /api/analyzer — Cortex parses JSON body and fails on empty input.
    post_headers = {**auth_headers, "Content-Type": "application/json"}
    analyzers = list_analysers(auth_headers)
    enabled = not_found = errors = already = 0

    for spec in ANALYSERS:
        name = spec["name"]
        aid = find_analyzer_id(analyzers, name)
        if not aid:
            print(f"[NOT FOUND] {name}")
            not_found += 1
            continue
        resp = enable_analyzer(post_headers, aid, spec["configuration"])
        if resp.status_code in (200, 201, 204):
            print(f"[ENABLED] {name}")
            enabled += 1
        elif resp.status_code == 409:
            print(f"[ALREADY ENABLED] {name}")
            already += 1
        elif resp.status_code == 400 and "already" in (resp.text or "").lower():
            print(f"[ALREADY ENABLED] {name}")
            already += 1
        else:
            print(f"[ERROR] {name} HTTP {resp.status_code}: {resp.text[:200]}")
            errors += 1

    print()
    print(
        f"Summary: {enabled} enabled, {already} already enabled, "
        f"{not_found} not found, {errors} errors"
    )
    print(
        "Note: Cortex CE images ship a subset of analysers; [NOT FOUND] is expected "
        "unless extra responder/analyser images are installed."
    )


if __name__ == "__main__":
    main()
