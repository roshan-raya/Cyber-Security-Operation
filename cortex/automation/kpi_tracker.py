#!/usr/bin/env python3
"""Compute SOC KPIs from TheHive cases and emit human / Prometheus reports."""
import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import requests

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
API_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)
PROM_FILE = os.path.join(os.path.dirname(__file__), "soc_kpi_metrics.prom")

# TheHive 5 uses workflow statuses such as "New" / "InProgress" for active cases;
# resolved cases use TruePositive / FalsePositive (not the string "Open" alone).
CLOSED_CASE_STATUSES = frozenset(
    {"TruePositive", "FalsePositive", "Duplicated", "Dismissed"}
)


def case_is_active(status):
    return (status or "") not in CLOSED_CASE_STATUSES


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


def list_all_alerts(session, api_key):
    body = {"query": [{"_name": "listAlert"}]}
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


def severity_label(sev):
    try:
        n = int(sev)
    except (TypeError, ValueError):
        return "low"
    if n >= 4:
        return "critical"
    if n == 3:
        return "high"
    if n == 2:
        return "medium"
    return "low"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=("human", "prometheus", "both"), default="human")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] Would query TheHive for all cases and compute KPIs.")
        return

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

    alerts_data, ar = list_all_alerts(session, api_key)
    if alerts_data is None:
        print(f"Alert query failed: HTTP {ar.status_code} {ar.text[:400]}")
        sys.exit(1)

    cases = [c for c in cases_data if isinstance(c, dict)]
    alerts = [a for a in alerts_data if isinstance(a, dict) and a.get("_type") == "Alert"]
    alerts_total = len(alerts)
    alerts_with_case = sum(1 for a in alerts if a.get("caseId"))
    alerts_no_case = alerts_total - alerts_with_case
    now_ms = int(time.time() * 1000)
    day_ago_ms = now_ms - 24 * 60 * 60 * 1000

    open_count = 0
    resolved_count = 0
    sev_counter = Counter()
    mttr_samples = []
    cases_today = 0
    sla_num = 0
    sla_den = 0
    tag_counter = Counter()

    for case in cases:
        status = case.get("status") or ""
        if case_is_active(status):
            open_count += 1
            sev_counter[severity_label(case.get("severity"))] += 1
        if status in ("TruePositive", "FalsePositive"):
            resolved_count += 1
            start = to_ms(case.get("startDate") or case.get("_createdAt") or case.get("createdAt"))
            end = to_ms(case.get("endDate") or case.get("closeDate"))
            if start is not None:
                end_use = end if end is not None else now_ms
                mttr_samples.append(max(0, (end_use - start) / 60000.0))

        start = to_ms(case.get("startDate") or case.get("_createdAt") or case.get("createdAt"))
        if start is not None and start >= day_ago_ms:
            cases_today += 1

        tags = case.get("tags") or []
        if isinstance(tags, list):
            for t in tags:
                if isinstance(t, str) and t.strip():
                    tag_counter[t.strip()] += 1

        cid = case.get("_id") or case.get("id")
        if not cid:
            continue
        tasks = get_tasks(session, api_key, cid)
        if not tasks:
            continue
        decorated = []
        for i, t in enumerate(tasks):
            order = t.get("order")
            if order is None:
                order = i
            try:
                order = int(order)
            except (TypeError, ValueError):
                order = i
            decorated.append((order, t))
        decorated.sort(key=lambda x: x[0])
        sla_den += 1
        start = to_ms(case.get("startDate") or case.get("_createdAt") or case.get("createdAt"))
        compliant = False
        if start is not None and decorated:
            first = decorated[0][1]
            st = str(first.get("status", "")).lower()
            if st in ("completed", "done", "ok"):
                end_task = to_ms(first.get("endDate") or first.get("_updatedAt"))
                if end_task is not None and end_task - start <= 15 * 60 * 1000:
                    compliant = True
        if compliant:
            sla_num += 1

    mttr = sum(mttr_samples) / len(mttr_samples) if mttr_samples else 0.0
    sla_pct = (100.0 * sla_num / sla_den) if sla_den else 0.0

    top_tags = tag_counter.most_common(5)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    human = []
    human.append("╔══════════════════════════════════════╗")
    human.append("║     Catnip Games SOC - KPI Report    ║")
    human.append("╚══════════════════════════════════════╝")
    human.append(f"Generated: {ts}")
    human.append("")
    human.append("CASE VOLUMES")
    human.append(f"├─ Open cases:        {open_count}")
    human.append(f"├─ Resolved cases:    {resolved_count}")
    human.append(f"└─ Created today:     {cases_today}")
    human.append("")
    human.append("ALERT PIPELINE (TheHive alerts ≠ cases until promoted)")
    human.append(f"├─ Imported alerts:   {alerts_total}")
    human.append(f"├─ Linked to a case:  {alerts_with_case}")
    human.append(f"└─ Pending case link: {alerts_no_case}")
    human.append("")
    human.append("OPEN CASES BY SEVERITY")
    human.append(f"├─ Critical:  {sev_counter['critical']}")
    human.append(f"├─ High:      {sev_counter['high']}")
    human.append(f"├─ Medium:    {sev_counter['medium']}")
    human.append(f"└─ Low:       {sev_counter['low']}")
    human.append("")
    human.append("PERFORMANCE")
    human.append(f"├─ MTTR:              {mttr:.1f} minutes")
    human.append(f"└─ SLA compliance:    {sla_pct:.1f}%")
    human.append("")
    human.append("TOP CATEGORIES")
    for tag, cnt in top_tags:
        human.append(f"{tag}: {cnt} cases")
    if not top_tags:
        human.append("(no tags)")
    human_text = "\n".join(human) + "\n"

    prom_lines = [
        "# HELP soc_open_cases Number of open SOC cases",
        "# TYPE soc_open_cases gauge",
        f"soc_open_cases {open_count}",
        "",
        "# HELP soc_resolved_cases Number of resolved SOC cases",
        "# TYPE soc_resolved_cases gauge",
        f"soc_resolved_cases {resolved_count}",
        "",
        "# HELP soc_mttr_minutes Mean time to resolve in minutes",
        "# TYPE soc_mttr_minutes gauge",
        f"soc_mttr_minutes {mttr:.4f}",
        "",
        "# HELP soc_sla_compliance_percent SLA compliance percentage",
        "# TYPE soc_sla_compliance_percent gauge",
        f"soc_sla_compliance_percent {sla_pct:.4f}",
        "",
        "# HELP soc_cases_today Cases created in last 24 hours",
        "# TYPE soc_cases_today gauge",
        f"soc_cases_today {cases_today}",
        "",
        "# HELP soc_alerts_total Alerts visible in TheHive (imported + triage pipeline)",
        "# TYPE soc_alerts_total gauge",
        f"soc_alerts_total {alerts_total}",
        "",
        "# HELP soc_alerts_with_case Alerts already linked to a case",
        "# TYPE soc_alerts_with_case gauge",
        f"soc_alerts_with_case {alerts_with_case}",
        "",
        "# HELP soc_alerts_without_case Alerts not yet linked to a case (e.g. not promoted)",
        "# TYPE soc_alerts_without_case gauge",
        f"soc_alerts_without_case {alerts_no_case}",
        "",
        "# HELP soc_cases_by_severity Open SOC cases by severity level",
        "# TYPE soc_cases_by_severity gauge",
        f'soc_cases_by_severity{{severity="critical"}} {sev_counter["critical"]}',
        f'soc_cases_by_severity{{severity="high"}} {sev_counter["high"]}',
        f'soc_cases_by_severity{{severity="medium"}} {sev_counter["medium"]}',
        f'soc_cases_by_severity{{severity="low"}} {sev_counter["low"]}',
        "",
    ]
    prom_text = "\n".join(prom_lines)

    if args.output in ("human", "both"):
        print(human_text, end="")
    if args.output in ("prometheus", "both"):
        print(prom_text)

    if args.output in ("prometheus", "both"):
        with open(PROM_FILE, "w", encoding="utf-8") as fh:
            fh.write(prom_text)

    if args.save:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(os.path.dirname(__file__), f"kpi_report_{stamp}.txt")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(human_text)
        print(f"Saved human report to {out_path}")


if __name__ == "__main__":
    main()
