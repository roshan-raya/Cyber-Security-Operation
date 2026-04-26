# CSOPROJECT — Project Document

**Automated Patch Management System**  
**Organisation context:** Catnip Games International — DevOps (Linux fleet ~300 servers, two data centres in the design narrative)

This file is the **single long-form project overview**: what the repository is for, how the pieces fit together, how to run and validate it, and where deeper documentation lives. For day-to-day commands, the root [README.md](../README.md) remains the quick entry point.

---

## 1. Purpose and scope

### What this repository delivers

- **Orchestrated patching** of Linux hosts using **Ansible** (playbooks, roles, inventory for dev, staging, production-style groups).
- **Observability** around patch runs: **Prometheus** scrapes patch and node metrics; **Grafana** dashboards; **Alertmanager** routes alerts by severity.
- A **local “mini production”** via **Docker Compose**: monitoring services always available; with `--profile sim`, an Ansible control node and five SSH-accessible patch targets simulate a small fleet.

### What it is not

- It is not a drop-in replacement for a full enterprise CMDB or ticket system; reporting is file-based (JSON/CSV) plus Prometheus textfile-style metrics.
- Default credentials and demo-only synthetic metrics are for **lab/demo** use; production hardening is described in [SECURITY.md](../SECURITY.md).

---

## 2. High-level architecture

```text
GitHub Actions (CI / scheduled patch / extended validation)
        │
        ▼
Ansible control node (Docker) ──SSH──► patch-target-1 … patch-target-5
        │                                      │
        │ writes reports / .prom               │ apt + sshd (simulated servers)
        ▼
metrics_exporter.py :9101 (Docker network only)
        │
        ▼
Prometheus :9090 ──► alert rules ──► Alertmanager :9093 ──► receivers / webhook
        │
        ▼
Grafana :3000 (dashboards provisioned from repo)
```

**Synthetic demo traffic:** `log-generator` runs `scripts/log_metrics_exporter.py` so Grafana charts look “alive” during demos. This is separate from patch metrics.

---

## 3. Repository layout

| Path | Role |
|------|------|
| `ansible/` | Ansible config, playbooks, roles, inventory, vault area, `metrics_exporter.py`, control-node and target Docker build contexts |
| `ansible/playbooks/` | `patch_orchestrator.yml`, `health_check.yml`, `drift_check.yml`, `rollback.yml`, `patch_dryrun.yml`, `patch_canary.yml`, etc. |
| `ansible/roles/` | `common`, `health_check`, `patch`, `reporting`, `security_scan` |
| `ansible/inventory/` | `hosts.ini`, `dev.ini`, `staging.ini`, `production.ini`, `group_vars/all.yml` |
| `prometheus/` | `prometheus.yml`, `alert.rules.yml` |
| `grafana/provisioning/` | Datasources and dashboards (JSON + `dashboards.yml`) |
| `alertmanager/` | `alertmanager.yml` |
| `scripts/` | `backup.sh`, `restore.sh`, `chaos-test.sh`, `benchmark.sh`, `verify-report.sh`, `vault-setup.sh`, `log_metrics_exporter.py` |
| `docs/` | Architecture, runbooks, test cases, ADRs, evidence, this document |
| `.github/workflows/` | `ci.yml`, `patch.yml`, `extended-validation.yml` |
| `docker-compose.yml` | Service topology, profiles, volumes, healthchecks |
| `Makefile` | Canonical shortcuts for compose, patch, validate, chaos, benchmark |

---

## 4. Technology stack (pinned images)

From `docker-compose.yml` (representative):

| Component | Image / runtime |
|-----------|------------------|
| Prometheus | `prom/prometheus:v2.52.0` |
| Alertmanager | `prom/alertmanager:v0.27.0` |
| Grafana | `grafana/grafana:10.4.2` |
| Node exporter (sim) | `prom/node-exporter:v1.8.0` |
| Ansible / targets | Built from `ansible/Dockerfile` and `ansible/target/Dockerfile` |
| Log generator | `python:3.12-slim-bookworm` |

CI installs **ansible-lint** on the runner and runs playbooks inside the **ansible** container.

---

## 5. Core workflows

### 5.1 Local development and demo

1. Install **Docker**, **Docker Compose**, **Make**, **Git**.
2. `cp .env.example .env` and adjust if needed (Grafana admin, optional `ALERTMANAGER_WEBHOOK_URL`).
3. **Monitoring only:** `docker compose up -d` or `make up`.
4. **Full simulation:** `docker compose --profile sim up -d` or `make up-sim`.
5. Run patching: `make patch`.
6. Validate: `make validate`, `make validate-reports`.

