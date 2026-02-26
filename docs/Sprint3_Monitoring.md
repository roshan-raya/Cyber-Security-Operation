# Sprint 3 — Monitoring Integration & Alerting

Sprint 3 exposes patch run metrics to Prometheus and adds alerting plus dashboard visualisation. The Ansible container runs a lightweight HTTP metrics exporter; Prometheus scrapes it on the monitoring network. No metrics are published to the host.

---

## 1. Metrics format

After each `make patch` run, the playbook writes **`/ansible/reports/patch_metrics.prom`** in Prometheus exposition format. The file is overwritten every run.

| Metric | Type | Description |
|--------|------|-------------|
| `patch_run_duration_seconds` | gauge | Duration of the last patch run (seconds). |
| `patch_host_success{host="..."}` | gauge | 1 = success, 0 = failure per host. |
| `patch_host_changed{host="..."}` | gauge | 1 = updates applied, 0 = no changes. |
| `patch_last_run_timestamp` | gauge | Unix timestamp of the last patch run. |

No hostnames or other sensitive data beyond the inventory host label are exposed.

---

## 2. Prometheus scrape config

In **`prometheus/prometheus.yml`** a dedicated job scrapes the Ansible exporter:

```yaml
- job_name: patch_metrics
  static_configs:
    - targets:
        - ansible:9101
      labels:
        role: patch-orchestration
```

- **Target:** `ansible:9101` (DNS name of the Ansible service on the `monitoring` network).
- **Path:** default `/metrics`.
- **Port 9101** is exposed only inside the Docker network (`expose: - "9101"` in docker-compose); no host publish.

---

## 3. Metrics exporter

**`ansible/metrics_exporter.py`** is a small Python HTTP server that:

- Listens on `0.0.0.0:9101`.
- Serves **GET /metrics** with the contents of `/ansible/reports/patch_metrics.prom`.
- If the file is missing (e.g. before the first patch run), returns minimal valid metrics (zeros) so the scrape does not fail.

Started in the background by the Ansible container entrypoint; no extra dependencies (stdlib only).

---

## 4. Alert rules

In **`prometheus/alert.rules.yml`** the group **`patch_alerts`** defines:

| Alert | Condition | For | Meaning |
|-------|-----------|-----|---------|
| **PatchFailure** | `patch_host_success == 0` | 1m | At least one host failed its last patch run. |
| **PatchDurationTooHigh** | `patch_run_duration_seconds > 120` | 1m | Last patch run took more than 2 minutes. |
| **PatchNotRunRecently** | `(time() - patch_last_run_timestamp) > 86400` | 5m | No patch run in the last 24 hours. |

Alerts use `severity: warning`. Configure Alertmanager and routing in later sprints if needed.

---

## 5. Dashboard panels (Node Overview)

The **Node Overview** dashboard (Sprint 1) was extended with Sprint 3 panels (tag `sprint3`):

- **Patch Run Duration** — Gauge of `patch_run_duration_seconds` (green &lt; 60s, yellow &lt; 120s, red ≥ 120s).
- **Last Patch Timestamp** — Stat showing when the last patch ran (relative time).
- **Patch Success Rate %** — Stat: `sum(patch_host_success) / count(patch_host_success) * 100`.
- **Per-host Patch Success** — Table of `patch_host_success` by host (OK/Fail).

Datasource: existing Prometheus (provisioned in Sprint 1).

---

## 6. Validation procedure

1. **Start stack and run patch**
   ```bash
   docker compose --profile sim up -d
   # wait ~20s for SSH keys
   make patch-health
   make patch
   ```

2. **Check metrics exporter**
   ```bash
   make metrics-test
   ```
   Should output Prometheus-format metrics (including `patch_run_duration_seconds`, `patch_host_success`, etc.).

3. **Prometheus targets**
   - Open **http://localhost:9090/targets**.
   - **patch_metrics** job should be **UP** (target `ansible:9101`).

4. **Prometheus queries**
   - In Prometheus → Graph or Explore, run:
     - `patch_run_duration_seconds`
     - `patch_host_success`
     - `patch_last_run_timestamp`
   - All should show the latest values from the last patch run.

5. **Grafana**
   - Open **http://localhost:3000** → Node Overview.
   - Confirm the four patch panels show data (duration, timestamp, success rate, per-host table).

6. **Failure test (optional)**
   - Stop SSH on one target:  
     `docker compose exec patch-target-1 sudo systemctl stop ssh`  
     (or stop the container).
   - Run **`make patch`** (at least one host will fail).
   - Check that **PatchFailure** fires in Prometheus (Alerts tab) for the failed host, and that the dashboard shows success &lt; 100% and the per-host table shows a failure.

---

## 7. Risk considerations

- **Metrics only on internal network** — Port 9101 is not published to the host; only containers on the `monitoring` network can reach it.
- **No auth on exporter** — Acceptable for an internal Docker network; for production, put the stack behind a reverse proxy with auth or restrict network access further.
- **Stale metrics** — If no patch runs for a long time, `patch_last_run_timestamp` is old; **PatchNotRunRecently** will fire after 24h. Run patches on a schedule or adjust the threshold.
- **Alert routing** — Alertmanager is not configured in Sprint 3; alerts are visible in Prometheus only. Add Alertmanager and routing for production.

---

## 8. Production hardening (recommendations)

- Do not publish the metrics port to the host; keep scrape only from Prometheus on a private network.
- If the Ansible controller is ever exposed, put the metrics endpoint behind a reverse proxy with authentication or IP allowlisting.
- Use Alertmanager for deduplication, routing, and silencing, and document runbooks for PatchFailure, PatchDurationTooHigh, and PatchNotRunRecently.
