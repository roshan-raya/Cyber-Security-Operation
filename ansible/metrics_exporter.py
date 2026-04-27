#!/usr/bin/env python3
"""Bridge Ansible’s filesystem reports to Prometheus pulls.

Ansible (reporting role) writes plain-text metrics to METRICS_FILE and audit history to STATE_FILE.
Prometheus does not read files directly — it scrapes HTTP — so this tiny server exposes /metrics.

End-to-end path (useful when debugging “why is my panel empty?”):
  patch_orchestrator.yml → reporting tasks → patch_metrics.prom.j2 → METRICS_FILE
  → this process merges audit gauges from STATE_FILE → Prometheus job patch_metrics in prometheus.yml
  → Grafana dashboards query the same metric/label names.

Fits into local docker-compose: the ansible service runs this script and exposes port 9101 on the network.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socketserver
import time

METRICS_FILE = "/ansible/reports/patch_metrics.prom"
STATE_FILE = "/ansible/reports/patch_audit_state.json"
PORT = 9101
HOST = "0.0.0.0"

# Labeled samples so queries like patch_run_duration_seconds{environment=~"$environment"} never go empty.
FALLBACK = """# HELP patch_run_duration_seconds Duration of last patch run
# TYPE patch_run_duration_seconds gauge
patch_run_duration_seconds{environment="unspecified",group="all"} 0
# HELP patch_host_success Patch success per host (1=success, 0=failure)
# TYPE patch_host_success gauge
# HELP patch_host_changed Whether host had updates applied
# TYPE patch_host_changed gauge
# HELP patch_last_run_timestamp Unix timestamp of last patch
# TYPE patch_last_run_timestamp gauge
patch_last_run_timestamp{environment="unspecified",group="all"} 0
# HELP patch_last_success_timestamp_seconds Unix timestamp of last successful patch completion (0 if none)
# TYPE patch_last_success_timestamp_seconds gauge
patch_last_success_timestamp_seconds{environment="unspecified",group="all"} 0
# HELP patch_compliance_percentage Patch compliance (success rate) percentage
# TYPE patch_compliance_percentage gauge
patch_compliance_percentage{environment="unspecified",group="all"} 0
# HELP patch_run_audit_timestamp Unix ms timestamp of each patch run
# TYPE patch_run_audit_timestamp gauge
patch_run_audit_timestamp{environment="unspecified",group="all",checksum="no_state"} 0
"""


def _escape_label_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _audit_header_only() -> str:
    return (
        "# HELP patch_run_audit_timestamp Unix ms timestamp of each patch run\n"
        "# TYPE patch_run_audit_timestamp gauge\n"
    )


def _audit_placeholder_line() -> str:
    """Single labeled series when no state file or no runs (avoids bare / unlabeled samples)."""
    return (
        'patch_run_audit_timestamp{environment="unspecified",group="all",checksum="no_state"} 0\n'
    )


def _audit_metrics_block() -> str:
    header = _audit_header_only()
    if not os.path.isfile(STATE_FILE):
        return header + _audit_placeholder_line()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
        if not raw:
            return header + _audit_placeholder_line()
        runs = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return header + _audit_placeholder_line() + f"# failed to read patch_audit_state.json: {exc}\n"

    if not isinstance(runs, list):
        return header + _audit_placeholder_line() + "# patch_audit_state.json must be a JSON array\n"

    lines = [
        "# HELP patch_run_audit_timestamp Unix ms timestamp of each patch run",
        "# TYPE patch_run_audit_timestamp gauge",
    ]

    for run in runs[-10:]:
        if not isinstance(run, dict):
            continue
        env = run.get("environment") or "unspecified"
        group = run.get("group") or "all"
        checksum = run.get("checksum") or "unknown"
        ts = run.get("timestamp", run.get("epoch"))
        if ts is None:
            ts = int(time.time())
        try:
            ts_int = int(ts)
        except (TypeError, ValueError):
            ts_int = int(time.time())
        # State file stores Unix seconds; exposition uses milliseconds for Grafana datetime.
        ts_ms = ts_int if ts_int > 10_000_000_000 else ts_int * 1000

        lines.append(
            "patch_run_audit_timestamp{"
            f'environment="{_escape_label_value(env)}",'
            f'group="{_escape_label_value(group)}",'
            f'checksum="{_escape_label_value(checksum)}"'
            f"}} {ts_ms}"
        )

    # Only HELP+TYPE and no samples → placeholder so Grafana never shows NaN label columns.
    if len(lines) == 2:
        lines.append(_audit_placeholder_line().rstrip("\n"))

    return "\n".join(lines) + "\n"


def _strip_duplicate_audit_type(main: str) -> str:
    """Remove legacy audit TYPE/Help from the prom file so we only emit audit once."""
    if not main.strip():
        return main
    # Drop trailing HELP/TYPE/lines for patch_run_audit_timestamp from Ansible-era files.
    pattern = re.compile(
        r"\n*# HELP patch_run_audit_timestamp[^\n]*\n"
        r"# TYPE patch_run_audit_timestamp gauge\n"
        r"(?:patch_run_audit_timestamp\{[^\n]*\n)*",
        re.MULTILINE,
    )
    return pattern.sub("\n", main).rstrip() + "\n"


_DURATION_FALLBACK = (
    "\n# HELP patch_run_duration_seconds Duration of last patch run\n"
    "# TYPE patch_run_duration_seconds gauge\n"
    'patch_run_duration_seconds{environment="unspecified",group="all"} 0\n'
)


def _ensure_patch_run_duration_seconds(content: str) -> str:
    """Grafana queries expect patch_run_duration_seconds{environment,...}; add 0 if file omits it."""
    if re.search(r"^\s*patch_run_duration_seconds\{", content, re.MULTILINE):
        return content
    return content.rstrip() + _DURATION_FALLBACK


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics" or self.path == "/metrics/":
            content = FALLBACK
            if os.path.isfile(METRICS_FILE):
                try:
                    with open(METRICS_FILE, "r", encoding="utf-8") as handle:
                        content = handle.read()
                except OSError:
                    pass
            content = _strip_duplicate_audit_type(content)
            content = _ensure_patch_run_duration_seconds(content)
            content = content.rstrip() + "\n" + _audit_metrics_block()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args):
        return


class _ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    with _ReusableTCPServer((HOST, PORT), MetricsHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
