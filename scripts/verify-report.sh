#!/usr/bin/env bash
# verify-report.sh — Verify the integrity of a patch report
# Usage: ./scripts/verify-report.sh [backup_dir]
# If no backup_dir given, verifies the latest report from the running container.

set -euo pipefail

BACKUP_DIR="${1:-}"

echo "╔══════════════════════════════════════╗"
echo "║   Patch Report Integrity Check       ║"
echo "╚══════════════════════════════════════╝"
echo ""

if [ -z "${BACKUP_DIR}" ]; then
  echo "Verifying latest report from running ansible container..."
  echo ""

  docker compose exec ansible sh -c '
    if [ ! -f /ansible/reports/patch_report_latest.json ]; then
      echo "ERROR: No report found. Run make patch first."
      exit 1
    fi

    if [ ! -f /ansible/reports/patch_report_latest.json.sha256 ]; then
      echo "ERROR: No signature file found. Report may predate Sprint 2."
      exit 1
    fi

    echo "Report: /ansible/reports/patch_report_latest.json"
    echo "Signature: /ansible/reports/patch_report_latest.json.sha256"
    echo ""

    cd /ansible/reports
    if sha256sum -c patch_report_latest.json.sha256; then
      echo ""
      echo "INTEGRITY CHECK: PASSED"
      echo "Report has not been tampered with."
    else
      echo ""
      echo "INTEGRITY CHECK: FAILED"
      echo "Report checksum does not match. Data may have been modified."
      exit 1
    fi

    echo ""
    echo "Audit trail (last 5 entries):"
    tail -5 /ansible/reports/audit_trail.log 2>/dev/null || echo "(no audit trail yet)"
  '
else
  echo "Verifying report in: ${BACKUP_DIR}"
  if [ ! -f "${BACKUP_DIR}/patch_report_latest.json" ]; then
    echo "ERROR: No report found in ${BACKUP_DIR}"
    exit 1
  fi

  cd "${BACKUP_DIR}"
  if sha256sum -c patch_report_latest.json.sha256 2>/dev/null; then
    echo "INTEGRITY CHECK: PASSED"
  else
    echo "INTEGRITY CHECK: FAILED"
    exit 1
  fi
fi
