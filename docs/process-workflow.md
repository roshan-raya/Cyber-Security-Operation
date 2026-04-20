# Process Workflow — Patch Lifecycle
**Catnip Games International — Patch Management System**

This document describes every stage of the patch lifecycle from trigger to verified
compliance report, covering both the automated CI path and the manual operator path.

---

## Automated CI Workflow (GitHub Actions)

Triggered on: push to `main`, `develop`; any pull request.

```
Push / Pull Request
        │
        ▼
Step 1: Ansible lint check (ansible-lint ansible/)
        │── FAIL ──► Block merge. Fix lint errors.
        │
        ▼
Step 2: Build Docker images (--profile sim, --no-cache)
        │── FAIL ──► Build error. Check Dockerfile syntax.
        │
        ▼
Step 3: Start full stack
        │   cp .env.example .env
        │   docker compose --profile sim up -d
        │   sleep 45
        │
        ▼
Step 4: Ansible syntax check (--syntax-check only, no execution)
        │── FAIL ──► Block merge. Fix playbook YAML syntax.
        │
        ▼
Step 5: Run patch orchestration (make patch)
        │
        │   Play 1 runs on all 5 targets in parallel (strategy: free):
        │     Role: common
        │       └── record patch_start_epoch
        │           set patch_failed = false
        │     Role: health_check
        │       └── gather_facts
        │           ping (connection check)
        │           uptime check
        │           SSH service check
        │     Role: patch
        │       ├── capture pre-patch package snapshot ──► rollback_packages fact
        │       └── block:
        │             apt update_cache
        │             apt upgrade: safe
        │             check /var/run/reboot-required
        │             reboot if required
        │             wait_for_connection
        │             assert uptime >= 0
        │           rescue:
        │             set patch_failed = true
        │             include rollback.yml (if rollback_enabled=true)
        │
        │   Play 2 runs on localhost only:
        │     Role: reporting
        │       └── build patch_report_list from hostvars
        │           calculate compliance_percentage
        │           write patch_report_<epoch>.json
        │           write patch_report_latest.json
        │           write patch_report_latest.csv
        │           write patch_metrics.prom
        │
        ▼
Step 6: Validate report gates
        │   compliance_percentage >= 95? ─── NO ──► FAIL pipeline
        │   duration_seconds <= 7200?    ─── NO ──► FAIL pipeline
        │   failed_hosts == 0?           ─── NO ──► FAIL pipeline
        │── ALL PASS ──► Pipeline succeeds
        │
        ▼
Step 7: Tear down (always runs, even on failure)
        docker compose --profile sim down -v
```

---

## Manual Operator Workflow

### Standard patch window

```
Before patching:
  1.  git pull origin main
  2.  docker compose --profile sim up -d && sleep 30
  3.  make validate                       ← Prometheus + Grafana healthy?
  4.  make patch-health                   ← all 5 targets reachable?
  5.  make backup LABEL=pre-patch-YYYYMMDD  ← snapshot volumes
  6.  make patch-dryrun                   ← review what will change

Patch execution:
  7.  make patch                          ← run the patch
  8.  make validate-reports               ← ≥95% compliance confirmed?
  9.  make patch-report                   ← read the full JSON report
  10. open http://localhost:3000          ← confirm Grafana shows new data

Post-patch:
  11. Archive proof: docker compose exec ansible \
        cat /ansible/reports/patch_report_latest.json \
        > docs/evidence/patch-YYYYMMDD.json
```

### Targeted patch (single host or group)

```bash
# Single host
make patch ENV=hosts LIMIT=patch-target-3

# Staging environment only
make patch-staging

# Blue group only (before patching green)
make patch-blue
make validate-reports
make patch-green
make validate-reports
```

### Phased production-style rollout (canary → batch → remainder)

For lab environments mirroring production controls, run the phased playbook instead of
patching every host in parallel:

```bash
make patch-canary-phased
```

This executes `playbooks/patch_canary.yml`: one canary host, a two-host batch, then
the remaining hosts, with health gates between phases and `max_fail_percentage`
limits so a canary failure stops the run before wider exposure.

### Emergency rollback for a specific host

```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  --limit <hostname> \
  -e rollback_enabled=true \
  -e patch_environment=rollback
```

---

## Chaos and performance verification (Sprint 3)

After major changes or before a demo, run automated resilience and SLO evidence:

```bash
make benchmark          # full patch + backup check + writes performance-report.md
make chaos-test         # all three chaos scenarios (or chaos-test-1 / -2 / -3)
```

Narrative and expected behaviour: [docs/chaos-testing.md](chaos-testing.md).
Evidence paths: `docs/evidence/chaos/`, `docs/evidence/performance-report.md`.

---

## Report Artefacts

After every patch run, the reporting role writes four files inside the ansible container:

| File | Format | Purpose |
|---|---|---|
| `patch_report_latest.json` | JSON | Machine-readable; used by validate-reports and CI gate |
| `patch_report_<epoch>.json` | JSON | Timestamped archive; retained for audit trail |
| `patch_report_latest.csv` | CSV | Human-readable; can be opened in spreadsheet tools |
| `patch_metrics.prom` | Prometheus text | Scraped by Prometheus via metrics_exporter.py |
| `patch_report_latest.json.sha256` | Text | SHA256 checksum line for `patch_report_latest.json` (integrity verification) |
| `audit_trail.log` | Text | Append-only log of each run: timestamp, env, group, compliance, duration, checksum |

Key fields in the JSON report:
- `compliance_percentage` — (successful_hosts / total_hosts) × 100
- `duration_seconds` — wall-clock time from first host start to report write
- `hosts[]` — per-host array with: host, changed, failed, rebooted, rollback_performed
- `environment` — value of patch_environment variable at run time
- `group` — value of patch_group variable at run time

---

## Alert Rules Reference

| Alert name | Condition | Severity | Fires after |
|---|---|---|---|
| PatchComplianceBelow95 | compliance_percentage < 95 | warning | 1 minute |
| PatchFailure | patch_host_success == 0 | warning | 1 minute |
| PatchDurationTooHigh | duration_seconds > 120 | warning | 1 minute |
| PatchNotRunRecently | no run in 24 hours | warning | 5 minutes |
| PatchFailureCritical | patch_host_success == 0 | critical | 2 minutes |
| PatchHostUnreachable | metrics exporter down | critical | 2 minutes |
| PatchComplianceLow | compliance_percentage < 80 | warning | 5 minutes |
| CriticalCVEsRemaining | patch_scan_critical_cves > 0 | critical | 5 minutes |
| HighCVEsAboveThreshold | patch_scan_high_cves > 5 | warning | 5 minutes |
