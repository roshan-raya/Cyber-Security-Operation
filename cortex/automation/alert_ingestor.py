#!/usr/bin/env python3
"""Create TheHive alerts from mock game-security signals and promote to cases."""
import argparse
import json
import os
import sys
import time

import requests

THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")
API_KEY_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "thehive", "setup", "api_key.txt")
)
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "ingestor_results.json")
INGEST_INTERVAL = int(os.getenv("ALERT_INGESTOR_INTERVAL", "60"))

TYPE_TO_TEMPLATE = {
    "account-compromise": "ACCOUNT_COMPROMISE",
    "bot-attack": "BOT_ATTACK",
    "social-engineering": "SOCIAL_ENGINEERING",
    "ddos": "DDOS_INFRASTRUCTURE",
    "malware": "BOT_ATTACK",
    "data-exfiltration": "ACCOUNT_COMPROMISE",
}

MOCK_ALERTS = [
    {
        "title": "Repeated failed logins - player account",
        "description": "150 failed login attempts in 5 minutes from IP 203.0.113.45",
        "severity": 2,
        "tags": ["account-compromise", "brute-force", "player-data"],
        "source": "IDS",
        "sourceRef": "IDS-2024-001",
        "type": "account-compromise",
        "observables": [{"type": "ip", "value": "203.0.113.45"}],
    },
    {
        "title": "Bot detected - matchmaking API abuse",
        "description": "Automated requests to matchmaking API at 500 req/min",
        "severity": 2,
        "tags": ["bot-attack", "game-integrity", "matchmaking"],
        "source": "WAF",
        "sourceRef": "WAF-2024-001",
        "type": "bot-attack",
        "observables": [
            {"type": "ip", "value": "198.51.100.23"},
            {"type": "url", "value": "/api/v1/matchmaking/join"},
        ],
    },
    {
        "title": "Social engineering attempt - staff email",
        "description": "Staff member received spearphishing email with malicious link",
        "severity": 3,
        "tags": ["social-engineering", "phishing", "staff"],
        "source": "EmailGateway",
        "sourceRef": "EMAIL-2024-001",
        "type": "social-engineering",
        "observables": [
            {"type": "domain", "value": "catnip-games-support.evil.com"},
            {"type": "mail", "value": "support@catnip-games-support.evil.com"},
        ],
    },
    {
        "title": "DDoS attack detected - game server cluster",
        "description": "50Gbps volumetric attack targeting game server DC1",
        "severity": 3,
        "tags": ["ddos", "infrastructure", "availability"],
        "source": "NetworkMonitor",
        "sourceRef": "NET-2024-001",
        "type": "ddos",
        "observables": [{"type": "ip", "value": "192.0.2.100"}],
    },
    {
        "title": "Suspicious admin login - off hours",
        "description": "Admin account login from unknown IP at 03:00 UTC",
        "severity": 2,
        "tags": ["account-compromise", "insider-threat", "admin"],
        "source": "SIEM",
        "sourceRef": "SIEM-2024-001",
        "type": "account-compromise",
        "observables": [{"type": "ip", "value": "203.0.113.99"}],
    },
    {
        "title": "Malware hash detected on game server",
        "description": "Known malware hash found on patch-target-3",
        "severity": 3,
        "tags": ["malware", "infrastructure", "game-server"],
        "source": "AV",
        "sourceRef": "AV-2024-001",
        "type": "malware",
        "observables": [{"type": "hash", "value": "44d88612fea8a8f36de82e1278abb02f"}],
    },
    {
        "title": "Credential stuffing campaign detected",
        "description": "10000 login attempts across 500 accounts in 1 hour",
        "severity": 3,
        "tags": ["credential-stuffing", "account-compromise", "player-data"],
        "source": "IDS",
        "sourceRef": "IDS-2024-002",
        "type": "account-compromise",
        "observables": [{"type": "ip", "value": "198.51.100.55"}],
    },
    {
        "title": "Game economy exploit attempt",
        "description": "Player account generating in-game currency at impossible rate",
        "severity": 2,
        "tags": ["bot-attack", "game-integrity", "economy"],
        "source": "GameServer",
        "sourceRef": "GAME-2024-001",
        "type": "bot-attack",
        "observables": [{"type": "other", "value": "player_id:GHI789"}],
    },
    {
        "title": "Suspicious outbound connection from game server",
        "description": "Game server establishing connection to known C2 IP",
        "severity": 3,
        "tags": ["malware", "infrastructure", "c2"],
        "source": "IDS",
        "sourceRef": "IDS-2024-003",
        "type": "malware",
        "observables": [
            {"type": "ip", "value": "192.0.2.200"},
            {"type": "domain", "value": "c2.malicious-actor.net"},
        ],
    },
    {
        "title": "Player data exfiltration attempt",
        "description": "Unusual bulk export of player records detected",
        "severity": 3,
        "tags": ["data-exfiltration", "player-data", "gdpr"],
        "source": "DLP",
        "sourceRef": "DLP-2024-001",
        "type": "data-exfiltration",
        "observables": [{"type": "ip", "value": "203.0.113.150"}],
    },
]


