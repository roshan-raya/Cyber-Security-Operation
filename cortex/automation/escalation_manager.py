#!/usr/bin/env python3
"""Auto-escalate TheHive cases that breach SLA-style thresholds."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
API_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)
LOG_PATH = os.path.join(os.path.dirname(__file__), "escalation_log.json")
CLOSED_STATUSES = {"TruePositive", "FalsePositive", "Duplicated", "Dismissed"}


def read_strip(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }


def list_all_cases(session, api_key):
    body = {"query": [{"_name": "listCase"}]}
    r = session.post(
        f"{THEHIVE_URL}/api/v1/query",
        headers=headers(api_key),
        json=body,
        timeout=120,
    )
    if r.status_code != 200:
        return None, r
    try:
        return r.json(), r
    except ValueError:
        return None, r


def get_tasks(session, api_key, case_id):
    body = {
        "query": [
            {"_name": "getCase", "idOrName": case_id},
            {"_name": "tasks"},
        ]
    }
    r = session.post(
        f"{THEHIVE_URL}/api/v1/query",
        headers=headers(api_key),
        json=body,
        timeout=120,
    )
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    return [t for t in data if isinstance(t, dict)]


def to_ms(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str) and val.isdigit():
        return int(val)
    return None


def any_task_completed(tasks):
    for t in tasks:
        st = str(t.get("status", "")).lower()
        if st in ("completed", "done", "ok"):
            return True
    return False


def add_comment(session, api_key, case_id, message):
    r = session.post(
        f"{THEHIVE_URL}/api/v1/case/{case_id}/comment",
        headers=headers(api_key),
        json={"message": message},
        timeout=60,
    )
    return r.status_code in (200, 201), r


def merge_tag(session, api_key, case_id, existing_tags, tag):
    tags = list(existing_tags) if isinstance(existing_tags, list) else []
    if tag in tags:
        return False, None
    tags.append(tag)
    r = session.patch(
        f"{THEHIVE_URL}/api/v1/case/{case_id}",
        headers=headers(api_key),
        json={"tags": tags},
        timeout=60,
    )
    return r.status_code in (200, 204), r


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case-id", dest="case_id", default=None)
    args = parser.parse_args()

    try:
        api_key = read_strip(API_KEY_FILE)
    except OSError as exc:
        print(f"Cannot read API key: {exc}")
        sys.exit(1)

    session = requests.Session()
    cases_data, cr = list_all_cases(session, api_key)
    if cases_data is None:
        print(f"Query failed: HTTP {cr.status_code} {cr.text[:400]}")
        sys.exit(1)

    cases = [c for c in cases_data if isinstance(c, dict)]
    cases = [c for c in cases if c.get("status") not in CLOSED_STATUSES]
    if args.case_id:
        cases = [
            c
            for c in cases
            if c.get("_id") == args.case_id or c.get("id") == args.case_id
        ]
        if not cases:
            print(f"No active case matching case-id {args.case_id!r}.")
            sys.exit(1)

    now_ms = int(time.time() * 1000)
    checked = len(cases)
    triggered = 0
    sla_breaches = 0
    l2_req = 0
    l3_req = 0
    events = []

    for case in cases:
        cid = case.get("_id") or case.get("id")
        if not cid:
            continue
        title = case.get("title") or "(no title)"
        sev = case.get("severity")
        try:
            sev_i = int(sev) if sev is not None else 0
        except (TypeError, ValueError):
            sev_i = 0
        start = to_ms(case.get("startDate") or case.get("_createdAt") or case.get("createdAt"))
        age_ms = (now_ms - start) if start is not None else 0
        age_min = age_ms / 60000.0 if start is not None else 0
        cstatus = str(case.get("status") or "")
        tags = case.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tasks = get_tasks(session, api_key, cid)
        completed = any_task_completed(tasks)

        act = None
        note = None
        new_tag = None
        label = None

        # Rule 3 — Critical unattended (evaluated first)
        if sev_i == 4 and age_min > 5 and "requires-l3" not in tags:
            act = "l3"
            note = "AUTO-ESCALATION: Critical severity - immediate L3"
            new_tag = "requires-l3"
            label = f"[ESCALATED] Case {cid}: {title} - requires L3 IMMEDIATE"
            l3_req += 1
        # Rule 2 — High severity unattended
        elif sev_i == 3 and age_min > 30 and cstatus == "New" and "requires-l2" not in tags:
            act = "l2"
            note = "AUTO-ESCALATION: High severity unattended (30 min)"
            new_tag = "requires-l2"
            label = f"[ESCALATED] Case {cid}: {title} - requires L2 attention"
            l2_req += 1
        # Rule 1 — Triage SLA breach
        elif (
            age_min > 15
            and sev_i >= 2
            and not completed
            and "sla-breach" not in tags
        ):
            act = "sla"
            note = "AUTO-ESCALATION: Triage SLA breached (15 min)"
            new_tag = "sla-breach"
            label = f"[ESCALATED] Case {cid}: {title} - triage SLA breached"
            sla_breaches += 1

        if act and note and new_tag and label:
            if args.dry_run:
                print(f"[DRY-RUN] {label}")
            else:
                ok_c, _ = add_comment(session, api_key, cid, note)
                ok_t, _ = merge_tag(session, api_key, cid, tags, new_tag)
                if ok_c and ok_t:
                    print(label)
                else:
                    print(f"[WARN] Case {cid}: comment/tag may have failed")
            triggered += 1
            events.append(
                {
                    "case_id": cid,
                    "title": title,
                    "action": act,
                    "dry_run": bool(args.dry_run),
                }
            )

    print()
    print(f"Cases checked: {checked}")
    print(f"Escalations triggered: {triggered}")
    print(f"SLA breaches: {sla_breaches}")
    print(f"L2 required: {l2_req}")
    print(f"L3 required: {l3_req}")

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cases_checked": checked,
        "escalations_triggered": triggered,
        "sla_breaches": sla_breaches,
        "l2_required": l2_req,
        "l3_required": l3_req,
        "events": events,
    }
    if not args.dry_run:
        with open(LOG_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)


if __name__ == "__main__":
    main()
