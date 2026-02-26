#!/usr/bin/env python3
"""Sprint 3: Lightweight HTTP server that serves patch_metrics.prom at /metrics for Prometheus.
   Accessible only within Docker network. No auth; no sensitive data."""
import http.server
import os
import socketserver

METRICS_FILE = "/ansible/reports/patch_metrics.prom"
PORT = 9101
HOST = "0.0.0.0"

FALLBACK = """# HELP patch_run_duration_seconds Duration of last patch run
# TYPE patch_run_duration_seconds gauge
patch_run_duration_seconds 0
# HELP patch_host_success Patch success per host (1=success, 0=failure)
# TYPE patch_host_success gauge
# HELP patch_host_changed Whether host had updates applied
# TYPE patch_host_changed gauge
# HELP patch_last_run_timestamp Unix timestamp of last patch
# TYPE patch_last_run_timestamp gauge
patch_last_run_timestamp 0
# HELP patch_compliance_percentage Patch compliance (success rate) percentage
# TYPE patch_compliance_percentage gauge
patch_compliance_percentage 0
"""


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics" or self.path == "/metrics/":
            content = FALLBACK
            if os.path.isfile(METRICS_FILE):
                try:
                    with open(METRICS_FILE, "r", encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8; version=0.0.4")
            self.send_header("Content-Length", str(len(content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    with socketserver.TCPServer((HOST, PORT), MetricsHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