def count_observables_in_feed():
    return sum(len(a["observables"]) for a in MOCK_ALERTS)


def baseline_block():
    return {
        "alerts_in_feed": len(MOCK_ALERTS),
        "observables_in_feed": count_observables_in_feed(),
    }


def build_dry_run_manifest(indices):
    """indices: list of indices into MOCK_ALERTS."""
    results = []
    obs_total = 0
    for idx in indices:
        alert = MOCK_ALERTS[idx]
        template = TYPE_TO_TEMPLATE[alert["type"]]
        nobs = len(alert["observables"])
        obs_total += nobs
        results.append(
            {
                "alert_index": idx + 1,
                "title": alert["title"],
                "status": "defined",
                "case_template": template,
                "observables_count": nobs,
            }
        )
    return {
        "mode": "dry_run",
        "note": "Mock feed definition only; no TheHive API calls. Run make ingest-alerts to create cases.",
        "baseline": baseline_block(),
        "alerts_in_this_run": len(indices),
        "observables_in_this_run": obs_total,
        "seconds": 0.0,
        "results": results,
    }


def read_api_key():
    with open(API_KEY_FILE, encoding="utf-8") as fh:
        return fh.read().strip()


def headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }


def hive_datatype(obs_type):
    mapping = {"mail": "mail", "hash": "hash"}
    return mapping.get(obs_type, obs_type)


def find_alert_by_feed_key(session, api_key, alert):
    """Return alert row matching source + sourceRef + type (feed identity)."""
    body = {
        "query": [
            {"_name": "listAlert"},
            {"_name": "filter", "_field": "sourceRef", "_value": alert["sourceRef"]},
        ]
    }
    r = session.post(
        f"{THEHIVE_URL}/api/v1/query",
        headers=headers(api_key),
        json=body,
        timeout=120,
    )
    if r.status_code != 200:
        return None
    try:
        rows = r.json()
    except ValueError:
        return None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("source") == alert["source"] and row.get("type") == alert["type"]:
            return row
    return None


def create_alert(session, api_key, alert):
    payload = {
        "type": alert["type"],
        "source": alert["source"],
        "sourceRef": alert["sourceRef"],
        "title": alert["title"],
        "description": alert["description"],
        "severity": alert["severity"],
        "tags": alert["tags"],
        "tlp": 2,
        "pap": 2,
    }
    return session.post(
        f"{THEHIVE_URL}/api/v1/alert",
        headers=headers(api_key),
        json=payload,
        timeout=60,
    )


def promote_alert(session, api_key, alert_id, template):
    bodies = [{"caseTemplate": template}, {"template": template}, {}]
    last = None
    for body in bodies:
        r = session.post(
            f"{THEHIVE_URL}/api/v1/alert/{alert_id}/case",
            headers=headers(api_key),
            json=body,
            timeout=60,
        )
        last = r
        if r.status_code in (200, 201):
            return r, body
    return last, bodies[0]


def extract_case_id(resp):
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_id") or data.get("id") or data.get("caseId")


def extract_alert_id(resp):
    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_id") or data.get("id")


