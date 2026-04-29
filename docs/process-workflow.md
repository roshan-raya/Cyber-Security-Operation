# Process Workflow — Patch Lifecycle
**Catnip Games International — Patch Management System (as built)**

This document describes how patching is actually run in this repository, both in CI and
for manual operator runs.

---

## 1) CI workflow (GitHub Actions)

Primary validation workflow: `.github/workflows/ci.yml`

Trigger:
- push to `main`, `master`, `develop`
- pull request

Execution order:
1. `ansible-lint ansible/`
2. `docker compose --profile sim build --no-cache`
3. start stack (`cp .env.example .env`, `docker compose --profile sim up -d`, sleep 45)
4. playbook syntax checks
5. `make patch`
6. gate checks from `/ansible/reports/patch_report_latest.json`:
   - compliance >= 95
   - duration <= 7200 seconds
   - failed hosts == 0
7. `make validate-patch-fleet`
8. optional rollback on patch step failure
9. `docker compose --profile sim down -v` (always)

Operational workflow: `.github/workflows/patch.yml`
- push to `main`, scheduled cron, manual dispatch
- runs `make patch`, validates reports/fleet, optional rollback, then teardown

Extended regression workflow: `.github/workflows/extended-validation.yml`
- runs `make benchmark` and `make chaos-test`
- uploads evidence artifacts

---

## 2) Manual operator workflow

### Standard patch window

```bash
git pull origin main
docker compose --profile sim up -d
sleep 30
make validate
make patch-health
make backup LABEL=pre-patch-YYYYMMDD
make patch-dryrun
make patch
make validate-reports
make patch-report
```

Validation checkpoints:
- Prometheus targets are up at `http://localhost:9090/targets`
- Grafana loads at `http://localhost:3000`
- latest report passes compliance and duration checks

### Targeted patch execution

```bash
# Single host
make patch ENV=hosts LIMIT=patch-target-3

# Staging only
make patch-staging

# Blue/green split
make patch-blue
make validate-reports
make patch-green
make validate-reports
```

### Emergency rollback (single host)

```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  --limit <hostname> \
  -e rollback_enabled=true \
  -e patch_environment=rollback
```

---

## 3) Patch report artifacts

The reporting role writes artifacts to `/ansible/reports/`:

| File | Format | Purpose |
|---|---|---|
| `patch_report_latest.json` | JSON | Main report used by `validate-reports` and CI gates |
| `patch_report_<epoch>.json` | JSON | Timestamped archive |
| `patch_report_latest.csv` | CSV | Human-readable summary |
| `patch_metrics.prom` | Prometheus text | Scraped by Prometheus via `metrics_exporter.py` |
| `patch_report_latest.json.sha256` | Text | Integrity checksum for latest JSON report |
| `audit_trail.log` | Text | Append-only audit lines per run |

Key JSON fields used by gates and dashboards:
- `compliance_percentage`
- `duration_seconds`
- `hosts[]` (host, changed, failed, rebooted, rollback_performed)
- `environment`
- `group`

---

## 4) Chaos and performance runs

Run before demo or after major changes:

```bash
make benchmark
make chaos-test
```

Reference: [docs/chaos-testing.md](chaos-testing.md)  
Current committed evidence path: `docs/evidence/chaos/`

---

## 5) Alert rules currently used

| Alert name | Condition | Severity | Fires after |
|---|---|---|---|
| PatchComplianceBelow95 | compliance_percentage < 95 | warning | 1 minute |
| PatchFailure | patch_host_success == 0 | warning | 1 minute |
| PatchDurationTooHigh | duration_seconds > 120 | warning | 1 minute |
| PatchNotRunRecently | no run in 24 hours | warning | 5 minutes |
| PatchMetricsStale | exporter up but last run timestamp stale | warning | 10 minutes |
| PatchFailureCritical | patch_host_success == 0 | critical | 2 minutes |
| PatchHostUnreachable | metrics exporter down | critical | 2 minutes |
| PatchComplianceLow | compliance_percentage < 80 | warning | 5 minutes |
| PatchDurationSLAExceeded | duration_seconds > 7200 | critical | 2 minutes |
| PatchComplianceCritical | compliance_percentage < 80 | critical | 5 minutes |
| PatchComplianceMetricMissing | compliance metric absent | critical | 2 minutes |
| CriticalCVEsRemaining | patch_scan_critical_cves > 0 | critical | 5 minutes |
| HighCVEsAboveThreshold | patch_scan_high_cves > 5 | warning | 5 minutes |

## 6) Alert routing currently used

Alertmanager routing in this implementation:
- warning -> Slack channel (`slack-warning`)
- critical -> webhook + Slack + PagerDuty (`webhook-critical`, `slack-critical`, `pagerduty-critical`)
- fallback -> console receiver

This routing was tested by triggering both warning and critical alerts and checking
delivery in Prometheus/Alertmanager and the downstream receivers.

Practical test notes from my implementation:
- Warning test: `PatchNotRunRecently` reached Slack.
- Critical test: stopping `ansible` triggered `PatchHostUnreachable` and `PatchComplianceMetricMissing`.
- Critical delivery was confirmed across webhook, Slack, and PagerDuty.
