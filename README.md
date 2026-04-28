# Automated Patch Management System
**Catnip Games International - DevOps Team**

## Overview
This repository implements automated Linux patch operations with:
- Ansible patch orchestration and reporting
- Prometheus/Grafana/Alertmanager monitoring and alerting
- rollback, backup, and recovery procedures
- CI workflows that enforce report gates

The coursework scenario references a 300-server estate. This repo is the as-built
simulation environment (5 patch targets) used for development, testing, and assessment.

## Architecture
```text
GitHub Actions (CI/CD)
     ↓
Ansible Control Node
     ↓
5 Patch Target Servers (dev/staging/prod blue/green)
     ↑
Prometheus ← metrics ← patch_metrics_exporter + log-generator (synthetic varying rates for demos)
     ↓
Grafana (Node Overview Dashboard)
     ↓
Alertmanager (alerts)
```

## Project Structure
```text
ansible/
  playbooks/     # patch_orchestrator, health_check, drift_check
  roles/         # common, health_check, patch, reporting
  inventory/     # hosts.ini, dev.ini, staging.ini, prod.ini
prometheus/      # prometheus.yml, alert.rules.yml
grafana/         # provisioning/dashboards/node-overview.json
alertmanager/    # alertmanager.yml
docker-compose.yml
Makefile
```

## Setup
1. **Prerequisites**: Docker, Docker Compose, Make, Git
2. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd CSOPROJECT
   ```
3. **Copy environment template**
   ```bash
   cp .env.example .env
   ```
4. **Start monitoring only**
   ```bash
   docker compose up -d
   ```
5. **Start full patch simulation**
   ```bash
   docker compose --profile sim up -d
   ```
6. **Run patch orchestration**
   ```bash
   make patch
   ```
7. **Validate platform and reports**
   ```bash
   make validate
   make validate-reports
   ```
8. **Open dashboards**
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000

## Make Commands
| Command | Description |
|---|---|
| `make up` | Start monitoring services |
| `make up-sim` | Start full simulation stack |
| `make down` | Stop all services |
| `make logs` | Stream service logs |
| `make status` | Show container status |
| `make clean` | Stop services and remove volumes |
| `make lint-prometheus` | Validate Prometheus config and rules |
| `make validate` | Validate Prometheus and Grafana health |
| `make validate-reports` | Validate patch report gates |
| `make patch` | Execute patch orchestration |
| `make patch-dryrun` | Run dry-run patch playbook |
| `make patch-health` | Run health-check playbook |
| `make patch-staging` | Patch staging inventory |
| `make patch-production` | Patch production inventory |
| `make patch-blue` | Patch blue production group |
| `make patch-green` | Patch green production group |
| `make patch-canary` | Canary patch then full rollout |
| `make patch-immutable` | Recreate one target and patch |
| `make patch-drift` | Run drift-check playbook |
| `make patch-report` | Print latest patch report |
| `make metrics-test` | Verify metrics exporter endpoint |
| `make backup` | Create pre-patch volume snapshot (use LABEL=name to tag it) |
| `make restore` | Restore from backup snapshot (requires BACKUP_DIR=backups/path) |
| `make patch-with-backup` | Run backup then patch in a single command |
| `make chaos-test` | Run all chaos engineering scenarios |
| `make benchmark` | Run benchmark workflow and generate performance evidence |

## Documentation

| Document | Purpose |
|---|---|
| [docs/technical-architecture.md](docs/technical-architecture.md) | System architecture, components, design decisions |
| [docs/recovery-runbook.md](docs/recovery-runbook.md) | Step-by-step operator recovery procedures |
| [docs/process-workflow.md](docs/process-workflow.md) | Full patch lifecycle — CI and manual paths |
| [docs/test-cases.md](docs/test-cases.md) | TC-001 through TC-017 with commands and pass criteria |
| [docs/chaos-testing.md](docs/chaos-testing.md) | Chaos engineering scenarios and recovery proof |
| [docs/adr/ADR-001.md](docs/adr/ADR-001.md) | Why Ansible for orchestration |
| [docs/adr/ADR-002.md](docs/adr/ADR-002.md) | Why Docker Compose for test environment |
| [docs/adr/ADR-003.md](docs/adr/ADR-003.md) | Why Prometheus over hosted monitoring |
| [docs/security-review-checklist.md](docs/security-review-checklist.md) | Hardening review checklist and formal sign-off (weeks 9–10) |

Pull requests run [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Extended validation
([`.github/workflows/extended-validation.yml`](.github/workflows/extended-validation.yml))
runs `make benchmark` and `make chaos-test` weekly and on manual dispatch, then uploads
evidence as workflow artifacts.

## Validation Checklist
Run in order:
```bash
docker compose --profile sim up -d
make patch
make validate-reports
```

Then confirm:
- Prometheus targets page (`http://localhost:9090/targets`) shows all patch targets UP
- Grafana (`http://localhost:3000`) loads the Node Overview dashboard

## Performance Requirements
| Requirement | Target | Implementation |
|---|---|---|
| Patch window | <= 2 hours | Enforced in CI validation |
| Concurrent updates | >= 5 | 5 patch targets in parallel |
| Monitoring refresh | <= 5 minutes | Prometheus scrape interval |
| Patch success rate | >= 95% | CI gate rejects <95% |
| System backups | Required | Docker volume snapshots |

## Ansible Roles
- **common** - baseline system configuration
- **health_check** - SSH, uptime, and service checks
- **patch** - apt update, upgrade, and reboot logic
- **reporting** - JSON/CSV report generation and Prometheus metrics output

## Monitoring and Alerts
- `PatchComplianceBelow95` - fires when compliance drops below 95%
- `PatchFailure` - fires when a host patch run fails
- `PatchDurationTooHigh` - fires when patch duration exceeds threshold
- `PatchNotRunRecently` - fires when no run is detected in 24 hours

> **Demo tip:** To see critical alerts arrive in real time, create a free endpoint at
> https://webhook.site, copy the UUID, and set `ALERTMANAGER_WEBHOOK_URL=https://webhook.site/YOUR-UUID`
> in `.env`. Restart alertmanager with `docker compose restart alertmanager`.
> Critical alerts (PatchFailureCritical, PatchHostUnreachable) will POST there within 5 seconds.

## Recovery Procedures
Step-by-step operator runbook: [docs/recovery-runbook.md](docs/recovery-runbook.md)

Quick reference:

| Action | Command |
|---|---|
| Pre-patch backup | `make backup LABEL=pre-patch` |
| Restore from backup | `make restore BACKUP_DIR=backups/<timestamp>` |
| Rollback a single host | `docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml --limit <host> -e rollback_enabled=true` |
| Restart full stack | `docker compose --profile sim up -d && make validate` |
| Check patch report | `make patch-report` |

For backup + patch in one command: `make patch-with-backup`

## Troubleshooting
| Issue | Fix |
|---|---|
| `make patch` fails because `ansible` is unavailable | Start simulation stack with `docker compose --profile sim up -d` |
| Patch report validation fails | Inspect `/ansible/reports/patch_report_latest.json` and rerun patch |
| Grafana has no patch metrics | Check `http://localhost:9090/targets` and verify scrape targets are UP |
| Prometheus rule check fails | Run `make lint-prometheus` and fix rule syntax |
| A patch target host is unreachable | Confirm patch-target containers are running and inventory names match |
