# Catnip Games SOC — Operational Runbook

## Platform Overview
URL map:
| Service | URL | Purpose |
|---------|-----|---------|
| TheHive | http://localhost:9000 | Case management |
| MISP | http://localhost:8080 | Threat intelligence |
| Cortex | http://localhost:9001 | Auto enrichment |
| Grafana | http://localhost:3000 | Dashboards |
| Prometheus | http://localhost:9090 | Metrics |
| Alertmanager | http://localhost:9093 | Alert routing |

## Daily SOC Operations

### Morning Checklist (start of shift)
1. Run: make thehive-status
2. Run: make misp-verify  
3. Run: make cortex-verify
4. Run: make kpi-report
5. Review open cases in TheHive
6. Check Grafana SOC dashboard for anomalies
7. Verify MISP feeds synced in last 24 hours

### Alert Response Workflow
1. Alert received → check TheHive for auto-created case
2. If no case → run: make ingest-alerts
3. Triage case → assign to analyst
4. Run enrichment: make enrich-alerts
5. Work case tasks per relevant playbook
6. Export IOCs: make export-iocs
7. Close case with resolution

### End of Shift
1. Run: make kpi-report --output both --save
2. Ensure all High severity cases have updates
3. Hand over open cases to next shift in TheHive

## How to Add a New Analyst
1. Log into TheHive as soc.admin@catnipgames.com
2. Go to Organisation → Users → New User
3. Set profile: analyst
4. Share TheHive URL and temporary password
5. New analyst reads: docs/playbooks/ before first shift

## How to Add a New Cortex Analyser
1. Log into Cortex as admin at http://localhost:9001
2. Go to Organizations → CatnipGamesSOC → Analyzers
3. Enable desired analyser
4. Add API key if required (AbuseIPDB, VirusTotal, Shodan)
5. Test: create a test case in TheHive with an IP observable
6. Run: make enrich-alerts --case-id {testCaseId}
7. Verify result appears in case timeline

## How to Rotate API Keys

### TheHive API key rotation
curl -u "admin@thehive.local:secret" \
  -X POST http://localhost:9000/api/v1/user/soc.admin@catnipgames.com/key/renew
echo "NEW_KEY" > thehive/setup/api_key.txt

### Cortex API key rotation
Log into http://localhost:9001 as admin
Go to Users → admin → Renew API Key
echo "NEW_KEY" > cortex/setup/cortex_api_key.txt

### MISP API key rotation
Run: make misp-init
Updates .misp_auth_key automatically

## Stack Recovery Procedures

### Full stack restart
docker compose down
docker compose up -d
Wait 3 minutes then run: make thehive-status

### TheHive lost all users (after volume wipe)
make thehive-init
make thehive-templates (verify templates still exist)
make thehive-canonicalize-templates

### MISP login fails
Check: grep MISP_ADMIN_PASSWORD .env
If password changed in UI: update .env to match
Run: make misp-verify

### Cortex not starting on Apple Silicon M1
ES7 needs ARM64 platform flag in docker-compose.yml
cortex-db must use: platform: linux/arm64
Allow 2-3 minutes for startup under emulation
Run: make cortex-status to verify

### API key expired errors
TheHive: make thehive-init (regenerates key)
Cortex: manual renewal via http://localhost:9001
MISP: make misp-init

## KPI Targets
| Metric | Target | Current |
|--------|--------|---------|
| Alert triage time | ≤15 minutes | Tracked in TheHive |
| Daily alert capacity | 1000/day | 10 simulated |
| Intelligence sharing latency | <5 minutes | 1.00 seconds |
| SLA compliance | ≥90% | Tracked via kpi_tracker.py |
| Patch compliance | ≥95% | Tracked via Prometheus |

## Architecture Diagram (text)
Game Servers / IDS Alerts
        ↓
   alert_ingestor.py
        ↓
   TheHive (cases + tasks)
        ↓
   Cortex (auto enrichment)
        ↓
   MISP (IOC lookup + sharing)
        ↓
   misp_exporter.py (confirmed IOCs → MISP)
        ↑
   Prometheus + Grafana (platform health + KPIs)
   Ansible (patch management + compliance)
