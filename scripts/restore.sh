#!/usr/bin/env bash
# restore.sh — Restore Docker volumes from a backup created by backup.sh
#
# Usage:   ./scripts/restore.sh <backup_dir>
# Example: ./scripts/restore.sh backups/20240419_143000_pre-patch
#
# Verifies SHA256 checksums from manifest before restoring each volume.
# Requires confirmation before overwriting live data.
# Services must be stopped before running this script.

set -euo pipefail

BACKUP_DIR="${1:-}"

# Why: macOS does not provide sha256sum by default; use shasum as a compatible fallback.
if command -v sha256sum >/dev/null 2>&1; then
  SHA256_CMD="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SHA256_CMD="shasum -a 256"
else
  echo "ERROR: neither sha256sum nor shasum is available"
  exit 1
fi

# ── Argument check ────────────────────────────────────────────────────────
if [ -z "${BACKUP_DIR}" ]; then
  echo "Usage: $0 <backup_dir>"
  echo ""
  echo "Available backups:"
  if [ -d "backups" ] && [ "$(ls -A backups 2>/dev/null)" ]; then
    ls -lt backups/ | grep "^d" | awk '{print "  " $NF}' | head -10
  else
    echo "  (no backups found — run: make backup)"
  fi
  exit 1
fi

if [ ! -d "${BACKUP_DIR}" ]; then
  echo "ERROR: Directory not found: ${BACKUP_DIR}"
  exit 1
fi

MANIFEST="${BACKUP_DIR}/manifest.json"
if [ ! -f "${MANIFEST}" ]; then
  echo "ERROR: No manifest.json in ${BACKUP_DIR}"
  echo "       This may not be a valid backup directory."
  exit 1
fi

# ── Show backup info ──────────────────────────────────────────────────────
echo "╔══════════════════════════════════════╗"
echo "║   Catnip Games — Volume Restore      ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Backup manifest:"
cat "${MANIFEST}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "WARNING: This will OVERWRITE current volume data."
echo "         Stop services first: docker compose down"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -r -p "Type 'yes' to confirm restore: " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
  echo "Aborted — no changes made."
  exit 0
fi

# ── Stop services ─────────────────────────────────────────────────────────
echo ""
echo "Stopping services..."
docker compose down 2>/dev/null || true

# ── Restore each volume ───────────────────────────────────────────────────
RESTORE_STATUS="success"
RESTORED=0
FAILED=0

for ARCHIVE in "${BACKUP_DIR}"/*.tar.gz; do
  [ -f "${ARCHIVE}" ] || continue
  VOLUME=$(basename "${ARCHIVE}" .tar.gz)
  printf "  %-45s" "Restoring ${VOLUME}..."

  # Verify checksum against manifest before touching anything
  EXPECTED=$(python3 -c "
import json, sys
with open('${MANIFEST}') as f:
    m = json.load(f)
vols = [v for v in m.get('volumes', []) if v.get('volume') == '${VOLUME}']
print(vols[0].get('sha256', '') if vols else '')
" 2>/dev/null)

  if [ -n "${EXPECTED}" ]; then
    ACTUAL=$(${SHA256_CMD} "${ARCHIVE}" | cut -d' ' -f1)
    if [ "${EXPECTED}" != "${ACTUAL}" ]; then
      echo "CHECKSUM MISMATCH — skipping (backup may be corrupt)"
      RESTORE_STATUS="partial"
      FAILED=$((FAILED + 1))
      continue
    fi
  fi

  # Ensure the volume exists before restoring into it
  docker volume create "${VOLUME}" > /dev/null 2>&1 || true

  # Restore via disposable alpine container
  if docker run --rm \
    -v "${VOLUME}:/dest" \
    -v "$(pwd)/${BACKUP_DIR}:/source:ro" \
    alpine:3.19 \
    sh -c "cd /dest && tar xzf /source/${VOLUME}.tar.gz" 2>/dev/null; then
    echo "OK"
    RESTORED=$((RESTORED + 1))
  else
    echo "FAILED"
    RESTORE_STATUS="partial"
    FAILED=$((FAILED + 1))
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "  Restored : ${RESTORED} volumes"
echo "  Failed   : ${FAILED} volumes"
echo "  Status   : ${RESTORE_STATUS}"
echo ""
echo "Next steps:"
echo "  1. docker compose --profile sim up -d"
echo "  2. sleep 30 && make validate"
echo "  3. make validate-reports"

if [ "${RESTORE_STATUS}" != "success" ]; then
  echo ""
  echo "WARNING: Some volumes failed to restore. Check output above."
  exit 1
fi
