#!/usr/bin/env python3
"""Prometheus exporter for log generator state."""
import http.server
import json
import os
import threading
import time

from generator import DEFAULT_STATE_PATH, LogGenerator


STATE_PATH = str(DEFAULT_STATE_PATH)
DEFAULT_PORT = 9104
IDS_RULES = ["BOT_DETECTED", "BRUTE_FORCE", "DDOS_TRAFFIC", "DATA_EXFILTRATION"]
PROFILES = [
    "ids_alert",
    "firewall_block",
    "failed_login",
    "game_server_alert",
    "waf_alert",
    "dlp_alert",
]


def read_metrics_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault("profile_counts", {})
    data.setdefault("ids_rule_counts", {})
    data.setdefault("events_per_minute", 0)
    data.setdefault("attack_wave_active", 0)
    data.setdefault("thehive_cases_created", 0)
    data.setdefault("misp_iocs_exported", 0)
    data.setdefault("total_events", 0)
    return data


def render_metrics():
    data = read_metrics_state()
    counts = data.get("profile_counts", {})
    ids_counts = data.get("ids_rule_counts", {})
    lines = [
        "# HELP catnip_log_events_total Total security events generated",
        "# TYPE catnip_log_events_total counter",
    ]
    for profile in PROFILES:
        value = counts.get(profile, 0)
        lines.append('catnip_log_events_total{profile="%s"} %s' % (profile, value))
    lines.extend(
        [
            "",
            "# HELP catnip_events_per_minute Current event generation rate",
            "# TYPE catnip_events_per_minute gauge",
            "catnip_events_per_minute %s" % data.get("events_per_minute", 0),
            "",
            "# HELP catnip_attack_wave_active Whether an attack wave is active",
            "# TYPE catnip_attack_wave_active gauge",
            "catnip_attack_wave_active %s" % data.get("attack_wave_active", 0),
            "",
            "# HELP catnip_thehive_cases_created Cases auto-created by log generator",
            "# TYPE catnip_thehive_cases_created counter",
            "catnip_thehive_cases_created %s" % data.get("thehive_cases_created", 0),
            "",
            "# HELP catnip_misp_iocs_exported IOCs auto-exported to MISP",
            "# TYPE catnip_misp_iocs_exported counter",
            "catnip_misp_iocs_exported %s" % data.get("misp_iocs_exported", 0),
            "",
            "# HELP catnip_ids_alerts_total IDS alerts by rule",
            "# TYPE catnip_ids_alerts_total counter",
        ]
    )
    for rule in IDS_RULES:
        lines.append('catnip_ids_alerts_total{rule="%s"} %s' % (rule, ids_counts.get(rule, 0)))
    return "\n".join(lines) + "\n"


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health":
            body = json.dumps({"status": "ok", "port": self.server.server_port}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not Found")


def serve_forever(stop_event=None, port=None):
    _ = LogGenerator
    listen_port = int(os.environ.get("PORT", port or DEFAULT_PORT))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", listen_port), MetricsHandler)
    if stop_event is None:
        server.serve_forever()
        return

    def _watch():
        while not stop_event.is_set():
            time.sleep(0.5)
        server.shutdown()

    threading.Thread(target=_watch, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    serve_forever()
