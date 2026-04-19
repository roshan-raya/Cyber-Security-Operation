# Automated Patch Management System
# Catnip Games International - DevOps Team

## Overview
This repository contains an automated patch management platform for Linux infrastructure. Ansible orchestrates patch deployment, while Prometheus, Grafana, and Alertmanager provide monitoring and alerting around patch operations.
Catnip Games manages 300 Linux servers. This system is designed to automate patch rollout with validation gates for compliance and runtime.

## Architecture
```text
GitHub Actions (CI/CD)
     ↓
Ansible Control Node
     ↓
5 Patch Target Servers (dev/staging/prod blue/green)
     ↑
Prometheus ← metrics ← patch_metrics_exporter
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

## Make Commands Table
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

## Recovery Procedures
- **Rollback**:
  `ansible-playbook roles/patch/tasks/rollback.yml`
- **Backup**: create Docker volume snapshots before patch windows
- **Recovery**:
  1. Restore relevant Docker volumes
  2. Start stack with `docker compose --profile sim up -d`
  3. Re-run `make validate` and `make validate-reports`

## Troubleshooting
| Issue | Fix |
|---|---|
| `make patch` fails because `ansible` is unavailable | Start simulation stack with `docker compose --profile sim up -d` |
| Patch report validation fails | Inspect `/ansible/reports/patch_report_latest.json` and rerun patch |
| Grafana has no patch metrics | Check `http://localhost:9090/targets` and verify scrape targets are UP |
| Prometheus rule check fails | Run `make lint-prometheus` and fix rule syntax |
| A patch target host is unreachable | Confirm patch-target containers are running and inventory names match |
