#!/usr/bin/env python3
"""Export public IOCs from generated logs to MISP."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from misp.setup.misp_http_session import MispSession, browser_form_login


ROOT = Path(__file__).resolve().parent
COMBINED_LOG = ROOT / "logs" / "combined.log"
STATE_PATH = ROOT / "state" / "exported_iocs.json"
METRICS_PATH = ROOT / "state" / "metrics.json"
DEFAULT_MISP_URL = os.getenv("MISP_BASEURL", "http://localhost:8080").rstrip("/")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z")
# Form POST /users/login counts toward MISP brute-force limits; reuse cookies between runs.
MISP_SESSION_RELOGIN_SEC = 300


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


def is_public_ip(ip_addr):
    if ip_addr.startswith("10."):
        return False
    if ip_addr.startswith("192.168."):
        return False
    if ip_addr.startswith("172."):
        return False
    parts = ip_addr.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


class MispIOCExporter:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.base_url = DEFAULT_MISP_URL
        self.email = os.getenv("MISP_ADMIN_EMAIL", "admin@catnipgames.com")
        self.password = os.getenv("MISP_ADMIN_PASSWORD", "")
        self.exported = read_json(STATE_PATH, {"ips": {}, "history": []})
        self.config = read_json(ROOT / "config" / "log_profiles.json", {})
        self.attack_profiles = self.config.get("attack_profiles", {})
        self._misp_session = None
        self._misp_login_at = 0.0

    def _misp_session_alive(self, session):
        r = session.get(
            "%s/servers/getVersion.json" % self.base_url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )
        return r.status_code == 200

    def _ensure_misp_session(self):
        """
        Return a session with a valid MISP cookie. Call browser_form_login at most
        once per MISP_SESSION_RELOGIN_SEC; otherwise reuse the session if getVersion succeeds.
        """
        if not self.password:
            return None
        now = time.time()
        if self._misp_session is not None and (now - self._misp_login_at) < MISP_SESSION_RELOGIN_SEC:
            if self._misp_session_alive(self._misp_session):
                return self._misp_session
        session = MispSession(self.base_url)
        if not browser_form_login(session, self.base_url, self.email, self.password):
            self._misp_session = None
            return None
        self._misp_session = session
        self._misp_login_at = time.time()
        return self._misp_session

    def _load_recent_events(self):
        metrics = read_json(METRICS_PATH, {})
        cutoff = int(time.time()) - 60
        out = []
        for item in metrics.get("recent_events", []):
            if int(item.get("epoch", 0)) >= cutoff:
                out.append(item)
        return out

    def _load_recent_ips_from_log(self):
        cutoff = time.time() - 60
        results = []
        if not COMBINED_LOG.exists():
            return results
        try:
            lines = COMBINED_LOG.read_text(encoding="utf-8").splitlines()[-500:]
        except OSError:
            return results
        for line in lines:
            match = TS_RE.search(line)
            if not match:
                continue
            try:
                line_ts = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                ).timestamp()
            except ValueError:
                continue
            if line_ts < cutoff:
                continue
            for ip_addr in IP_RE.findall(line):
                if is_public_ip(ip_addr):
                    results.append(ip_addr)
        return results

    def _export_ip(self, session, ip_addr, profile_name, tags):
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        event_payload = {
            "Event": {
                "info": "Catnip Games Log Generator IOC - %s" % timestamp,
                "distribution": 0,
                "threat_level_id": 2,
                "analysis": 1,
            }
        }
        event_resp = session.post(
            "%s/events/add" % self.base_url,
            json=event_payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
        )
        if event_resp.status_code not in (200, 201):
            return False
        data = event_resp.json()
        event_id = (
            data.get("Event", {}).get("id")
            or data.get("id")
            or data.get("saved", {}).get("Event", {}).get("id")
        )
        if not event_id:
            return False
        attr_payload = {
            "Attribute": {
                "type": "ip-dst",
                "value": ip_addr,
                "comment": "Auto-extracted from %s logs" % profile_name,
                "distribution": 0,
            }
        }
        attr_resp = session.post(
            "%s/attributes/add/%s" % (self.base_url, event_id),
            json=attr_payload,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
        )
        if attr_resp.status_code not in (200, 201):
            return False
        for tag in tags:
            session.post(
                "%s/tags/attachTagToObject" % self.base_url,
                json={"uuid": event_id, "tag": tag, "local": True},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=30,
            )
        return True

    def export_once(self):
        recent_events = self._load_recent_events()
        recent_public_ips = set(self._load_recent_ips_from_log())
        if self.dry_run:
            count = 0
            for item in recent_events:
                src_ip = item.get("src_ip")
                if (
                    src_ip
                    and src_ip in recent_public_ips
                    and src_ip not in self.exported.get("ips", {})
                ):
                    count += 1
            print("[DRY-RUN] [MISP] Would export %s new IOCs to MISP" % count)
            return count
        if not self.password:
            print("[WARN] MISP_ADMIN_PASSWORD missing; skipping export.")
            return 0
        session = self._ensure_misp_session()
        if not session:
            print("[WARN] MISP login failed; skipping export.")
            return 0
        exported_now = 0
        ips_state = self.exported.setdefault("ips", {})
        history = self.exported.setdefault("history", [])
        for item in recent_events:
            src_ip = item.get("src_ip")
            if not src_ip or src_ip not in recent_public_ips or src_ip in ips_state:
                continue
            profile_name = item.get("profile", "unknown")
            profile_cfg = self.attack_profiles.get(profile_name, {})
            tags = list(profile_cfg.get("misp_tags", [])) + [profile_name]
            ok = self._export_ip(session, src_ip, profile_name, tags)
            if not ok:
                continue
            exported_now += 1
            ips_state[src_ip] = {
                "profile": profile_name,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }
            history.append({"ip": src_ip, "profile": profile_name, "timestamp": datetime.now(timezone.utc).isoformat()})
        if exported_now:
            metrics = read_json(METRICS_PATH, {})
            metrics["misp_iocs_exported"] = int(metrics.get("misp_iocs_exported", 0)) + exported_now
            write_json(METRICS_PATH, metrics)
        write_json(STATE_PATH, self.exported)
        print("[MISP] Exported %s new IOCs to MISP" % exported_now)
        return exported_now

    def run_forever(self, stop_event=None):
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            self.export_once()
            for _ in range(60):
                if stop_event is not None and stop_event.is_set():
                    return
                time.sleep(1)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    exporter = MispIOCExporter(dry_run=args.dry_run)
    exporter.export_once()


if __name__ == "__main__":
    main()
