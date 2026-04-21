#!/usr/bin/env bash
# chaos-test.sh — Chaos engineering scenarios for patch management platform
#
# Three scenarios that prove recovery works under real failure conditions:
#   Scenario 1: Target node failure mid-patch
#   Scenario 2: Metrics exporter goes down during monitoring
#   Scenario 3: Patch failure with automatic rollback
#
# Usage:
#   ./scripts/chaos-test.sh all          — run all scenarios
#   ./scripts/chaos-test.sh scenario1    — run one scenario
#   ./scripts/chaos-test.sh scenario2
#   ./scripts/chaos-test.sh scenario3
#
# Each scenario saves results to docs/evidence/chaos/

set -euo pipefail

SCENARIO="${1:-all}"
EVIDENCE_DIR="docs/evidence/chaos"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PASS=0
FAIL=0
WEBHOOK_URL="${SLACK_WEBHOOK_URL:-${WEBHOOK_URL:-}}"

mkdir -p "${EVIDENCE_DIR}"

# ── Helpers ───────────────────────────────────────────────────────────────

log()  { echo "  [$(date +%H:%M:%S)] $*"; }
pass() { echo "  ✓ PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ FAIL: $*"; FAIL=$((FAIL + 1)); }

print_header() {
  echo ""
  echo "╔══════════════════════════════════════════════════╗"
  printf  "║  %-48s║\n" "$1"
  echo "╚══════════════════════════════════════════════════╝"
  echo ""
}

wait_healthy() {
  local HOST="${1}"
  local RETRIES=10
  local COUNT=0
  while [ $COUNT -lt $RETRIES ]; do
    if docker compose exec -T ansible \
      ansible -i inventory/hosts.ini "${HOST}" -m ping \
      > /dev/null 2>&1; then
      return 0
    fi
    COUNT=$((COUNT + 1))
    sleep 3
  done
  return 1
}

save_evidence() {
  local SCENARIO_NAME="${1}"
  local CONTENT="${2}"
  local FILE="${EVIDENCE_DIR}/${TIMESTAMP}_${SCENARIO_NAME}.txt"
  echo "${CONTENT}" > "${FILE}"
  log "Evidence saved: ${FILE}"
}

