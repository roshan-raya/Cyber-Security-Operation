#!/usr/bin/env python3
"""Queue Cortex analyser jobs for observables on open TheHive cases."""
import argparse
import json
import os
import sys
import time

import requests

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
THEHIVE_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)
CORTEX_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "setup", "cortex_api_key.txt")
)

OBS_TO_ANALYSERS = {
    "ip": ["AbuseIPDB", "MaxMind_GeoIP", "Shodan_Host"],
    "domain": ["VirusTotal_GetReport"],
    "hash": ["VirusTotal_GetReport"],
    "url": ["VirusTotal_GetReport"],
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


def list_open_cases(session, api_key):
    body = {
        "query": [
            {"_name": "listCase"},
            {"_name": "filter", "_field": "status", "_value": "Open"},
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


def normalize_datatype(dt):
    if not dt:
        return ""
    return str(dt).lower()


def start_job(session, api_key, analyzer_id, artifact_id):
    payload = {"analyzerId": analyzer_id, "artifactId": artifact_id}
    return session.post(
        f"{THEHIVE_URL}/api/v1/connector/cortex/job",
        headers=th_headers(api_key),
        json=payload,
        timeout=60,
    )


def poll_job(session, api_key, job_id, timeout_sec=300, interval=10):
    url = f"{THEHIVE_URL}/api/v1/connector/cortex/job/{job_id}"
    deadline = time.time() + timeout_sec
    last = None
    while time.time() < deadline:
        r = session.get(url, headers=th_headers(api_key), timeout=60)
        last = r
        if r.status_code != 200:
            time.sleep(interval)
            continue
        try:
            data = r.json()
        except ValueError:
            time.sleep(interval)
            continue
        status = (data.get("status") or data.get("cortexStatus") or "").lower()
        if status in ("success", "failure", "denied", "ok", "ko"):
            return data, r
        time.sleep(interval)
    return None, last


def summarize_job(data):
    if not isinstance(data, dict):
        return "no report"
    rep = data.get("report") or data.get("summary") or data.get("message")
    if isinstance(rep, str):
        return rep[:200]
    if isinstance(rep, dict):
        return json.dumps(rep)[:200]
    return json.dumps(data)[:200]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-id", dest="case_id", default=None)
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] Would list open cases and queue Cortex jobs per observable type.")
        if args.case_id:
            print(f"          Single case filter: {args.case_id}")
        return

    try:
        th_key = read_strip(THEHIVE_KEY_FILE)
        cx_key = read_strip(CORTEX_KEY_FILE)
    except OSError as exc:
        print(f"[FAIL] Key file: {exc}")
        sys.exit(1)
    if not cx_key:
        print("[FAIL] Cortex API key file is empty.")
        sys.exit(1)

    session = requests.Session()
    cases_data, cr = list_open_cases(session, th_key)
    if cases_data is None:
        print(f"[FAIL] list open cases: HTTP {cr.status_code} {cr.text[:400]}")
        sys.exit(1)

    cases = [row for row in cases_data if isinstance(row, dict)]
    if args.case_id:
        cases = [c for c in cases if c.get("_id") == args.case_id or c.get("id") == args.case_id]
        if not cases:
            print(f"[FAIL] Case {args.case_id!r} not found among open cases.")
            sys.exit(1)

    cases_processed = 0
    observables_touched = 0
    jobs_completed = 0
    jobs_failed = 0

    for case in cases:
        case_id = case.get("_id") or case.get("id")
        if not case_id:
            continue
        cases_processed += 1
        obs_list, orow = get_observables(session, th_key, case_id)
        if obs_list is None:
            print(f"[FAIL] observables for case {case_id}: HTTP {orow.status_code}")
            continue
        obs_rows = [o for o in obs_list if isinstance(o, dict)]

        for obs in obs_rows:
            oid = obs.get("_id") or obs.get("id")
            dt = normalize_datatype(obs.get("dataType"))
            val = obs.get("data") or obs.get("message") or ""
            analysers = OBS_TO_ANALYSERS.get(dt, [])
            if not oid or not analysers:
                continue
            observables_touched += 1
            for analyser in analysers:
                jr = start_job(session, th_key, analyser, oid)
                if jr.status_code not in (200, 201):
                    print(
                        f"[FAIL] {analyser} on {dt}:{val} "
                        f"HTTP {jr.status_code} {jr.text[:200]}"
                    )
                    jobs_failed += 1
                    continue
                try:
                    jb = jr.json()
                except ValueError:
                    print(f"[FAIL] {analyser}: non-JSON job response")
                    jobs_failed += 1
                    continue
                job_id = jb.get("_id") or jb.get("id") or jb.get("cortexJobId")
                if not job_id:
                    print(f"[FAIL] {analyser}: no job id in response")
                    jobs_failed += 1
                    continue
                print(f"[QUEUED] {analyser} on {dt}:{val}")
                data, pr = poll_job(session, th_key, job_id)
                if data is None:
                    print(f"[FAIL] {analyser}: timeout waiting for job {job_id}")
                    jobs_failed += 1
                    continue
                st = (data.get("status") or data.get("cortexStatus") or "").lower()
                if st in ("success", "ok"):
                    print(f"[DONE] {analyser}: {summarize_job(data)}")
                    jobs_completed += 1
                else:
                    err = data.get("errorMessage") or data.get("message") or summarize_job(data)
                    print(f"[FAIL] {analyser}: {err}")
                    jobs_failed += 1

    print()
    print("=== Summary ===")
    print(f"Cases processed: {cases_processed}")
    print(f"Observables analysed (job attempts): {observables_touched}")
    print(f"Jobs completed: {jobs_completed}")
    print(f"Jobs failed: {jobs_failed}")


if __name__ == "__main__":
    main()
