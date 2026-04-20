# Individual Screencast Script
**Catnip Games International — Patch Management System**
Duration: 5 minutes exactly

---

## Pre-recording checklist

```bash
# Run these before hitting record
docker compose --profile sim up -d
sleep 30
make patch          # ensure clean state
make validate       # confirm healthy
```

Browser tabs ready:
- http://localhost:3000 (Grafana — Patch Management SLO dashboard)
- http://localhost:9090 (Prometheus)
- https://webhook.site/53813426-de90-4268-a2d4-eabee6ee7fa4

Terminal: full screen, large font (18pt minimum), dark theme.

---

## Minute 1 — Architecture and repo structure (0:00–1:00)

**Say:**
"This is the automated patch management system I built for Catnip Games
International. The company manages 300 Linux servers across two data centres.
This system automates patch deployment, monitors compliance, and alerts on
failures."

**Show:** `docs/technical-architecture.md` — point at the ASCII diagram
briefly. Then switch to terminal.

**Type:**
```bash
ls -la
```

**Say:**
"The repo has Ansible playbooks for orchestration, Prometheus and Grafana for
monitoring, Docker Compose for the test environment, and a full docs folder
including Architecture Decision Records, a recovery runbook, and test cases."

```bash
ls ansible/playbooks/
ls docs/
```

---

## Minute 2 — Live patch deployment (1:00–2:30)

**Say:**
"I'll now run a live patch across all 5 servers."

**Type:**
```bash
make patch
```

**While it runs, say:**
"This runs the patch_orchestrator playbook. It has four roles in sequence —
common records the start time, health_check verifies SSH and uptime on every
host, patch runs apt update and safe upgrade with automatic reboot if needed,
and reporting generates a signed JSON report with compliance metrics."

**After it completes, type:**
```bash
make validate-reports
```

**Say:**
"The validation gate checks three things — compliance is at or above 95%,
duration is under 2 hours, and no hosts failed. All three are passing."

---

## Minute 3 — Monitoring dashboard (2:30–3:30)

**Switch to Grafana browser tab.**

**Say:**
"This is the SLO dashboard I built with 7 panels. The compliance gauge shows
100% — above our 95% SLO. Duration is under 30 seconds — well inside the 2
hour window. All 5 hosts are green in the per-host grid."

**Switch to Prometheus tab.**

**Type in Prometheus query bar:**
```
patch_compliance_percentage
```

**Say:**
"Prometheus is scraping the custom patch metrics from the Ansible container
every 15 seconds. This is the compliance metric that drives the alert rules
and the Grafana dashboard."

---

## Minute 4 — Failure and alert demo (3:30–4:30)

**Switch to terminal.**

**Say:**
"I'll now demonstrate the failure detection and alerting pipeline."

**Type:**
```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini \
  playbooks/patch_orchestrator.yml \
  -e fail_host=patch-target-1 \
  -e rollback_enabled=true
```

**While it runs, say:**
"This uses the built-in failure simulation flag to force a patch failure on
target-1 and trigger the automatic rollback. The rescue block in the patch
role captures the failure and runs rollback.yml, which reinstalls packages
from the pre-patch snapshot."

**After it completes:**
```bash
docker compose exec ansible \
  sh -c 'jq "{compliance,rollback_performed: .hosts[0].rollback_performed}" \
  /ansible/reports/patch_report_latest.json'
```

**Say:**
"The report shows rollback_performed is true. Now I'll wait for the
Prometheus alert to fire and route to our webhook endpoint."

**Switch to webhook.site tab — wait for POST to appear.**

**Say:**
"There's the alert — PatchFailureCritical, severity critical, routed to the
webhook-critical receiver in Alertmanager. In production this would go to
Slack or PagerDuty."

---

## Minute 5 — Report integrity and summary (4:30–5:00)

**Switch to terminal.**

**Type:**
```bash
make verify-report
```

**Say:**
"Every patch report is SHA256 signed. This command verifies the report was
not modified after the run. The audit trail shows every run with timestamp,
environment, compliance percentage, and checksum."

**Quickly show:**
```bash
make benchmark
```

**Say:**
"The benchmark script proves all 5 performance requirements — patch window,
backups, concurrent updates, monitoring refresh, and 95% success rate. All
passing."

**Final line:**
"This system is production-ready — automated, monitored, recoverable, and
fully documented."

---

## Recording tips

- Use `clear` between major sections
- Pause 1 second after typing each command before hitting enter
- Keep the cursor visible at all times
- If something goes wrong, stop recording and restart — do not continue with errors
- Target exactly 5 minutes — practice the run-through twice before recording
