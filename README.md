# Enterprise Automated Patch Management Platform

![CI](https://github.com/roshan-raya/Cyber-Security-Operation/actions/workflows/ci.yml/badge.svg)
![Nightly](https://github.com/roshan-raya/Cyber-Security-Operation/actions/workflows/nightly.yml/badge.svg)
![Security](https://github.com/roshan-raya/Cyber-Security-Operation/actions/workflows/security.yml/badge.svg)

## CI/CD Pipeline

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| CI | Every push + PR | Code quality, syntax, integration tests |
| Nightly | 2am daily | Full stack validation, KPI report |
| Security | Weekly + PR | SAST, secret scan, container scan |
| PR Checks | Every PR | Fast quality gates, required files |
| Release | On git tag | Validate, package, publish release |

### Running locally

All CI checks can be run locally before pushing:

```bash
make validate
make thehive-templates
make misp-verify
make cortex-verify
python3 cortex/automation/alert_ingestor.py --dry-run
python3 cortex/automation/kpi_tracker.py --output human
python3 cortex/automation/escalation_manager.py --dry-run
```

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

**Template name drift:** If a template was saved with a typo in the machine name (for example **`DDOS_INFRASTUTURE`** instead of **`DDOS_INFRASTRUCTURE`**—wrong spelling of *Infrastructure*), ingestion and checks expect the canonical id **`DDOS_INFRASTRUCTURE`**. After TheHive is running, run **`make thehive-canonicalize-templates`** once to PATCH names to match `thehive/config/case_templates.json`, then **`make thehive-templates`** to confirm.

**API key after restart:** The SOC automation scripts read **`thehive/setup/api_key.txt`**. If Cassandra or TheHive data was reset, or TheHive was recreated so the previous organisation API key no longer works, run **`make thehive-init`** again (or **`make thehive-rekey`** to renew only the key) before **`make ingest-alerts`**, **`make kpi-report`**, or **`make check-escalations`**. Otherwise automation may see empty results or HTTP 401.

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
| After **TheHive container restart** automation fails with 401 or empty cases | Run **`make thehive-init`** (or **`make thehive-rekey`**) so **`thehive/setup/api_key.txt`** matches a valid org API key |
| KPI / `soc_open_cases` show **0** but cases exist in the UI | TheHive 5 marks active cases as **`New`** (not only **`Open`**). Use a current **`kpi_tracker.py`**; refresh metrics with **`make kpi-report`** |
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

**Cortex Community Edition:** Many analysers appear as **`[NOT FOUND]`** in the UI or in **`make cortex-analysers`** output because CE ships a reduced catalog and images may not bundle every resolver. That is expected in this project. A **production** deployment typically uses Cortex Enterprise or full analyser images and valid vendor API keys (see placeholders in **`.env.example`**).

### Automation scripts

| Script | Command | Purpose |
|--------|---------|---------|
| `alert_ingestor.py` | `make ingest-alerts` | Creates 10 TheHive cases from mock alerts |
| `alert_enricher.py` | `make enrich-alerts` | Triggers Cortex on open-case observables |
| `misp_exporter.py` | `make export-iocs` | Exports resolved case IOCs to MISP |
| `kpi_tracker.py` | `make kpi-report` | SOC KPI report + Prometheus textfile metrics |

Free API keys for AbuseIPDB, VirusTotal, and Shodan are available at [abuseipdb.com](https://www.abuseipdb.com), [virustotal.com](https://www.virustotal.com), and [shodan.io](https://www.shodan.io). Copy **`ABUSEIPDB_API_KEY`**, **`VT_API_KEY`**, and **`SHODAN_API_KEY`** from **`.env.example`** into **`.env`** for production-style enrichment; the setup scripts use `demo_key` when a variable is unset (limited or placeholder behaviour).

### Troubleshooting

| Issue | What to check |
|-------|----------------|
| Cortex not starting | `docker compose logs cortex`; `cortex-db` must pass its healthcheck |
| No analysers found / **NOT FOUND** | Expected for **Cortex CE** for many analysers; enable what the catalog lists. For AbuseIPDB / VirusTotal / Shodan, set keys in **`.env`** (see **`.env.example`**) in a full deployment |
| TheHive connection failing | Run `make cortex-connect-thehive` |
| Jobs not completing | Confirm `/var/run/docker.sock` is mounted on `cortex`; inspect `docker compose logs cortex` |

---

## Sprint 5 — KPIs, Escalation & Operations

### SOC KPI Dashboard

- **Grafana:** [http://localhost:3000](http://localhost:3000) — open **Catnip Games SOC - Security Dashboard** (folder: default provisioning).
- **Start KPI metrics server (Prometheus textfile on port 9102):** `make kpi-server` (Prometheus scrapes `host.docker.internal:9102` as job `soc_kpi`).
- **Generate KPI report:** `make kpi-report`
- **Check SLA-style escalations against open cases:** `make check-escalations` (dry-run: `make check-escalations-dry`)

Prometheus must be able to reach the KPI server from Docker Desktop (e.g. run `kpi-server` on the host so `host.docker.internal:9102` is alive).

### KPI Targets

| Metric | Target | Current |
|--------|--------|---------|
| Alert triage time | ≤15 minutes | Tracked in TheHive |
| Daily alert capacity | 1000/day | 10 simulated |
| Intelligence sharing latency | <5 minutes | 1.00 seconds |
| SLA compliance | ≥90% | Tracked via `kpi_tracker.py` |
| Patch compliance | ≥95% | Tracked via Prometheus |

### Escalation Tiers

| Tier | Account | Handles | SLA |
|------|---------|---------|-----|
| L1 | soc.analyst@catnipgames.com | Triage, low/medium | 15 min |
| L2 | soc.admin@catnipgames.com | High severity, breaches | 30 min |
| L3 | IR Lead | Critical, GDPR, comms | Immediate |

### Documentation Index

| File | Purpose |
|------|---------|
| `docs/playbooks/playbook_bot_attack.md` | Bot/exploit response |
| `docs/playbooks/playbook_account_compromise.md` | Account takeover response |
| `docs/playbooks/playbook_social_engineering.md` | Phishing/SE response |
| `docs/playbooks/playbook_ddos.md` | DDoS response |
| `docs/escalation/escalation_procedures.md` | When and how to escalate |
| `docs/runbook/operational_runbook.md` | Day-to-day SOC operations |

### MITRE ATT&CK Coverage

| Playbook | Tactics Covered | Key Techniques |
|----------|-----------------|----------------|
| Bot Attack | Initial Access, Execution, Impact | T1078, T1059, T1499 |
| Account Compromise | Credential Access, Initial Access | T1110, T1078 |
| Social Engineering | Initial Access, Reconnaissance | T1566, T1598 |
| DDoS | Impact, Reconnaissance | T1498, T1499 |

---

## Sprint 6 — Automatic Log Generator

The log generator simulates realistic security events from Catnip Games infrastructure continuously. It generates IDS alerts, firewall blocks, failed logins, game server alerts, WAF events, and DLP alerts — automatically creating TheHive cases and exporting IOCs to MISP when thresholds are breached.

### Quick start

```bash
make start-logs          # Start with all integrations
make start-logs-fast     # Start in fast mode (demo)
make view-logs           # Watch live event feed
make logs-status         # Check if running
make stop-logs           # Stop generator
```

### Attack profiles

| Profile | Threshold | TheHive Template | MITRE |
|---------|-----------|------------------|-------|
| IDS Alert | 10/30s | BOT_ATTACK | T1190 |
| Firewall Block | 50/30s | BOT_ATTACK | T1190 |
| Failed Login | 20/30s | ACCOUNT_COMPROMISE | T1110 |
| Game Server | 5/30s | BOT_ATTACK | T1499 |
| WAF Alert | 15/30s | BOT_ATTACK | T1190 |
| DLP Alert | 3/30s | ACCOUNT_COMPROMISE | T1005 |

### Log files

| File | Contents |
|------|----------|
| `logs/combined.log` | All events |
| `logs/ids_alert.log` | IDS alerts only |
| `logs/firewall_block.log` | Firewall events |
| `logs/failed_login.log` | Auth failures |
| `logs/game_server_alert.log` | Game integrity events |
| `logs/waf_alert.log` | WAF blocks |
| `logs/dlp_alert.log` | Data loss events |

### Grafana integration

New panels added to the SOC dashboard show live event rates, IDS alert breakdown, auto-created cases count, and MISP IOC export count. All update every 15 seconds.

### Scalability note

In production, replace `generator.py` with a Syslog receiver or webhook endpoint to ingest real events from Snort, Suricata, pfSense, or cloud WAF. The TheHive and MISP integration code remains unchanged.

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
  grafana/provisioning/ # datasources, dashboards (Node Overview, SOC KPI)
  alertmanager/         # alertmanager.yml (console + Slack/email)
  ansible/
    playbooks/          # patch_orchestrator.yml, drift_check.yml
    roles/              # common, health_check, patch, reporting
    inventory/          # hosts.ini, dev.ini, staging.ini, prod.ini (blue/green)
  cortex/
    setup/              # init_cortex, configure_analysers, connect_thehive, verify_cortex
    automation/         # alert_ingestor, alert_enricher, misp_exporter, kpi_tracker, kpi_metrics_server, escalation_manager
  .github/workflows/    # ci.yml (lint, build, patch, validate, SOC checks)
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