def add_observable(session, api_key, case_id, obs):
    dt = hive_datatype(obs["type"])
    body = {
        "dataType": dt,
        "data": obs["value"],
        "message": "Ingested from mock alert feed",
        "tlp": 2,
    }
    url = f"{THEHIVE_URL}/api/v1/case/{case_id}/observable"
    r = session.post(url, headers=headers(api_key), json=body, timeout=60)
    if r.status_code in (200, 201):
        return True, r
    alt = {
        "dataType": dt,
        "data": obs["value"],
        "message": "Ingested from mock alert feed",
        "tlp": 2,
        "_parent": {"id": case_id, "type": "case", "case": case_id},
    }
    r2 = session.post(
        f"{THEHIVE_URL}/api/v1/observable",
        headers=headers(api_key),
        json=alt,
        timeout=60,
    )
    return r2.status_code in (200, 201), r2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--single", type=int, choices=range(1, 11), metavar="N")
    args = parser.parse_args()

    if args.dry_run:
        indices = [args.single - 1] if args.single else list(range(len(MOCK_ALERTS)))
        for i in indices:
            a = MOCK_ALERTS[i]
            tpl = TYPE_TO_TEMPLATE[a["type"]]
            print(f"[DRY-RUN] Would create alert + case: {a['title']} -> {tpl}")
            for o in a["observables"]:
                print(f"            observable {o['type']}:{o['value']}")
        manifest = build_dry_run_manifest(indices)
        with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        b = manifest["baseline"]
        print()
        print("=== Summary (dry-run, no API calls) ===")
        print(f"Baseline: {b['alerts_in_feed']} alerts, {b['observables_in_feed']} observables in MOCK_ALERTS")
        print(
            f"This run: {manifest['alerts_in_this_run']} alerts, "
            f"{manifest['observables_in_this_run']} observables"
        )
        print(f"Wrote {RESULTS_PATH}")
        return

    try:
        api_key = read_api_key()
    except OSError as exc:
        print(f"Cannot read API key: {exc}")
        sys.exit(1)

    session = requests.Session()
    results = []
    total_obs = 0
    ok_cases = 0
    failed = 0
    t0 = time.time()

    idx_list = [args.single - 1] if args.single else list(range(len(MOCK_ALERTS)))

    for pos, idx in enumerate(idx_list):
        alert = MOCK_ALERTS[idx]
        template = TYPE_TO_TEMPLATE[alert["type"]]
        entry = {"alert_index": idx + 1, "title": alert["title"], "status": "failed"}

        ar = create_alert(session, api_key, alert)
        if ar.status_code not in (200, 201):
            dup = (
                ar.status_code == 400
                and "already exists" in (ar.text or "").lower()
            )
            if dup:
                hit = find_alert_by_feed_key(session, api_key, alert)
                if hit:
                    alert_id = hit.get("_id") or hit.get("id")
                    case_id = hit.get("caseId")
                    if not case_id and alert_id:
                        pr, _ = promote_alert(session, api_key, alert_id, template)
                        if pr.status_code in (200, 201):
                            case_id = extract_case_id(pr)
                    if case_id and alert_id:
                        obs_added = 0
                        for obs in alert["observables"]:
                            good, _ = add_observable(session, api_key, case_id, obs)
                            if good:
                                obs_added += 1
                            else:
                                print(
                                    f"[WARN] Observable add failed {obs['type']}:{obs['value']}"
                                )
                        total_obs += obs_added
                        ok_cases += 1
                        entry.update(
                            {
                                "status": "ok",
                                "caseId": case_id,
                                "alertId": alert_id,
                                "observables": obs_added,
                                "note": "feed_alert_already_present",
                            }
                        )
                        results.append(entry)
                        print(
                            f"[OK] Feed alert already in org — using case #{case_id}: {alert['title']}"
                        )
                        if INGEST_INTERVAL > 0 and pos < len(idx_list) - 1:
                            time.sleep(min(INGEST_INTERVAL, 5))
                        continue
            print(f"[FAIL] Alert create for {alert['title']}: HTTP {ar.status_code} {ar.text[:300]}")
            failed += 1
            results.append(entry)
            continue
        alert_id = extract_alert_id(ar)
        if not alert_id:
            print(f"[FAIL] No alert id in response for {alert['title']}")
            failed += 1
            results.append(entry)
            continue

        pr, _ = promote_alert(session, api_key, alert_id, template)
        if pr.status_code not in (200, 201):
            print(
                f"[FAIL] Promote alert {alert_id} for {alert['title']}: "
                f"HTTP {pr.status_code} {pr.text[:400]}"
            )
            failed += 1
            results.append(entry)
            continue

        case_id = extract_case_id(pr)
        if not case_id:
            print(f"[FAIL] No case id after promote for {alert['title']}")
            failed += 1
            results.append(entry)
            continue

        obs_added = 0
        for obs in alert["observables"]:
            good, _ = add_observable(session, api_key, case_id, obs)
            if good:
                obs_added += 1
            else:
                print(f"[WARN] Observable add failed {obs['type']}:{obs['value']}")
        total_obs += obs_added
        ok_cases += 1
        entry.update({"status": "ok", "caseId": case_id, "alertId": alert_id, "observables": obs_added})
        results.append(entry)
        print(f"[OK] Created case #{case_id} for alert: {alert['title']}")

        if INGEST_INTERVAL > 0 and pos < len(idx_list) - 1:
            time.sleep(min(INGEST_INTERVAL, 5))

    elapsed = time.time() - t0
    summary = {
        "mode": "live",
        "baseline": baseline_block(),
        "total_alerts": len(idx_list),
        "cases_created": ok_cases,
        "failed": failed,
        "observables_added": total_obs,
        "seconds": round(elapsed, 2),
        "results": results,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print()
    print("=== Summary ===")
    print(f"Total alerts processed: {summary['total_alerts']}")
    print(f"Cases created successfully: {ok_cases}")
    print(f"Failed alerts: {failed}")
    print(f"Total observables added: {total_obs}")
    print(f"Time taken: {elapsed:.2f}s")
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