**URLs:** Prometheus `http://localhost:9090`, Grafana `http://localhost:3000`, Alertmanager `http://localhost:9093`.

### 5.2 Patch orchestration (conceptual)

- **Play 1 (targets):** `common` → `health_check` → `patch` (apt update/upgrade, optional reboot); failures can feed rollback behaviour when enabled.
- **Play 2 (localhost):** `reporting` builds compliance/duration/host status and writes `patch_report_latest.json`, CSV, and `patch_metrics.prom` on the shared volume; the exporter serves derived metrics to Prometheus.

### 5.3 Inventory and environments

| File | Intent |
|------|--------|
| `hosts.ini` | Combined lab layout (canary + DC-style groups) |
| `dev.ini` | Single-host dev |
| `staging.ini` | Staging slice |
| `production.ini` | Blue/green style groups |

SSH user, key paths, and shared variables live in `ansible/inventory/group_vars/all.yml`.

**Makefile targeting:** `make patch` accepts optional `ENV=` and `LIMIT=` to select inventory and Ansible `--limit` (see comments in the `Makefile` `patch` target).

---

## 6. Make targets (operator reference)

Grouped for readability; authoritative definitions are in the [Makefile](../Makefile).

**Compose lifecycle**

| Target | Description |
|--------|-------------|
| `up` | Start prometheus, grafana, alertmanager |
| `up-sim` | Start full sim profile (ansible + targets + node exporters, etc.) |
| `down` | `docker compose down` |
| `logs` | Follow logs |
| `status` | `docker compose ps` |
| `clean` | Down with volumes |

**Patching and Ansible**

| Target | Description |
|--------|-------------|
| `patch` | Main orchestrator against default or `ENV` / `LIMIT` |
| `rollback` | Run `playbooks/rollback.yml` |
| `patch-dryrun` | Dry-run playbook |
| `patch-health` | Health check playbook |
| `patch-staging` / `patch-production` | Environment-specific orchestrator |
| `patch-blue` / `patch-green` | Production inventory, limited groups |
| `patch-canary` | Canary then full fleet on `hosts.ini` |
| `patch-canary-phased` | Phased canary playbook (`patch_canary.yml`) |
| `patch-immutable` | Recreate one target then patch |
| `patch-drift` | Drift check playbook |

**Quality gates and observability**

| Target | Description |
|--------|-------------|
| `lint-prometheus` | `promtool` check config + rules |
| `validate` | Ready checks for Prometheus and Grafana |
| `validate-reports` | JSON/CSV/.prom exist; compliance ≥ 95%; duration ≤ 2h; no failed hosts |
| `validate-patch-fleet` | At least five hosts in latest report (concurrency SLA) |
| `patch-report` | Print latest JSON report |
| `metrics-test` | Curl patch metrics exporter inside ansible container |
| `verify-report` | `scripts/verify-report.sh` |

**Backup / restore**

| Target | Description |
|--------|-------------|
| `backup` | `scripts/backup.sh` (optional `LABEL=`) |
| `restore` | `scripts/restore.sh` with `BACKUP_DIR=backups/...` |
| `patch-with-backup` | Backup then patch |

**Resilience and performance evidence**

| Target | Description |
|--------|-------------|
| `chaos-test` | All chaos scenarios (`SCENARIO=` optional) |
| `chaos-test-1` … `chaos-test-3` | Individual scenarios |
| `benchmark` | `scripts/benchmark.sh` — performance requirement checks |

---

## 7. Performance and SLO-style requirements

| Requirement | Target | Enforcement |
|-------------|--------|-------------|
| Patch window | ≤ 2 hours | `validate-reports` / CI on `duration_seconds` |
| Concurrent updates | ≥ 5 hosts | Five targets; `validate-patch-fleet` in CI |
| Monitoring refresh | ≤ 5 minutes | Prometheus scrape configuration |
| Patch success / compliance | ≥ 95% | Report JSON `compliance_percentage` |
| Backups | Required for process | `scripts/backup.sh`, documented runbook |

---

## 8. CI/CD

### 8.1 `ci.yml` — “CI - Patch Management”

**Triggers:** push to `main`, `master`, `develop`; all pull requests.

