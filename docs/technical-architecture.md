# Technical Architecture
**Catnip Games International — Automated Patch Management System**

## System Overview

This system automates security patch deployment across approximately 300 Linux servers
spanning two data centres (DC1, DC2). Ansible orchestrates patch operations, Prometheus
and Grafana provide real-time observability, and Docker Compose reproduces the full
environment locally for development and assessment.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      GitHub Actions CI/CD                        │
│    lint ──► build ──► syntax-check ──► patch ──► gate-check     │
└─────────────────────────────┬───────────────────────────────────┘
                              │ triggers on push to main/develop
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Ansible Control Node                          │
│                                                                 │
│  patch_orchestrator.yml                                         │
│    Play 1 — runs on all patch targets in parallel               │
│      ├── Role: common       records start time and defaults     │
│      ├── Role: health_check SSH ping, uptime, sshd active       │
│      ├── Role: patch        apt update → upgrade → reboot       │
│      │     rescue block ──► rollback.yml (if enabled)           │
│      └── (failure flags captured per host)                      │
│                                                                 │
│    Play 2 — runs on localhost only                              │
│      └── Role: reporting    JSON + CSV + .prom metrics files    │
│                                                                 │
│  patch_metrics_exporter.py  serves /metrics on port 9101        │
└──────────┬──────────────────────────────────────────────────────┘
           │ SSH (key-based auth, devops user, sudo for apt)
    ┌──────┴──────────────────────────────────────┐
    ▼                                             ▼
[DC1: patch-target-1, 2, 3]           [DC2: patch-target-4, 5]
Ubuntu containers, SSH + apt          Ubuntu containers, SSH + apt
Dockerfile: ansible/target/           SSH key injected via volume

Metrics pipeline:
  ansible:9101/metrics
       │
       ▼
  Prometheus:9090  ─── evaluates alert.rules.yml every 1 min
       │                       │
       ▼                       ▼
  Grafana:3000          Alertmanager:9093
  node-overview           ├── warning  → console (docker logs)
  dashboard               └── critical → ALERTMANAGER_WEBHOOK_URL

  patch_metrics_exporter also exposes:
    patch_scan_critical_cves  — CVEs remaining post-patch per host
    patch_scan_high_cves      — High CVEs remaining per host
```

## Component Responsibilities

| Component | Technology | Responsibility |
|---|---|---|
| Ansible control node | Ansible 2.x in Docker | Orchestrates all patch operations |
| patch-target-1 to 5 | Ubuntu Docker containers | Simulate production Linux servers |
| Prometheus | prom/prometheus:v2.52.0 | Scrapes metrics, evaluates 7 alert rules |
| Grafana | grafana/grafana:10.4.2 | Visualises compliance, duration, host status |
| Alertmanager | prom/alertmanager:v0.27.0 | Routes alerts by severity to receivers |
| GitHub Actions CI | ubuntu-latest runner | Lint, build, patch, gate-check on every push |
| Node Exporter | prom/node-exporter:v1.8.0 | Host-level system metrics (x2 in sim profile) |
| Security scan role | Trivy (binary) | Post-patch CVE scan; exposes critical/high counts as metrics |
| Ansible Vault | ansible-vault | Encrypts secrets at rest; safe to commit ciphertext to repo |

## Inventory Structure

```
hosts.ini          canary → dc1 (targets 1-3) → dc2 (targets 4-5)
production.ini     blue group (3,4) / green group (5)
staging.ini        staging group (targets 1-2)
dev.ini            dev group (target 1 only)
```

All inventory files share the same SSH user and key path via group_vars/all.yml.

## Performance Requirements

| Requirement | Target | How enforced |
|---|---|---|
| Patch window | ≤ 2 hours | `make validate-reports` and CI gate check duration_seconds ≤ 7200 |
| Concurrent updates | ≥ 5 | `strategy: free` in patch_orchestrator.yml + 5 targets |
| Monitoring refresh | ≤ 5 minutes | `scrape_interval: 5m` global in prometheus.yml |
| Patch success rate | ≥ 95% | CI gate rejects compliance_percentage < 95 |
| System backups | Required | `scripts/backup.sh` creates Docker volume snapshots with SHA256 manifest |

## Security Design

- All containers run as non-root (`nobody`, `grafana` users)
- `read_only: true` on Prometheus and Grafana containers
- SSH keys generated at container startup, stored in Docker volume, never in image
- Sensitive operator secrets stored in Ansible Vault (`ansible/vault/secrets.yml`); `.env` holds Docker-only defaults (gitignored) — never commit live secrets
- Internal services (node-exporter port 9100, metrics-exporter port 9101) bound to
  Docker network only — not published to host
- See `SECURITY.md` for full hardening documentation

## Architecture Decision Records

Structured rationale for major technology choices (Ansible, Docker Compose, Prometheus)
lives in [docs/adr/README.md](adr/README.md). Use these ADRs for design reviews and
assessment Q&A.
