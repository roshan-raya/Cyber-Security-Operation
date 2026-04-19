#!/usr/bin/env python3
"""Create TheHive cases automatically from generated log thresholds."""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "log_profiles.json"
STATE_PATH = ROOT / "state" / "metrics.json"
ALERTER_STATE_PATH = ROOT / "state" / "alerter_state.json"
API_KEY_FILE = ROOT.parent / "thehive" / "setup" / "api_key.txt"
THEHIVE_URL = os.getenv("THEHIVE_URL", "http://localhost:9000").rstrip("/")
ORG = os.getenv("THEHIVE_ORG_NAME", "CatnipGamesSOC")


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def thehive_headers(api_key):
    return {
        "Authorization": "Bearer %s" % api_key,
        "Content-Type": "application/json",
        "X-Organisation": ORG,
    }


class TheHiveAlerter:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.config = read_json(CONFIG_PATH, {})
        self.attack_profiles = self.config.get("attack_profiles", {})
        self.state = read_json(ALERTER_STATE_PATH, {"profiles": {}, "history": []})
        self.api_key = self._read_api_key()
        self.session = requests.Session()

    def _read_api_key(self):
        try:
            return API_KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print("Cannot read TheHive API key: %s" % exc)
            sys.exit(1)

    def _recent_profile_events(self, metrics, profile_name):
        cutoff = int(time.time()) - 30
        result = []
        for item in metrics.get("recent_events", []):
            if item.get("profile") != profile_name:
                continue
            if int(item.get("epoch", 0)) < cutoff:
                continue
            result.append(item)
        return result

    def _case_cooldown_ok(self, profile_name):
        now = int(time.time())
        profile_state = self.state.get("profiles", {}).get(profile_name, {})
        last_created = int(profile_state.get("last_created_epoch", 0))
        return (now - last_created) >= 300

    def _save_state(self):
        write_json(ALERTER_STATE_PATH, self.state)

    def _create_alert(self, api_key, profile_name, profile, count):
        source_ref = "LG-%s-%s-%s" % (
            profile_name,
            int(time.time() * 1000),
            random.randint(1000, 9999),
        )
        payload = {
            "title": "AUTO: %s threshold breached" % profile.get("display_name", profile_name),
            "description": "%s events in last 30 seconds (threshold: %s)" % (
                count,
                profile.get("auto_case_threshold", 0),
            ),
            "severity": max(profile.get("severity_range", [1, 1])),
            "tags": list(profile.get("misp_tags", [])) + ["auto-generated", "log-generator"],
            "source": "LogGenerator",
            "sourceRef": source_ref,
            "type": profile_name,
        }
        return self.session.post(
            "%s/api/v1/alert" % THEHIVE_URL,
            headers=thehive_headers(api_key),
            json=payload,
            timeout=60,
        )

    def _promote_alert(self, api_key, alert_id, profile):
        payload = {"caseTemplate": profile.get("thehive_template")}
        return self.session.post(
            "%s/api/v1/alert/%s/case" % (THEHIVE_URL, alert_id),
            headers=thehive_headers(api_key),
            json=payload,
            timeout=60,
        )

    def _add_observable(self, api_key, case_id, src_ip):
        payload = {"dataType": "ip", "data": src_ip, "message": "Log generator threshold breach", "tlp": 2}
        return self.session.post(
            "%s/api/v1/case/%s/observable" % (THEHIVE_URL, case_id),
            headers=thehive_headers(api_key),
            json=payload,
            timeout=60,
        )

    def _extract_id(self, response):
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        return data.get("_id") or data.get("id") or data.get("caseId")

    def check_once(self):
        metrics = read_json(STATE_PATH, {})
        profile_counts = metrics.get("profile_counts", {})
        created = 0
        profiles_state = self.state.setdefault("profiles", {})
        self.state.setdefault("history", [])
        for profile_name, profile in self.attack_profiles.items():
            recent_events = self._recent_profile_events(metrics, profile_name)
            count = len(recent_events)
            threshold = int(profile.get("auto_case_threshold", 0))
            profile_state = profiles_state.setdefault(profile_name, {})
            profile_state["last_seen_count"] = int(profile_counts.get(profile_name, 0))
            profile_state["last_checked_epoch"] = int(time.time())
            if count < threshold or not self._case_cooldown_ok(profile_name):
                continue
            if self.dry_run:
                print(
                    "[DRY-RUN] [AUTO-CASE] Would create case for %s | Threshold: %s | Events: %s"
                    % (profile_name, threshold, count)
                )
                continue
            alert_resp = self._create_alert(self.api_key, profile_name, profile, count)
            if alert_resp.status_code not in (200, 201):
                print("[WARN] TheHive alert create failed for %s: HTTP %s" % (profile_name, alert_resp.status_code))
                continue
            alert_id = self._extract_id(alert_resp)
            promote_resp = self._promote_alert(self.api_key, alert_id, profile)
            if promote_resp.status_code == 404:
                print("[INFO] Alert already promoted, skipping")
                created += 1
                profile_state["last_created_epoch"] = int(time.time())
                profile_state["last_case_id"] = "already-promoted"
                profile_state["last_alert_id"] = alert_id
                self.state["history"].append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "profile": profile_name,
                        "case_id": "already-promoted",
                        "events": count,
                        "threshold": threshold,
                    }
                )
                continue
            elif promote_resp.status_code not in (200, 201):
                print("[WARN] TheHive case promotion failed for %s: HTTP %s" % (profile_name, promote_resp.status_code))
                continue
            case_id = self._extract_id(promote_resp)
            unique_ips = []
            seen = set()
            for event in recent_events:
                src_ip = event.get("src_ip")
                if not src_ip or src_ip in seen:
                    continue
                seen.add(src_ip)
                unique_ips.append(src_ip)
                if len(unique_ips) >= 5:
                    break
            for src_ip in unique_ips:
                self._add_observable(self.api_key, case_id, src_ip)
            created += 1
            profile_state["last_created_epoch"] = int(time.time())
            profile_state["last_case_id"] = case_id
            profile_state["last_alert_id"] = alert_id
            self.state["history"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "profile": profile_name,
                    "case_id": case_id,
                    "events": count,
                    "threshold": threshold,
                }
            )
            print(
                "[AUTO-CASE] Created case #%s for %s\nThreshold: %s | Events: %s"
                % (case_id, profile_name, threshold, count)
            )
        if created:
            metrics["thehive_cases_created"] = int(metrics.get("thehive_cases_created", 0)) + created
            write_json(STATE_PATH, metrics)
        self._save_state()
        return created

    def run_forever(self, stop_event=None):
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            self.check_once()
            for _ in range(30):
                if stop_event is not None and stop_event.is_set():
                    return
                time.sleep(1)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    alerter = TheHiveAlerter(dry_run=args.dry_run)
    if args.daemon:
        alerter.run_forever()
    else:
        alerter.check_once()


if __name__ == "__main__":
    main()
