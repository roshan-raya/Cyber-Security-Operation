# Technical Architecture
**Catnip Games International — Automated Patch Management System (as built)**

## 1. Scope and reality check

This document describes what is really implemented in this repository.
The assignment scenario talks about a 300-server, two-datacentre environment. In this project
I model that with Docker Compose: one Ansible control node and five Linux patch targets.

The objective here is not full production parity. The objective is a reproducible setup that proves:
- automated patch orchestration
- monitoring and alerting
- rollback and recovery flows
- CI validation gates

This write-up is implementation-first. It reflects what is running now in this repo,
not a future target design.

## 2. High-level architecture

```text
GitHub (push/PR/schedule)
        |
        v
GitHub Actions workflows
  - ci.yml
  - patch.yml
  - extended-validation.yml
        |
        v
Docker Compose (--profile sim)
  +-------------------------------------+
  | Ansible control node                |
  | - playbooks + roles + inventory     |
  | - metrics_exporter.py (:9101)       |
  +-------------------------------------+
        | SSH
        v
  patch-target-1 ... patch-target-5

Ansible writes:
  /ansible/reports/*.json, *.csv, *.prom
        |
        v
Prometheus (:9090) -> Grafana (:3000)
        |
        v
Alertmanager (:9093)
```

## 3. Patch execution flow

Main playbook: `ansible/playbooks/patch_orchestrator.yml`

- **Play 1 (hosts: all, strategy: free)**
  - `common`
  - `health_check`
  - `patch`
  - `security_scan`
- **Play 2 (hosts: localhost)**
  - `reporting`

Patch role behaviour in `ansible/roles/patch/tasks/main.yml`:
- capture pre-patch package snapshot
- `apt update_cache`
- `apt upgrade: safe`
- detect reboot requirement and reboot when needed
- `rescue` path can include `rollback.yml` when `rollback_enabled=true`

## 4. Runtime components

| Component | Implementation | Notes |
|---|---|---|
| Orchestration | Ansible container (`ansible/`) | Executes playbooks against simulated targets |
| Patch targets | `patch-target-1..5` | Built from `ansible/target/Dockerfile` |
| Monitoring | Prometheus | Scrapes exporters and evaluates `prometheus/alert.rules.yml` |
| Dashboards | Grafana | Provisioned from `grafana/provisioning/` |
| Alert routing | Alertmanager | Config in `alertmanager/alertmanager.yml` |
| Host metrics (sim) | node-exporter-1, node-exporter-2 | Enabled under `--profile sim` |
| Patch metrics | `ansible/metrics_exporter.py` + reporting role | Serves metrics from report outputs on port 9101 |
| CI validation | GitHub Actions | Runs lint/build/patch/gates in workflows |

## 5. Inventory model

Implemented inventory files:
- `ansible/inventory/hosts.ini`
- `ansible/inventory/dev.ini`
- `ansible/inventory/staging.ini`
- `ansible/inventory/production.ini`

Examples of grouping used by current files:
- canary, dc1, dc2
- blue, green
- patch_targets

Shared target connection vars are defined in `ansible/inventory/group_vars/all.yml`.

## 6. CI/CD architecture

### `ci.yml` (PR and branch validation)
- ansible-lint
- build sim images
- bring stack up
- syntax-check playbooks
- run `make patch`
- enforce report gates:
  - compliance >= 95
  - duration <= 7200 seconds
  - failed hosts == 0
- validate minimum patch fleet size

### `patch.yml` (operational patch workflow)
- trigger: push to `main`, scheduled cron, manual dispatch
- run patch + report validation
- optional rollback on patch failure

### `extended-validation.yml` (regression and resilience)
- run benchmark and chaos tests
- upload evidence artifacts

## 7. Security and resilience controls (implemented)

- Prometheus and Grafana run as non-root users with read-only rootfs in Compose.
- Ansible SSH key is generated inside the container runtime and persisted via volume.
- Secrets workflow exists via `ansible/vault/` and `.env` template usage.
- Alertmanager supports multi-channel routing by severity:
  - warning -> Slack
  - critical -> webhook + Slack + PagerDuty
- Tracked Alertmanager config uses placeholders and is rendered at container startup from `.env`,
  so real webhook/routing keys are not stored directly in `alertmanager/alertmanager.yml`.
- Rollback and recovery are implemented:
  - `ansible/playbooks/rollback.yml`
  - `ansible/roles/patch/tasks/rollback.yml`
  - `docs/recovery-runbook.md`
  - `scripts/backup.sh` and `scripts/restore.sh`

For full hardening posture and operational guidance, see `SECURITY.md`.

## 8. Monitoring and alerting implementation notes (what I validated)

- I validated warning delivery to Slack using `PatchNotRunRecently`.
- I validated critical delivery using `PatchHostUnreachable` and `PatchComplianceMetricMissing`.
- Critical alert fanout is active to webhook + Slack + PagerDuty.
- Tracked Alertmanager config keeps placeholders; runtime values are injected from `.env` at startup.

## 9. Known limitations

- This is a simulation environment, not a direct production deployment to 300 servers.
- Alertmanager routing and thresholds are tuned for coursework/demo validation. In a real production
  setup, escalation ownership, maintenance silence policy, and key rotation need stricter governance.
- Some evidence/report files are generated during workflow runs and may be missing locally until
  the related scripts are executed.

## 10. Related design decisions

Architecture decisions are documented in:
- `docs/adr/ADR-001.md` (Ansible)
- `docs/adr/ADR-002.md` (Docker Compose simulation)
- `docs/adr/ADR-003.md` (Prometheus/Grafana stack)
