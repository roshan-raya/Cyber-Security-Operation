# Test Cases — Automated Patch Management System
**Catnip Games International**

## Test Environment

```bash
# Start environment before running any tests
cp .env.example .env
docker compose --profile sim up -d
sleep 45
make validate    # confirm Prometheus and Grafana are healthy
```

All commands run from the project root unless stated otherwise.
Expected results marked with ✓. Failure criteria marked with ✗.

---

## TC-001: SSH connectivity to all patch targets

**Covers:** Health check role, inventory configuration
**Command:**
```bash
make patch-health
```
**Pass:** All 5 hosts (patch-target-1 through 5) show "SSH OK, uptime OK, ssh service active". Exit code 0.
**Fail:** Any host shows UNREACHABLE or FAILED.

---

## TC-002: Dry run — no changes applied to targets

**Covers:** Check mode, apt module, safe preview before live patching
**Command:**
```bash
make patch-dryrun
```
**Pass:** Playbook exits 0. All tasks show `ok` or `skipping`. Zero tasks show `changed`. Dry run summary reports upgrade would_change and reboot_required for each host.
**Fail:** Any task shows `changed` (would mean check_mode is not working).

---

## TC-003: Full patch deployment — success path

**Covers:** Complete patch lifecycle, 2-hour window requirement, 95% compliance requirement
**Commands:**
```bash
make patch
make validate-reports
```
**Pass:**
- `make validate-reports` prints `=== PASS ===`
- `compliance_percentage` ≥ 95 in patch_report_latest.json
- `duration_seconds` ≤ 7200
- No host has `"failed": true`

**Fail:** Any FAIL line in validate-reports output.

**Evidence capture:**
```bash
docker compose exec ansible \
  cat /ansible/reports/patch_report_latest.json \
  > docs/evidence/TC-003-patch-report.json
```

---

## TC-004: Concurrent updates — 5 hosts in parallel

**Covers:** strategy: free, ≥5 concurrent update requirement
**Command:**
```bash
time make patch 2>&1 | tee docs/evidence/TC-004-timing.txt
```
**Pass:**
- All 5 hosts appear in patch_report_latest.json
- Total elapsed time is not a multiple of single-host time (confirms parallelism)
- Prometheus target count shows 5 patch targets active

**Fail:** Hosts patched sequentially (timing would be ~5× longer).

---

## TC-005: Patch failure simulation and rollback

**Covers:** Rollback capability, rescue block, rollback_packages fact, pre-patch snapshot
**Command:**
```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  -e fail_host=patch-target-1 \
  -e rollback_enabled=true
```
**Pass:**
- patch-target-1 hits "FAILURE SIMULATION" task and enters the rescue block
- rollback.yml runs on patch-target-1
- "ROLLBACK COMPLETED" appears in Ansible output
- patch_report_latest.json shows `"failed": true` for patch-target-1
- `"rollback_performed": true` in patch-target-1 entry
- Other 4 hosts complete successfully

**Fail:** rollback.yml crashes with "undefined variable"; rescue block does not execute.

**Evidence capture:**
```bash
docker compose exec ansible \
  cat /ansible/reports/patch_report_latest.json \
  > docs/evidence/TC-005-rollback-report.json
```

---

## TC-006: Prometheus metrics endpoint

**Covers:** metrics_exporter.py, patch_metrics scrape job, monitoring refresh requirement
**Command:**
```bash
make metrics-test
```
**Pass:**
- HTTP 200 response
- Output contains `patch_compliance_percentage`
- Output contains `patch_host_success`
- Output contains `patch_run_duration_seconds`

**Fail:** Connection refused or missing metric names.

---

## TC-007: Alert rule firing — PatchComplianceBelow95

**Covers:** Alert rules, Prometheus evaluation, alertmanager routing
**Commands:**
```bash
# Cause compliance to drop below 95% (4/5 = 80%)
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  -e fail_host=patch-target-1 \
  -e rollback_enabled=false

# Wait for Prometheus to evaluate the rule (evaluation interval is 1m)
echo "Waiting 90 seconds for Prometheus evaluation..."
sleep 90

# Check alert state
curl -s http://localhost:9090/api/v1/alerts | python3 -m json.tool
```
**Pass:**
- `PatchComplianceBelow95` appears in the API response with `"state": "firing"`
- Alert visible at http://localhost:9090/alerts
- If ALERTMANAGER_WEBHOOK_URL is set: POST received at webhook.site

