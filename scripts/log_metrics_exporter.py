#!/usr/bin/env python3
"""Synthetic Prometheus gauges for demo dashboards (log-generator service).

Exposes catnip_synthetic_* metrics on :9104. This is the container behind the
compose service name ``log-generator`` (some docs refer to it as a log API).
"""
from __future__ import annotations

import http.server
import math
import socketserver
import time

PORT = 9104
HOST = "0.0.0.0"
_T0 = time.time()


def _metrics_body() -> str:
    t = time.time() - _T0
    log_lines = 50.0 + 20.0 * math.sin(t / 3.1)
    queue = 10.0 + 5.0 * math.sin(t / 7.0)
    sessions = 200.0 + 80.0 * math.sin(t / 11.0)
    err = 0.01 + 0.005 * (1.0 + math.sin(t / 5.0))
    err = max(0.0, min(0.5, err))
    return f"""# HELP catnip_synthetic_log_lines_per_second Demo synthetic log line rate
# TYPE catnip_synthetic_log_lines_per_second gauge
catnip_synthetic_log_lines_per_second {log_lines:.6f}
# HELP catnip_synthetic_queue_depth Demo synthetic queue depth
# TYPE catnip_synthetic_queue_depth gauge
catnip_synthetic_queue_depth {queue:.6f}
# HELP catnip_synthetic_active_sessions Demo synthetic active sessions
# TYPE catnip_synthetic_active_sessions gauge
catnip_synthetic_active_sessions {sessions:.6f}
# HELP catnip_synthetic_error_ratio Demo synthetic error ratio (0-1)
# TYPE catnip_synthetic_error_ratio gauge
catnip_synthetic_error_ratio {err:.6f}
"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/metrics", "/metrics/"):
            body = _metrics_body().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    with socketserver.TCPServer((HOST, PORT), _Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
