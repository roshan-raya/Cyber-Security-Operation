# Enterprise Automated Patch Management Platform

![CI](https://github.com/YOUR_GITHUB_OWNER/YOUR_REPO/actions/workflows/ci.yml/badge.svg)

Production-ready repository for automated patch management and monitoring of a multiplayer game infrastructure (300+ Linux servers across two data centres). Sprint 1 delivers the **foundation and architecture**: Docker-based monitoring baseline with Prometheus, Grafana, and simulated node exporters.

All work is Infrastructure-as-Code, version controlled, and documented.

**Sprint 1.1** adds hardening: version-pinned images, healthchecks, improved `make validate`, and secure-by-default Grafana settings. **Sprint 2** adds Ansible patch orchestration: an Ansible control container and 5 Docker-based SSH patch targets (Ubuntu, devops user, key-based auth) on the same monitoring network. **Sprint 3** adds monitoring integration: patch metrics exported to Prometheus, alert rules, and Node Overview dashboard panels. **Sprint 4** adds enterprise features: role-based Ansible (common, health_check, patch, reporting), environment separation (staging/production inventories), blue/green production patching, Alertmanager, compliance reporting (latest JSON/CSV, patch_compliance_percentage), GitHub Actions (push/manual/nightly), security hardening (root SSH disabled, StrictModes), and Grafana panels (Compliance %, Failed Hosts, Blue/Green Success %, environment filter). Node-exporter metrics are **container-scoped** (simulated); patch targets are simulated Linux servers for automation testing.

---

## Quick Start

1. **Copy environment file and set Grafana admin password**
   ```bash
   cp .env.example .env
   # Edit .env and set GF_SECURITY_ADMIN_PASSWORD (and optionally GF_SECURITY_ADMIN_USER)
   ```

2. **Start the stack**
   - Monitoring only (Prometheus + Grafana): `docker compose up -d` or `make up`
   - Full stack (monitoring + node exporters + Ansible + 5 patch targets): `docker compose --profile sim up -d` or `make up-sim`

3. **Verify**
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (login with credentials from `.env`)
   - See [Validation](#validation) below for full checks.

---

## Project Structure

```
/project-root
  docker-compose.yml
  Makefile
  .env.example
  .gitignore
  README.md
  SECURITY.md
  /prometheus
    prometheus.yml
    alert.rules.yml
  /grafana
    /provisioning
      /datasources
        datasource.yml
      /dashboards
        dashboards.yml
        node-overview.json
  /ansible
    /playbooks
    /inventory
  /docs
    Sprint1_Architecture.md
    Sprint1_Runbook.md
```

---

## Makefile Commands

| Command   | Description                          |
|----------|--------------------------------------|
| `make up`     | Start monitoring stack only (Prometheus + Grafana) |
| `make up-sim` | Start full stack including simulated node exporters (`--profile sim`) |
| `make down`   | Stop all services                    |
| `make logs`   | Follow container logs                |
| `make status` | Show container status                |
| `make clean`  | Stop and remove containers and volumes |
| `make validate` | Run validation: containers (2, 4, or 11+), Prometheus ready (200), Grafana health (200); outputs PASS/FAIL. |
| `make lint-prometheus` | Lint Prometheus config and rules (requires stack up). |
| `make patch-health` | (Sprint 2) Run Ansible health_check playbook on patch targets. Requires `make up-sim`. |
| `make patch-dryrun` | (Sprint 2) Run patch playbook in check mode. |
| `make patch` | (Sprint 2/4) Run role-based patch orchestration (all targets from default inventory). |
| `make patch-staging` | (Sprint 4) Patch staging only (patch-target-1, 2). |
| `make patch-production` | (Sprint 4) Patch production only (patch-target-3, 4, 5). |
| `make patch-blue` | (Sprint 4) Patch blue group only (patch-target-3, 4). |
| `make patch-green` | (Sprint 4) Patch green group only (patch-target-5). |
| `make patch-report` | (Sprint 2) Print latest patch report JSON (patch_report_latest.json or latest timestamped). |
| `make metrics-test` | (Sprint 3) Curl patch metrics from Ansible exporter. Requires `make up-sim`. |

---

## Validation

Run automated checks and optional manual steps.

### Automated: `make validate`

```bash
docker compose up -d          # or: make up-sim for full stack with sim nodes
make validate
```

**Checks:** (1) Containers running (2 = monitoring only, 4 = sim without Ansible/patch targets, 11+ = full sim, 12+ with Alertmanager), (2) Prometheus ready, (3) Grafana health. Each check prints `[PASS]` or `[FAIL]`. See **Healthchecks** in docs/Sprint1_Runbook.md and **docs/Sprint4_Enterprise.md** for Sprint 4.

### 1. Start and check containers

```bash
docker compose up -d           # monitoring only
docker compose --profile sim up -d   # include simulated node exporters
docker compose ps
```

**Expected:** With `up -d`: two containers (prometheus, grafana). With `--profile sim`: four containers (prometheus, grafana, node-exporter-1, node-exporter-2). Prometheus and Grafana show as `healthy` once their healthchecks pass.

### 2. Prometheus readiness

```bash
curl http://localhost:9090/-/ready
```

**Expected:** HTTP 200, no error.

### 3. Prometheus targets

Open in a browser: **http://localhost:9090/targets**

**Expected:** With monitoring only: 1 target (prometheus). With `--profile sim`: 4 targets, all **UP** — `prometheus`, `node-exporter` (×2), `patch_metrics` (ansible:9101).

### 4. Grafana

- Open **http://localhost:3000**
- Login with:
  - **User:** value of `GF_SECURITY_ADMIN_USER` in `.env` (default `admin`)
  - **Password:** value of `GF_SECURITY_ADMIN_PASSWORD` in `.env` (default `changeme`)

**Expected:** Grafana home loads; no login error.

### 5. Dashboard and metrics

- Go to **Dashboards** (left menu) → open **Node Overview**.
- **Expected:** Dashboard loads and shows:
  - **Targets Up** (stat): values for Prometheus and both node exporters.
  - **CPU Usage %** (time series) for each node.
  - **Memory Usage %** (time series) for each node.
- **Sprint 3:** Patch Run Duration, Last Patch Timestamp, Patch Success Rate %, Per-host Patch Success (after `make patch`). Run `make metrics-test` to verify the metrics exporter.

If panels show “No data”:
- Wait 1–2 scrape cycles (default scrape interval is 5 minutes; see [Troubleshooting](#troubleshooting)).
- Ensure targets are UP in http://localhost:9090/targets (including `patch_metrics` when using sim).

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| **Containers not starting** | `docker compose logs`; ensure ports 3000 and 9090 are free. |
| **Prometheus not ready** | `docker compose logs prometheus`; confirm `prometheus.yml` and `alert.rules.yml` mount correctly. |
| **Targets down** | Same Docker network: `docker network inspect csoproject_monitoring` (or your project name); node exporters must be reachable at `node-exporter-1:9100`, `node-exporter-2:9100`. |
| **Grafana login fails** | Credentials must match `.env` (`GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`). If `.env` is missing, copy from `.env.example`. |
| **Dashboard “No data”** | 1) All 3 targets UP in Prometheus. 2) Default scrape interval is 5m — wait a few minutes or temporarily reduce `scrape_interval` in `prometheus/prometheus.yml` (see comment in file) for testing. 3) In Grafana, check Data source “Prometheus” is working (Explore → run query `up`). |

### Reducing scrape interval for testing

In `prometheus/prometheus.yml`, under the relevant `scrape_configs` job, add for example:

```yaml
scrape_interval: 30s
```

Reload Prometheus config (lifecycle API) or restart the container. Revert to 5m for production alignment.

---

## Version pinning and healthchecks

- **Image versions** are pinned in `docker-compose.yml` (e.g. `prom/prometheus:v2.52.0`, `grafana/grafana:10.4.2`, `prom/node-exporter:v1.8.0`) for **reproducibility** and controlled upgrades. See SECURITY.md for rationale.
- **Healthchecks:** Prometheus uses `http://localhost:9090/-/ready`; Grafana uses `http://localhost:3000/api/health`. Grafana starts only after Prometheus is healthy (`depends_on: prometheus: condition: service_healthy`).

## Security

See **SECURITY.md** for baseline security considerations (least privilege, secrets, networking, firewall, version pinning).

---

## Documentation

- **docs/Sprint1_Architecture.md** — Architecture and design for Sprint 1.
- **docs/Sprint1_Runbook.md** — Operational runbook for monitoring stack.
- **docs/Sprint2_Automation.md** — Ansible patch orchestration, SSH, concurrency, reporting.
- **docs/Sprint2_Testing.md** — Validation steps, example report, failure scenarios.
- **docs/Sprint3_Monitoring.md** — Patch metrics, Prometheus scrape, alert rules, dashboard panels, validation, risks.
- **docs/Sprint4_Enterprise.md** — Role-based Ansible, staging/production, blue/green, Alertmanager, CI/CD, compliance, security.

---

## Licence and ownership

Internal enterprise use. All rights reserved.