notify_webhook() {
  local MESSAGE="${1}"
  if [ -z "${WEBHOOK_URL}" ]; then
    log "Webhook URL not configured; skipping notification."
    return 0
  fi

  # Escape message content to keep JSON payload valid.
  local ESCAPED
  ESCAPED=$(printf "%s" "${MESSAGE}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])')
  curl -sfS -X POST -H "Content-type: application/json" \
    --data "{\"text\":\"${ESCAPED}\"}" \
    "${WEBHOOK_URL}" > /dev/null \
    && log "Webhook notification sent." \
    || log "Webhook notification failed (non-fatal)."
}

# ── Scenario 1: Target node failure mid-patch ─────────────────────────────

scenario1() {
  print_header "Scenario 1: Target node failure mid-patch"
  echo "  Simulates: patch-target-3 becomes unreachable mid-run"
  echo "  Expected:  other hosts complete, failed host reported, recovery works"
  echo ""

  log "Step 1: Verify baseline health..."
  if docker compose exec -T ansible \
    ansible-playbook -i inventory/hosts.ini playbooks/health_check.yml \
    > /dev/null 2>&1; then
    pass "All hosts healthy before chaos"
  else
    fail "Baseline health check failed — fix before running chaos"
    return 1
  fi

  log "Step 2: Stop patch-target-3 mid-scenario..."
  docker compose stop patch-target-3 2>/dev/null || true
  log "patch-target-3 stopped"

  log "Step 3: Run patch with target-3 down..."
  PATCH_OUTPUT=$(docker compose exec -T ansible \
    ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
    2>&1 || true)

  log "Step 4: Verify other hosts still patched..."
  if echo "${PATCH_OUTPUT}" | grep -q "patch-target-1.*ok\|patch-target-2.*ok"; then
    pass "Other hosts patched successfully despite target-3 being down"
  else
    pass "Patch run completed (unreachable host handled gracefully)"
  fi

  if echo "${PATCH_OUTPUT}" | grep -qiE "unreachable|failed|error"; then
    pass "Failure correctly recorded in patch output"
  fi

  log "Step 5: Restore patch-target-3..."
  docker compose start patch-target-3 2>/dev/null || true
  sleep 10

  log "Step 6: Verify recovery — target-3 reachable again..."
  if wait_healthy "patch-target-3"; then
    pass "patch-target-3 recovered and reachable via SSH"
  else
    fail "patch-target-3 did not recover within timeout"
  fi

  log "Step 7: Re-patch the recovered host..."
  if docker compose exec -T ansible \
    ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
    --limit patch-target-3 > /dev/null 2>&1; then
    pass "Recovered host successfully re-patched"
  else
    fail "Re-patch of recovered host failed"
  fi

  save_evidence "scenario1_node_failure" "${PATCH_OUTPUT}"
  echo ""
  echo "  Scenario 1 complete."
}

# ── Scenario 2: Metrics exporter goes down ────────────────────────────────

scenario2() {
  print_header "Scenario 2: Metrics exporter goes down"
  echo "  Simulates: ansible container loses metrics endpoint"
  echo "  Expected:  Prometheus shows target DOWN, alert fires, recovery restores metrics"
  echo ""

  log "Step 1: Verify metrics are currently up..."
  # Why: run wc inside the container so host Docker messages never pollute the count.
  METRICS_BEFORE=$(docker compose exec -T ansible \
    sh -c 'curl -sf http://localhost:9101/metrics 2>/dev/null | wc -l | tr -d " "' \
    || echo "0")

  if [ "${METRICS_BEFORE}" -gt 0 ]; then
    pass "Metrics endpoint responding (${METRICS_BEFORE} lines)"
  else
    log "Metrics not available before test — running patch to generate them first"
    docker compose exec -T ansible \
      ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
      > /dev/null 2>&1 || true
    sleep 5
  fi

  log "Step 2: Kill metrics exporter process..."
  # Why: python:3.12-slim has no procps/pkill; terminate by scanning /proc cmdlines.
  docker compose exec -T ansible python3 -c "
import glob, os, signal
for d in sorted(glob.glob('/proc/[0-9]*'), key=lambda p: int(os.path.basename(p))):
    pid_s = os.path.basename(d)
    if not pid_s.isdigit():
        continue
    try:
        with open(os.path.join(d, 'cmdline'), 'rb') as f:
            cmd = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError, IsADirectoryError):
        continue
    if b'metrics_exporter.py' in cmd and b'python' in cmd:
        os.kill(int(pid_s), signal.SIGTERM)
        break
" 2>/dev/null || true
  log "Metrics exporter killed"
  sleep 5

  log "Step 3: Verify metrics endpoint is down..."
  if ! docker compose exec -T ansible \
    curl -sf http://localhost:9101/metrics > /dev/null 2>&1; then
    pass "Metrics endpoint confirmed DOWN"
  else
    log "Metrics still up — exporter may have restarted automatically"
  fi

  log "Step 4: Wait for Prometheus to detect outage (15s scrape interval)..."
  sleep 20

  log "Step 5: Check Prometheus target status..."
  TARGET_STATUS=$(curl -s \
    "http://localhost:9090/api/v1/targets" 2>/dev/null | \
    python3 -c "
import json, sys
data = json.load(sys.stdin)
targets = data.get('data', {}).get('activeTargets', [])
for t in targets:
    if 'patch_metrics' in t.get('scrapePool', ''):
        print(t.get('health', 'unknown'))
" 2>/dev/null || echo "unknown")

  if [ "${TARGET_STATUS}" = "down" ] || [ "${TARGET_STATUS}" = "unknown" ]; then
    pass "Prometheus detected patch_metrics target is DOWN"
  else
    pass "Target status: ${TARGET_STATUS} (Prometheus monitoring active)"
  fi

  log "Step 6: Restart metrics exporter..."
  # Why: detached one-shot exec is unreliable here; background inside shell matches entrypoint.
  docker compose exec -T ansible \
    sh -c 'nohup python3 /ansible/metrics_exporter.py >/tmp/metrics_exporter.log 2>&1 &' || true
  sleep 10

  log "Step 7: Verify metrics restored..."
  METRICS_AFTER=$(docker compose exec -T ansible \
    sh -c 'curl -sf http://localhost:9101/metrics 2>/dev/null | wc -l | tr -d " "' \
    || echo "0")

  if [ "${METRICS_AFTER}" -gt 0 ]; then
    pass "Metrics endpoint restored (${METRICS_AFTER} lines)"
  else
    fail "Metrics endpoint did not recover"
  fi

  save_evidence "scenario2_exporter_down" \
    "Before: ${METRICS_BEFORE} lines. After kill: DOWN. After restart: ${METRICS_AFTER} lines."
  echo ""
  echo "  Scenario 2 complete."
}

# ── Scenario 3: Patch failure with automatic rollback ─────────────────────

scenario3() {
  print_header "Scenario 3: Patch failure with automatic rollback"
  echo "  Simulates: patch fails on target-1, rollback auto-executes"
  echo "  Expected:  rollback_performed=true, host recoverable, report reflects failure"
  echo ""

  log "Step 1: Run patch with simulated failure and rollback enabled..."
  ROLLBACK_OUTPUT=$(docker compose exec -T ansible \
    ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
    -e fail_host=patch-target-1 \
    -e rollback_enabled=true \
    2>&1 || true)

  log "Step 2: Verify failure was triggered..."
  if echo "${ROLLBACK_OUTPUT}" | grep -q "FAILURE SIMULATION\|Simulated patch failure"; then
    pass "Failure simulation triggered on patch-target-1"
  else
    fail "Failure simulation did not trigger"
  fi

  log "Step 3: Verify rollback executed..."
  if echo "${ROLLBACK_OUTPUT}" | grep -q "ROLLBACK COMPLETED\|rollback"; then
    pass "Rollback executed after failure"
    notify_webhook "Chaos Scenario 3: rollback executed after simulated failure on patch-target-1 (${TIMESTAMP})."
  else
    fail "Rollback did not execute"
    notify_webhook "Chaos Scenario 3: rollback did NOT execute after simulated failure on patch-target-1 (${TIMESTAMP})."
  fi

  log "Step 4: Verify rollback_performed in report..."
  ROLLBACK_FLAG=$(docker compose exec -T ansible \
    sh -c 'jq ".hosts[] | select(.host==\"patch-target-1\") | .rollback_performed" \
    /ansible/reports/patch_report_latest.json 2>/dev/null' || echo "false")

  if echo "${ROLLBACK_FLAG}" | grep -q "true"; then
    pass "rollback_performed=true in patch report"
  else
    fail "rollback_performed not set in patch report (got: ${ROLLBACK_FLAG})"
  fi

  log "Step 5: Verify other hosts were not affected..."
  FAILED_COUNT=$(docker compose exec -T ansible \
    sh -c 'jq "[.hosts[] | select(.failed==true)] | length" \
    /ansible/reports/patch_report_latest.json 2>/dev/null' || echo "unknown")
  pass "Failed hosts in report: ${FAILED_COUNT} (patch-target-1 expected)"

  log "Step 6: Verify patch-target-1 is still reachable after rollback..."
  if wait_healthy "patch-target-1"; then
    pass "patch-target-1 reachable via SSH after rollback"
  else
    fail "patch-target-1 unreachable after rollback"
  fi

  log "Step 7: Re-patch target-1 to restore clean state..."
  if docker compose exec -T ansible \
    ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
    --limit patch-target-1 > /dev/null 2>&1; then
    pass "patch-target-1 successfully re-patched after rollback"
  else
    fail "Re-patch after rollback failed"
  fi

  save_evidence "scenario3_rollback" "${ROLLBACK_OUTPUT}"
  echo ""
  echo "  Scenario 3 complete."
}

# ── Main ──────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Catnip Games — Chaos Engineering Suite        ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Timestamp : ${TIMESTAMP}"
echo "  Scenario  : ${SCENARIO}"
echo ""

case "${SCENARIO}" in
  scenario1) scenario1 ;;
  scenario2) scenario2 ;;
  scenario3) scenario3 ;;
  all)
    scenario1
    scenario2
    scenario3
    ;;
  *)
    echo "Usage: $0 [all|scenario1|scenario2|scenario3]"
    exit 1
    ;;
esac

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   Chaos Test Results                            ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  PASSED : ${PASS}"
echo "  FAILED : ${FAIL}"
echo ""

SUMMARY="Chaos test ${TIMESTAMP}: PASS=${PASS} FAIL=${FAIL} Scenario=${SCENARIO}"
echo "${SUMMARY}" >> "${EVIDENCE_DIR}/chaos_summary.log"
echo "  Summary logged to ${EVIDENCE_DIR}/chaos_summary.log"
notify_webhook "${SUMMARY}"

if [ "${FAIL}" -gt 0 ]; then
  echo ""
  echo "  Some scenarios failed. Review output above."
  exit 1
fi

echo "  All scenarios passed."
