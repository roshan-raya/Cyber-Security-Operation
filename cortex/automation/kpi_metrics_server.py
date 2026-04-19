#!/usr/bin/env python3
"""HTTP server exposing SOC KPI Prometheus textfile and periodic kpi_tracker refresh."""
import http.server
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PROM_FILE = os.path.join(ROOT, "soc_kpi_metrics.prom")
KPI_TRACKER = os.path.join(ROOT, "kpi_tracker.py")
REFRESH_SEC = 300


def run_kpi_tracker():
    subprocess.run(
        [sys.executable, KPI_TRACKER, "--output", "prometheus"],
        cwd=ROOT,
        check=False,
    )


def refresh_loop():
    while True:
        time.sleep(REFRESH_SEC)
        run_kpi_tracker()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/metrics":
            try:
                with open(PROM_FILE, encoding="utf-8") as fh:
                    body = fh.read()
            except OSError:
                body = ""
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/health":
            raw = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_error(404, "Not Found")


def main():
    run_kpi_tracker()
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", "9102"))
    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    if port == 9102:
        print("SOC KPI metrics server running on port 9102", flush=True)
    else:
        print(f"SOC KPI metrics server running on port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
