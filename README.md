# Enterprise Automated Patch Management Platform

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

## TheHive SOC Platform

TheHive 5 is the case management backbone of the SOC platform, handling alert triage, incident tracking, and response workflows.

### Quick start

```bash
make thehive-setup       # Deploy and fully configure TheHive
make thehive-status      # Check TheHive is running
```

Open http://localhost:9000

> Note: TheHive Community Edition does not expose **create** case templates via REST API (`manageCaseTemplate` on POST). Create templates in the UI first, then run **`make thehive-canonicalize-templates`** so their **Name** fields match the canonical ids (`BOT_ATTACK`, …). **`make thehive-templates`** then checks those names **and** the task lists defined in `thehive/config/case_templates.json`.

### Default passwords (development)

After `cp .env.example .env`, Grafana, TheHive org admin, MISP admin, and the seeded TheHive analyst/read-only users use the same development default unless you override them in `.env`:

| Variable / account | Default (from `.env.example`) |
|--------------------|-------------------------------|
| `GF_SECURITY_ADMIN_PASSWORD` | `Nepsoft@123!` |
| `THEHIVE_ADMIN_PASSWORD` | `Nepsoft@321!` |
| `MISP_ADMIN_PASSWORD` | `Nepsoft@321!` |
| TheHive bootstrap `admin@thehive.local` | `secret` (fixed by the container image; see `.env` comments) |

**MISP:** passwords must meet the server policy (typically **at least 12 characters**). Shorter values such as `Nepsoft@123` are rejected; use **`Nepsoft@321!`** (or another 12+ character value) and keep **`.env` in sync with the MISP UI**. Run **`make misp-init`** after changing `MISP_ADMIN_PASSWORD` so the cake CLI can sync the DB password with `.env`.

**Production:** replace all of these with strong, unique secrets (see `SECURITY.md`).

### Default user accounts

| Role | Email | Password | Purpose |
|------|-------|----------|---------|
| Org admin | soc.admin@catnipgames.com | `Nepsoft@321!` (or `.env` `THEHIVE_ADMIN_PASSWORD`) | Organisation admin: users, case templates, cases |
| Analyst | soc.analyst@catnipgames.com | Same as `THEHIVE_ADMIN_PASSWORD` on first `thehive-init` | Case management |
| Read-only | soc.readonly@catnipgames.com | Same as `THEHIVE_ADMIN_PASSWORD` on first `thehive-init` | Monitoring only |

### Case templates

| Template | Severity |
|----------|----------|
| BOT_ATTACK (Bot Attack / Game Exploit) | Medium (2) |
| ACCOUNT_COMPROMISE (Account Compromise / Credential Stuffing) | High (3) |
| SOCIAL_ENGINEERING (Social Engineering / Phishing) | High (3) |
| DDOS_INFRASTRUCTURE (DDoS / Infrastructure Attack) | High (3) |

### Custom fields

| Field | What it captures |
|-------|------------------|
| player-id | Affected player account identifier |
| affected-server | Hostname or IP of the affected game server |
| matchmaking-service | Matchmaking service instance involved |
| incident-category | SOC incident classification |

### TheHive Make targets

| Command | Description |
|---------|-------------|
| `make thehive-up` | Start Cassandra + TheHive |
| `make thehive-init` | Organisation, users (org-admin SOC admin), custom fields, write `thehive/setup/api_key.txt` |
| `make thehive-init-force` | Same as init with `--force` (continues past some organisation HTTP 400 responses after volume wipes) |
| `make thehive-rekey` | Renew **only** the SOC admin API key (`--rekey-only`) using default `admin@thehive.local` |
| `make thehive-canonicalize-templates` | PATCH template **Name** / **Display name** to match `thehive/config/case_templates.json` |
| `make thehive-templates` | Verify canonical names **and** expected tasks vs `case_templates.json` |
| `make thehive-status` | Quick reachability check |
| `make thehive-logs` | Follow TheHive + Cassandra logs |

### Troubleshooting

| Issue | What to check |
|-------|----------------|
| TheHive not starting | `docker compose logs thehive`; Cassandra must be healthy first |
| Login fails | Run: `make thehive-init` to re-initialise users |
| Templates missing or wrong name | Create rough templates in UI, then `make thehive-canonicalize-templates`, then `make thehive-templates` |
| API key invalid / Cassandra rebuilt | Run: `make thehive-rekey` (or `make thehive-init-force` for a full pass) |
| Cassandra not ready | Wait 60-90s after startup; check: `docker compose logs cassandra` |

---

## MISP Threat Intelligence Platform

MISP is the threat intelligence backbone of the SOC platform. It shares IOCs between analysts, integrates with TheHive for observable enrichment, and connects to external threat feeds relevant to gaming infrastructure threats.

### Quick start

```bash
make misp-setup               # Deploy and configure MISP
make misp-status              # Check MISP is running
make misp-reset-login-lockout # Clear "maximum login attempts" / brute-force lockout (MySQL)
make misp-integration-test    # Test TheHive-MISP round trip
```

Open http://localhost:8080

### Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@catnipgames.com | `Nepsoft@321!` (or `.env` `MISP_ADMIN_PASSWORD`) |

### Enabled feeds (target list)

| Feed | Purpose |
|------|---------|
| CIRCL OSINT | General threat intel |
| Abuse.ch URLhaus | Malicious URLs |
| Abuse.ch Feodo Tracker | Botnet C2 IPs (relevant: bot attacks) |
| Abuse.ch SSL Blacklist | Malicious SSL certs |
| The Botvrij.eu Data | Threat actor IOCs |
| blocklist.de | Known attack sources |

### Integration

TheHive connects to MISP for observable enrichment. When an analyst adds an IP, domain, or hash to a TheHive case, Cortex (Sprint 3) will automatically query MISP for matches. Confirmed IOCs are exported back to MISP via `misp_exporter.py` (Sprint 3).

### Troubleshooting

| Issue | What to check |
|-------|----------------|
| MISP not starting | `docker compose logs misp`; `misp-db` must be healthy first |
| "Maximum number of login attempts" (300s lockout) | Run **`make misp-reset-login-lockout`** (empties the `bruteforces` table), wait a few seconds, then try again |
| Login fails | Check `MISP_ADMIN_EMAIL` and `MISP_ADMIN_PASSWORD` in `.env` (min ~12 chars for MISP); run **`make misp-init`** to sync the DB password with `.env` |
| Feeds not syncing | Run: `make misp-feeds` |
| TheHive integration failing | Run: `make misp-integration-test` for details |
| misp-db unhealthy | Wait 60-90s; check: `docker compose logs misp-db` |

---

## Cortex Automated Analysis

Cortex automates observable enrichment. When an analyst adds an IP, domain, or hash to a TheHive case, Cortex runs analysers and reports findings back on the case timeline (via the TheHive–Cortex connector).

### Quick start

```bash
make cortex-setup          # Deploy and configure Cortex
make cortex-status         # Check Cortex is running
make ingest-alerts         # Ingest 10 simulated game security alerts
make enrich-alerts         # Auto-enrich all open case observables
make kpi-report            # Generate SOC KPI report
```

### Credentials

| Item | Value |
|------|--------|
| URL | http://localhost:9001 |
| Admin | `admin` / `Nepsoft@123` (or `.env` `CORTEX_ADMIN_PASSWORD`) |

### Analysers

| Analyser | Purpose | Requires |
|----------|---------|----------|
| AbuseIPDB | IP reputation | `ABUSEIPDB_API_KEY` |
| MaxMind GeoIP | IP geolocation | Free (local DB path in container) |
| VirusTotal | File/URL/domain reputation | `VT_API_KEY` |
| Shodan | IP infrastructure intel | `SHODAN_API_KEY` |
| MISP_2_1 | Local MISP lookup | `MISP_THEHIVE_API_KEY` |

### Automation scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `alert_ingestor.py` | `make ingest-alerts` | Creates 10 TheHive cases from mock alerts |
| `alert_enricher.py` | `make enrich-alerts` | Triggers Cortex on open-case observables |
| `misp_exporter.py` | `make export-iocs` | Exports resolved case IOCs to MISP |
| `kpi_tracker.py` | `make kpi-report` | SOC KPI report + Prometheus textfile metrics |

Free API keys for AbuseIPDB, VirusTotal, and Shodan are available at [abuseipdb.com](https://www.abuseipdb.com), [virustotal.com](https://www.virustotal.com), and [shodan.io](https://www.shodan.io). Add them to `.env` for full analyser behaviour; the setup scripts use `demo_key` when a variable is unset (limited or placeholder behaviour).

### Troubleshooting

| Issue | What to check |
|-------|----------------|
| Cortex not starting | `docker compose logs cortex`; `cortex-db` must pass its healthcheck |
| No analysers found | Cortex CE ships a limited set; `[NOT FOUND]` from `make cortex-analysers` is normal |
| TheHive connection failing | Run `make cortex-connect-thehive` |
| Jobs not completing | Confirm `/var/run/docker.sock` is mounted on `cortex`; inspect `docker compose logs cortex` |

---

## Project structure

```
/
  docker-compose.yml    # Monitoring, Ansible sim, TheHive, MISP, Cortex + ES
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
  cortex/
    setup/              # init_cortex, configure_analysers, connect_thehive, verify_cortex
    automation/         # alert_ingestor, alert_enricher, misp_exporter, kpi_tracker
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

- `GF_SECURITY_ADMIN_PASSWORD` (Grafana admin password; `Nepsoft@123!` in `.env.example` for local dev only)
- `THEHIVE_ADMIN_PASSWORD` and `MISP_ADMIN_PASSWORD` if you use TheHive/MISP (see `.env.example`; **quote** `THEHIVE_ORG_DESCRIPTION` if it contains spaces)
- Optionally `GF_SECURITY_ADMIN_USER` (default: `admin`)

For a quick start you can keep the `.env.example` values, then **change every password** before any shared or production use.

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

## Licence and ownership

Internal enterprise use. All rights reserved.
