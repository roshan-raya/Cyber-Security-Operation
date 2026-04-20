# Onboarding Guide — Patch Management Platform
**Catnip Games International**
For new engineers joining the DevOps team.

---

## What this system does

This system automates security patch deployment across ~300 Linux servers in two
data centres. It replaces manual patching that caused version mismatches and player
disconnections during the beta period.

One command patches all servers, validates compliance, generates a signed report,
and sends alerts if anything goes wrong.

---

## Prerequisites

Install these before starting:

| Tool | Version | Install |
|---|---|---|
| Docker Desktop | Latest | https://docker.com |
| Git | Any | `brew install git` |
| Make | Any | Pre-installed on macOS/Linux |
| Python 3 | 3.9+ | Pre-installed or `brew install python` |

---

## First-time setup (15 minutes)

```bash
# 1. Clone the repository
git clone <repo-url>
cd CSOPROJECT

# 2. Copy environment template
cp .env.example .env
# Edit .env if needed — Grafana password is already set

# 3. Get the vault password from your team lead
# Then set it up:
./scripts/vault-setup.sh

# 4. Start the full simulation stack
docker compose --profile sim up -d
sleep 45

# 5. Verify everything is healthy
make validate
make patch-health
```

You should see all checks passing. If not, see Troubleshooting below.

---

## Your first patch run

```bash
# Preview what will change (no changes applied)
make patch-dryrun

# Run the actual patch
make patch

# Check the results
make validate-reports
make patch-report
```

Open http://localhost:3000 to see the Grafana SLO dashboard update.

---

## Key URLs

| Service | URL | Credentials |
|---|---|---|
| Grafana | http://localhost:3000 | admin / see .env |
| Prometheus | http://localhost:9090 | none |
| Alertmanager | http://localhost:9093 | none |

---

## Most useful make commands

```bash
make patch               # Run patch on all hosts
make patch-dryrun        # Preview without changes
make patch-health        # Check all hosts reachable
make patch-canary-phased # Phased canary → batch → full rollout
make validate            # Check Prometheus + Grafana healthy
make validate-reports    # Check compliance >= 95%
make backup              # Snapshot all volumes
make verify-report       # Check report integrity
make chaos-test          # Run chaos engineering scenarios
make benchmark           # Prove all 5 performance requirements
```

---

## Repository structure

```
ansible/
  playbooks/    patch_orchestrator.yml, patch_canary.yml, health_check.yml
  roles/        common, health_check, patch, reporting, security_scan
  inventory/    hosts.ini (all), staging.ini, production.ini
  vault/        encrypted secrets (see vault/README.md)
prometheus/     prometheus.yml, alert.rules.yml
grafana/        SLO dashboard (patch-slo.json), node overview
alertmanager/   routing config (critical → webhook, warning → console)
scripts/        backup.sh, restore.sh, benchmark.sh, chaos-test.sh
docs/
  adr/          Architecture Decision Records
  evidence/     Proof run artefacts (reports, chaos results)
  *.md          Runbooks, test cases, process workflow
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `make patch` fails — ansible not found | Run `docker compose --profile sim up -d` first |
| Grafana login fails | Check `GF_SECURITY_ADMIN_PASSWORD` in `.env` |
| Prometheus targets showing DOWN | Run `make patch` to generate fresh metrics |
| Backup fails | Check Docker is running: `docker compose ps` |
| `make validate` fails after restart | Wait 30s for containers to become healthy |

---

## Who to ask

- Patch system questions → DevOps team channel
- Vault password → team lead (never share over Slack/email)
- Production patch approval → change management process (see docs/process-workflow.md)
