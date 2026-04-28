#!/usr/bin/env python3
"""
soc_kpi_exporter.py

Expose SOC/patch KPI metrics derived from the latest Ansible patch report.
This is a real project-data exporter (not synthetic random metrics).
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
from pathlib import Path

HOST = "0.0.0.0"
PORT = 9102
REPORT_PATH = Path("/ansible/reports/patch_report_latest.json")


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_report():
    if not REPORT_PATH.exists():
        return None
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_metrics_text():
    now = int(time.time())
    report = _load_report()

    if not report:
        return "\n".join(
            [
                "# HELP soc_kpi_report_available 1 when latest patch report is present and readable.",
                "# TYPE soc_kpi_report_available gauge",
                "soc_kpi_report_available 0",
                "# HELP soc_kpi_last_collection_epoch Unix epoch when exporter served this payload.",
                "# TYPE soc_kpi_last_collection_epoch gauge",
                f"soc_kpi_last_collection_epoch {now}",
                "",
            ]
        )

    hosts = report.get("hosts", [])
    host_count = len(hosts)
    failed_count = sum(1 for h in hosts if bool(h.get("failed")))
    success_count = host_count - failed_count
    success_rate = (success_count / host_count * 100.0) if host_count else 0.0
    compliance = _safe_float(report.get("compliance_percentage"), 0.0)
    duration_seconds = _safe_float(report.get("duration_seconds"), 0.0)
    critical_cves = sum(int(h.get("critical_cves", 0) or 0) for h in hosts)
    high_cves = sum(int(h.get("high_cves", 0) or 0) for h in hosts)

    return "\n".join(
        [
            "# HELP soc_kpi_report_available 1 when latest patch report is present and readable.",
            "# TYPE soc_kpi_report_available gauge",
            "soc_kpi_report_available 1",
            "# HELP soc_kpi_last_collection_epoch Unix epoch when exporter served this payload.",
            "# TYPE soc_kpi_last_collection_epoch gauge",
            f"soc_kpi_last_collection_epoch {now}",
            "# HELP soc_kpi_patch_host_count Number of hosts in latest patch report.",
            "# TYPE soc_kpi_patch_host_count gauge",
            f"soc_kpi_patch_host_count {host_count}",
            "# HELP soc_kpi_patch_success_count Number of successfully patched hosts.",
            "# TYPE soc_kpi_patch_success_count gauge",
            f"soc_kpi_patch_success_count {success_count}",
            "# HELP soc_kpi_patch_failed_count Number of failed hosts in latest run.",
            "# TYPE soc_kpi_patch_failed_count gauge",
            f"soc_kpi_patch_failed_count {failed_count}",
            "# HELP soc_kpi_patch_success_rate_percent Successful hosts percentage.",
            "# TYPE soc_kpi_patch_success_rate_percent gauge",
            f"soc_kpi_patch_success_rate_percent {success_rate:.2f}",
            "# HELP soc_kpi_patch_compliance_percent Compliance percentage from report.",
            "# TYPE soc_kpi_patch_compliance_percent gauge",
            f"soc_kpi_patch_compliance_percent {compliance:.2f}",
            "# HELP soc_kpi_patch_duration_seconds Patch run duration in seconds.",
            "# TYPE soc_kpi_patch_duration_seconds gauge",
            f"soc_kpi_patch_duration_seconds {duration_seconds:.2f}",
            "# HELP soc_kpi_patch_critical_cves_total Sum of critical CVEs across hosts.",
            "# TYPE soc_kpi_patch_critical_cves_total gauge",
            f"soc_kpi_patch_critical_cves_total {critical_cves}",
            "# HELP soc_kpi_patch_high_cves_total Sum of high CVEs across hosts.",
            "# TYPE soc_kpi_patch_high_cves_total gauge",
            f"soc_kpi_patch_high_cves_total {high_cves}",
            "",
        ]
    )


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/metrics"):
            payload = build_metrics_text().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    HTTPServer((HOST, PORT), Handler).serve_forever()