**Flow:** Checkout → Python + `ansible-lint` → `docker compose --profile sim build --no-cache` → stack up → Ansible `--syntax-check` on orchestrator and rollback playbooks → `make patch` → report gates (compliance, duration, failed hosts) → `make validate-patch-fleet` → teardown (`docker compose --profile sim down -v`).

### 8.2 `patch.yml` — “Patch Orchestration”

**Triggers:** push to `main`, `workflow_dispatch`, nightly cron (`0 2 * * *`).

Runs the stack, `make patch`, and post-patch validation (fleet size and report gates). Use for scheduled or on-demand patch demonstration in CI.

### 8.3 `extended-validation.yml`

**Triggers:** `workflow_dispatch`; weekly Monday 03:15 UTC cron.

Runs **`make benchmark`** and **`make chaos-test`**, uploads evidence artifacts. Intended as a heavier regression path than per-PR CI.

---

## 9. Monitoring and alerting

- **Scrape targets** are defined in `prometheus/prometheus.yml` (Prometheus, node exporters, patch metrics, log generator, etc.).
- **Alert rules** live in `prometheus/alert.rules.yml` (compliance, failures, duration, staleness, etc.; see README for named alerts).
- **Alertmanager** routing is in `alertmanager/alertmanager.yml`; optional external webhook via `.env` (`ALERTMANAGER_WEBHOOK_URL`).

---

## 10. Security (summary)

- Non-root users and read-only roots where configured; dedicated Docker network; limited host port exposure (Prometheus, Grafana, Alertmanager).
- Secrets: `.env` gitignored; Ansible Vault under `ansible/vault/` for operator patterns; SSH keys generated in-container and stored in a volume — not committed.
- Full discussion: [SECURITY.md](../SECURITY.md).

---

## 11. Operations, recovery, and testing

| Topic | Document |
|-------|----------|
| Recovery and rollback steps | [recovery-runbook.md](recovery-runbook.md) |
| End-to-end patch lifecycle (CI + manual) | [process-workflow.md](process-workflow.md) |
| Component-level design | [technical-architecture.md](technical-architecture.md) |
| Formal test cases (TC-001 …) | [test-cases.md](test-cases.md) |
| Chaos scenarios | [chaos-testing.md](chaos-testing.md) |
| Demo / screencast scripts | [demo-script.md](demo-script.md), [screencast-script.md](screencast-script.md) |
| New engineer setup | [onboarding.md](onboarding.md) |
| Security review checklist | [security-review-checklist.md](security-review-checklist.md) |
| Architecture decisions | [adr/README.md](adr/README.md) (ADR-001 Ansible, ADR-002 Compose, ADR-003 Prometheus) |

**Evidence and reports:** Under `docs/evidence/` (performance, chaos logs, Alertmanager proofs, etc.). Chaos summary: `docs/evidence/chaos/chaos_summary.log`.

---

## 12. Ansible roles (short descriptions)

| Role | Responsibility |
|------|------------------|
| `common` | Baseline facts and patch window bookkeeping |
| `health_check` | Connectivity and basic service health |
| `patch` | Package update path, reboot handling, rollback hooks |
| `reporting` | Aggregated JSON/CSV and `.prom` for metrics |
| `security_scan` | Post-patch scanning (e.g. Trivy) and exposure of CVE-ish metrics where implemented |

---

## 13. Troubleshooting (quick)

| Symptom | Likely fix |
|---------|------------|
| `make patch` fails: no ansible | Bring up sim profile: `make up-sim` |
| Report validation fails | Inspect report in container path `/ansible/reports/`; re-run `make patch` |
| Grafana empty for patch metrics | Check Prometheus targets UP; confirm exporter on `monitoring` network |
| Rule check fails | `make lint-prometheus` and fix YAML/rule syntax |
| SSH unreachable to targets | Ensure five `patch-target-*` containers are up and inventory names match |

---

## 14. Version control and hooks

- **Commit message hook:** `.githooks/commit-msg` (install per your Git hooks policy).
- **Lint:** `.ansible-lint` for Ansible style and rules.

---

## 15. Document maintenance

When you add a playbook, workflow, or major behaviour change:

1. Update the root [README.md](../README.md) if operator commands or URLs change.
2. Update this **PROJECT.md** if architecture, CI layout, or performance gates change.
3. Add or adjust ADRs for non-obvious technology choices.

---

*Last consolidated as a full-project document for the CSOPROJECT repository (Automated Patch Management System).*
