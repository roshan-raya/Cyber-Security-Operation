# Enterprise Automated Patch Management Platform

![CI](https://github.com/YOUR_GITHUB_OWNER/YOUR_REPO/actions/workflows/ci.yml/badge.svg)

Production-ready Dockerised patch orchestration with Ansible, Prometheus, Grafana, and automated rollback. One file: architecture + setup on any laptop.

---

## Architecture

```
                    +------------------+
                    |  GitHub Actions  |
                    |  (push/cron)     |
                    +--------+---------+
                             | docker compose --profile sim up -d; make patch
                             v
+----------------+    +----------------+    +----------------+
|   Prometheus   |<---|    Ansible     |--->| 5 Patch Targets|
|   :9090        |    | (common,       |    | (dev/staging/  |
|   + Alerting   |    |  health_check,  |    |  prod blue/    |
|   -> Alertmgr  |    |  patch, report)|    |  green)        |
+--------+-------+    +--------+-------+    +----------------+
         |                    | metrics :9101
         | scrape              v
         v             +----------------+
+----------------+    | patch_metrics   |
|  Alertmanager  |    | (compliance %,  |
|  :9093         |    |  env, group)    |
+--------+-------+    +----------------+
         |
         v
+----------------+
|    Grafana     |
|  :3000         |
|  Node Overview |
+----------------+
```

- **Prometheus** scrapes itself, node-exporters, patch_metrics, alertmanager (5m interval).
- **Ansible** runs patch orchestration (roles: common → health_check → patch → reporting); writes JSON/CSV and exposes metrics for Prometheus.
- **Alertmanager** receives firing alerts (e.g. PatchComplianceBelow95); can route to Slack/email.
- **Grafana** uses Prometheus; Node Overview shows Compliance %, Patch duration, Failed hosts, CPU/Memory, Blue/Green %.

---

## Project structure

```
/
  docker-compose.yml    # Prometheus, Grafana, Alertmanager, ansible, 5 patch targets (sim profile)
  Makefile              # up, patch, validate, ENV= / LIMIT=
  .env.example          # Copy to .env (Grafana credentials)
  README.md             # This file
  SECURITY.md           # Security notes
  prometheus/           # prometheus.yml, alert.rules.yml
  grafana/provisioning/ # datasources, dashboards (Node Overview)
  alertmanager/         # alertmanager.yml (console + Slack/email)
  ansible/
    playbooks/          # patch_orchestrator.yml, drift_check.yml
    roles/              # common, health_check, patch, reporting
    inventory/          # hosts.ini, dev.ini, staging.ini, prod.ini (blue/green)
  .github/workflows/    # ci.yml (lint, build, patch, validate)
```

---

## Setup on a new laptop

### Prerequisites

- **Docker** and **Docker Compose** (Docker Compose v2)
- **Make** (optional; you can run the underlying `docker compose` / `ansible-playbook` commands manually)
- **Git** (to clone the repo)

### Step 1 — Clone and enter project

```bash
git clone <your-repo-url> CSOPROJECT
cd CSOPROJECT
```

### Step 2 — Environment file

```bash
cp .env.example .env
```

Edit `.env` and set at least:

- `GF_SECURITY_ADMIN_PASSWORD` (Grafana admin password)
- Optionally `GF_SECURITY_ADMIN_USER` (default: `admin`)

### Step 3 — Start the stack

**Monitoring only (Prometheus + Grafana):**

```bash
docker compose up -d
```

**Full stack (monitoring + node exporters + Ansible + 5 patch targets):**

```bash
docker compose --profile sim up -d
```

Or:

```bash
make up-sim
```

Wait until containers are healthy (e.g. 30–60 seconds). Check:

```bash
docker compose ps
```

### Step 4 — Run patch orchestration

With the full stack up:

```bash
make patch
```

This runs the Ansible playbook on all patch targets, generates reports, and updates metrics.

### Step 5 — Validate

```bash
make validate        # Containers, Prometheus ready, Grafana health
make validate-reports   # Reports exist, compliance ≥95%, duration ≤2h, no failed hosts
```

Expect: `[PASS]` and `Validation: PASS`.

### Step 6 — Open UIs

- **Prometheus:** http://localhost:9090 (targets, alerts, query `patch_host_success`, `patch_compliance_percentage`)
- **Grafana:** http://localhost:3000 — login with `.env` credentials → Dashboards → **Node Overview** (use time range “Last 15 minutes” for CPU)

---

## Make commands (reference)

| Command | Description |
|--------|-------------|
| `make up` | Start monitoring only (Prometheus + Grafana) |
| `make up-sim` | Start full stack (sim profile: node exporters + Ansible + 5 patch targets) |
| `make down` | Stop all services |
| `make patch` | Run patch orchestration (default inventory) |
| `make patch ENV=prod` | Patch using `inventory/prod.ini` (ENV=dev, staging, or prod) |
| `make patch ENV=prod LIMIT=blue` | Patch prod Blue group only; then `LIMIT=green` for Green |
| `make patch-staging` | Patch staging only |
| `make patch-blue` / `make patch-green` | Patch blue or green group (production inventory) |
| `make patch-canary` | Patch canary host first, then all |
| `make patch-drift` | Drift detection (packages) |
| `make patch-immutable` | Recreate patch-target-1 then run patch |
| `make patch-report` | Print latest patch report JSON |
| `make patch-health` | Run health_check playbook |
| `make validate` | Check containers, Prometheus, Grafana |
| `make validate-reports` | Check reports, compliance ≥95%, duration ≤2h, no failed hosts |
| `make metrics-test` | Curl patch metrics from exporter |
| `make lint-prometheus` | Lint Prometheus config and rules |
| `make clean` | Down and remove volumes |

---

## Validation checklist (after setup)

Run in order:

```bash
docker compose --profile sim up -d
make patch
make validate-reports
```

Then:

- **Prometheus** http://localhost:9090/targets — prometheus, node-exporter, patch_metrics, alertmanager **UP**
- **Grafana** http://localhost:3000 — Node Overview shows Compliance %, Patch duration, Failed hosts, CPU/Memory

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| Containers not starting | `docker compose logs`; free ports 3000, 9090 |
| Prometheus not ready | `docker compose logs prometheus`; config/alert rules mounted |
| Targets down | Same Docker network; `docker network inspect …_monitoring` |
| Grafana login fails | Credentials in `.env` match (user/password) |
| Dashboard “No data” | Targets UP in Prometheus; wait 1–2 scrape cycles (5m); Grafana time range e.g. “Last 15 minutes” for CPU |
| `make patch` fails | Full stack up (`make up-sim`); ansible container has inventory + roles mounted |
| "removal of container is already in progress" / "service ansible is not running" | Run `docker compose --profile sim down`, wait a few seconds, then `docker compose --profile sim up -d` and retry |

---

## Security

See **SECURITY.md** for least privilege, secrets, networking, and version pinning. Summary: no root SSH on patch targets; metrics internal-only; use TLS and secrets management in production.

---

## CI badge

Replace `YOUR_GITHUB_OWNER` and `YOUR_REPO` in the badge URL at the top with your GitHub org/repo so the badge shows your workflow status.

---

## Licence and ownership

Internal enterprise use. All rights reserved.