**Fail:** No alerts appear in Prometheus UI after 90 seconds.

---

## TC-008: Backup creation and integrity verification

**Covers:** scripts/backup.sh, Docker volume snapshots, SHA256 integrity
**Commands:**
```bash
make backup LABEL=tc-008-test
ls -la backups/
cat backups/*tc-008*/manifest.json
```
**Pass:**
- Backup directory created under `backups/`
- `manifest.json` written with `"status": "success"`
- All 4 volumes present in manifest with `"status": "ok"`
- SHA256 checksums present for each archive

**Fail:** Missing manifest, `"status": "partial"` or `"failed"` entries, missing archives.

---

## TC-009: Configuration drift detection

**Covers:** drift_check.yml, dpkg package audit
**Command:**
```bash
make patch-drift
```
**Pass:**
- Playbook exits 0
- Each host shows a summary line with package count
- Held or inconsistently-installed package count reported (can be 0)

**Fail:** Exit code non-zero, UNREACHABLE hosts.

---

## TC-010: Grafana dashboard accessibility

**Covers:** Grafana provisioning, datasource configuration, dashboard JSON
**Manual test:**
1. Open http://localhost:3000
2. Log in (credentials from .env)
3. Navigate to Dashboards → Node Overview
4. Confirm panels display data (not "No data")

**Pass:** At least 3 panels show populated data after running TC-003.
**Fail:** Panels show "No data" or dashboard fails to load.

---

## TC-011: Phased canary rollout

**Covers:** patch_canary.yml, serial batching, max_fail_percentage, health gates
**Command:**
```bash
make patch-canary-phased
```
**Pass:**
- Phase 1 (canary) completes on patch-target-1 before Phase 2 starts
- Health gate runs between phases
- Phase 2 patches patch-target-2 and patch-target-3
- Phase 3 patches patch-target-4 and patch-target-5
- Ansible output shows phase names in play headers

**Fail:** All hosts patch simultaneously (would mean serial is not working).

---

## TC-012: Canary auto-halt on failure

**Covers:** max_fail_percentage: 0 on canary phase, automatic rollout halt
**Command:**
```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_canary.yml \
  -e fail_host=patch-target-1
```
**Pass:**
- Phase 1 fails on patch-target-1
- Ansible halts — Phase 2 and Phase 3 do NOT run
- Output shows "Failure percentage ... is greater than maximum" error

**Fail:** Phase 2 or Phase 3 runs despite Phase 1 failure.

---

## TC-013: Patch report integrity verification

**Covers:** SHA256 report signing, audit trail, verify-report.sh
**Commands:**
```bash
make patch
make verify-report
```
**Pass:**
- Output shows "INTEGRITY CHECK: PASSED"
- Audit trail shows the latest run entry
- patch_report_latest.json.sha256 file exists in container

**Fail:** "INTEGRITY CHECK: FAILED" or missing signature file.

---

## TC-014: SLO dashboard loads in Grafana

**Covers:** patch-slo.json provisioning, Prometheus datasource, SLO panels
**Manual test:**
1. Open http://localhost:3000
2. Navigate to Dashboards → Patch Management SLO
3. Confirm all 7 panels load with data after running make patch

**Pass:** Compliance gauge, duration stat, per-host success row all show values.
**Fail:** Dashboard not found, or all panels show "No data".

---

## TC-015: Chaos test — node failure mid-patch

**Covers:** scripts/chaos-test.sh scenario1, recovery procedures
**Command:**
```bash
make chaos-test-1
```
**Pass:** All steps show ✓ PASS. Evidence saved to docs/evidence/chaos/.
**Fail:** Any ✗ FAIL line in output.

---

## TC-016: Chaos test — metrics exporter recovery

**Covers:** scripts/chaos-test.sh scenario2, Prometheus alerting on outage
**Command:**
```bash
make chaos-test-2
```
**Pass:** Exporter confirmed DOWN then restored. Evidence saved.
**Fail:** Exporter did not recover within timeout.

---

## TC-017: Performance benchmark — all 5 requirements

**Covers:** scripts/benchmark.sh, all performance SLOs
**Command:**
```bash
make benchmark
```
**Pass:** All 5 requirements show ✅ PASS in output and in
docs/evidence/performance-report.md.
**Fail:** Any requirement shows ❌ FAIL.
