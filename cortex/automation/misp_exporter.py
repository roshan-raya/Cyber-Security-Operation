#!/usr/bin/env python3
"""Export resolved TheHive case IOCs into MISP events."""
import argparse
import json
import os
import sys
import time

import requests

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "misp", "setup"))

from misp_http_session import MispSession, browser_form_login  # noqa: E402

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
MISP_BASEURL = os.getenv("MISP_BASEURL", "http://localhost:8080").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
THEHIVE_KEY_FILE = os.path.join(ROOT, "thehive", "setup", "api_key.txt")
EXPORT_LOG = os.path.join(os.path.dirname(__file__), "export_log.json")

TYPE_MAP = {
    "ip": "ip-dst",
    "domain": "domain",
    "url": "url",
    "hash": "md5",
    "mail": "email-src",
    "other": "text",
}


def read_strip(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def th_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }


def run_query(session, api_key, body):
    return session.post(
        f"{THEHIVE_URL}/api/v1/query",
        headers=th_headers(api_key),
        json=body,
        timeout=120,
    )


def list_resolved_cases(session, api_key):
    body = {
        "query": [
            {"_name": "listCase"},
            {"_name": "filter", "_field": "status", "_value": "TruePositive"},
        ]
    }
    r = run_query(session, api_key, body)
    if r.status_code != 200:
        return None, r
    try:
        return r.json(), r
    except ValueError:
        return None, r


def get_observables(session, api_key, case_id):
    body = {
        "query": [
            {"_name": "getCase", "idOrName": case_id},
            {"_name": "observables"},
        ]
    }
    r = run_query(session, api_key, body)
    if r.status_code != 200:
        return None, r
    try:
        return r.json(), r
    except ValueError:
        return None, r


def map_attributes(obs_rows):
    attrs = []
    for obs in obs_rows:
        if not isinstance(obs, dict):
            continue
        dt = (obs.get("dataType") or "").lower()
        val = obs.get("data")
        if not val:
            continue
        misp_type = TYPE_MAP.get(dt)
        if not misp_type:
            continue
        attrs.append(
            {
                "type": misp_type,
                "value": str(val),
                "category": "Network activity",
                "distribution": 0,
                "to_ids": True,
            }
        )
    return attrs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    email = os.getenv("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
    password = os.getenv("MISP_ADMIN_PASSWORD", "")

    if args.dry_run:
        try:
            th_key = read_strip(THEHIVE_KEY_FILE)
        except OSError as exc:
            print(f"[DRY-RUN] TheHive API key unreadable: {exc}")
            return
        session = requests.Session()
        cases_data, cr = list_resolved_cases(session, th_key)
        if cases_data is None:
            print(f"[DRY-RUN] Would export cases but query failed: HTTP {cr.status_code}")
            return
        cases = [c for c in cases_data if isinstance(c, dict)]
        print(f"[DRY-RUN] Would export {len(cases)} TruePositive cases to MISP at {MISP_BASEURL}")
        for c in cases:
            cid = c.get("_id") or c.get("id")
            print(f"          Case {cid}: {c.get('title')}")
        return

    try:
        th_key = read_strip(THEHIVE_KEY_FILE)
    except OSError as exc:
        print(f"[FAIL] TheHive API key: {exc}")
        sys.exit(1)

    session = requests.Session()
    cases_data, cr = list_resolved_cases(session, th_key)
    if cases_data is None:
        print(f"[FAIL] list cases: HTTP {cr.status_code} {cr.text[:400]}")
        sys.exit(1)

    cases = [c for c in cases_data if isinstance(c, dict)]
    log_entries = []
    exported = skipped = failed = 0

    misp = MispSession(MISP_BASEURL)
    if not browser_form_login(misp, MISP_BASEURL, email, password):
        print("[FAIL] MISP login")
        sys.exit(1)

    for case in cases:
        case_id = case.get("_id") or case.get("id")
        title = case.get("title") or "Untitled"
        entry = {"caseId": case_id, "title": title, "status": "failed"}
        if not case_id:
            failed += 1
            log_entries.append(entry)
            continue

        obs_data, orow = get_observables(session, th_key, case_id)
        if obs_data is None:
            print(f"[FAIL] observables case {case_id}: HTTP {orow.status_code}")
            failed += 1
            log_entries.append(entry)
            continue
        obs_rows = [o for o in obs_data if isinstance(o, dict)]
        attrs = map_attributes(obs_rows)
        if not attrs:
            print(f"[SKIPPED] Case {case_id}: no exportable observables")
            skipped += 1
            entry["status"] = "skipped"
            log_entries.append(entry)
            continue

        event_payload = {
            "Event": {
                "info": f"TheHive Case {case_id}: {title}",
                "distribution": 0,
                "threat_level_id": 2,
                "analysis": 2,
                "org_id": 1,
                "Attribute": attrs,
            }
        }
        resp = misp.post(
            f"{MISP_BASEURL}/events/add",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=event_payload,
            timeout=120,
        )
        if resp.status_code not in (200, 201):
            print(f"[FAIL] Case {case_id}: MISP HTTP {resp.status_code} {resp.text[:300]}")
            failed += 1
            log_entries.append(entry)
            continue
        try:
            body = resp.json()
        except ValueError:
            body = {}
        eid = None
        if isinstance(body, dict):
            eid = (body.get("Event") or {}).get("id")
        if not eid:
            eid = body.get("id") if isinstance(body, dict) else None
        print(f"[EXPORTED] Case {case_id}: {title} → MISP event {eid}")
        exported += 1
        entry.update({"status": "exported", "mispEventId": eid})
        log_entries.append(entry)

    summary = {
        "exported": exported,
        "skipped": skipped,
        "failed": failed,
        "entries": log_entries,
        "timestamp": time.time(),
    }
    with open(EXPORT_LOG, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print()
    print(f"Summary: {exported} exported, {skipped} skipped, {failed} failed")
    print(f"Log written to {EXPORT_LOG}")


if __name__ == "__main__":
    main()
