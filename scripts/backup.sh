#!/usr/bin/env bash
# backup.sh — Pre-patch Docker volume snapshot
#
# Usage:   ./scripts/backup.sh [label]
# Example: ./scripts/backup.sh pre-patch
#
# Creates timestamped tar.gz archives of all persistent volumes.
# Writes a manifest.json with SHA256 checksums for restore verification.
# Exit code 0 = all volumes backed up. Exit code 1 = one or more failed.

set -euo pipefail

# Why: macOS does not provide sha256sum by default; use shasum as a compatible fallback.
if command -v sha256sum >/dev/null 2>&1; then
  SHA256_CMD="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SHA256_CMD="shasum -a 256"
else
  echo "ERROR: neither sha256sum nor shasum is available"
  exit 1
fi

LABEL="${1:-pre-patch}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/${TIMESTAMP}_${LABEL}"
MANIFEST="${BACKUP_DIR}/manifest.json"

# All persistent volumes defined in docker-compose.yml
VOLUMES=(
  "csoproject_prometheus_data"
  "csoproject_grafana_data"
  "csoproject_alertmanager_data"
  "csoproject_ansible_reports"
)

echo "╔══════════════════════════════════════╗"
echo "║   Catnip Games — Volume Backup       ║"
echo "╚══════════════════════════════════════╝"
echo "  Label     : ${LABEL}"
echo "  Timestamp : ${TIMESTAMP}"
echo "  Output    : ${BACKUP_DIR}"
echo ""

mkdir -p "${BACKUP_DIR}"

# Build manifest entries as a bash array of JSON strings
ENTRIES=()
OVERALL_STATUS="success"
BACKED_UP=0
SKIPPED=0
FAILED=0

for VOLUME in "${VOLUMES[@]}"; do
  ARCHIVE="${BACKUP_DIR}/${VOLUME}.tar.gz"
  printf "  %-45s" "Backing up ${VOLUME}..."

  # Skip if volume does not exist (stack may not be running)
  if ! docker volume inspect "${VOLUME}" > /dev/null 2>&1; then
    echo "SKIP (not found)"
    ENTRIES+=("{\"volume\":\"${VOLUME}\",\"status\":\"skipped\",\"reason\":\"volume not found\"}")
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Archive via disposable alpine container — no data touches the host filesystem directly
  if docker run --rm \
    -v "${VOLUME}:/source:ro" \
    -v "$(pwd)/${BACKUP_DIR}:/dest" \
    alpine:3.19 \
    tar czf "/dest/${VOLUME}.tar.gz" -C /source . 2>/dev/null; then

    SIZE=$(du -sh "${ARCHIVE}" 2>/dev/null | cut -f1)
    CHECKSUM=$(${SHA256_CMD} "${ARCHIVE}" | cut -d' ' -f1)
    echo "OK  (${SIZE})  sha256:${CHECKSUM:0:16}…"
    ENTRIES+=("{\"volume\":\"${VOLUME}\",\"archive\":\"${VOLUME}.tar.gz\",\"size_human\":\"${SIZE}\",\"sha256\":\"${CHECKSUM}\",\"status\":\"ok\"}")
    BACKED_UP=$((BACKED_UP + 1))
  else
    echo "FAILED"
    ENTRIES+=("{\"volume\":\"${VOLUME}\",\"status\":\"failed\"}")
    OVERALL_STATUS="partial"
    FAILED=$((FAILED + 1))
  fi
done

# Build and write manifest.json
ENTRIES_JSON=$(printf '%s\n' "${ENTRIES[@]}" | paste -sd ',' - | sed 's/^/[/;s/$/]/')

cat > "${MANIFEST}" << EOF
{
  "backup_label": "${LABEL}",
  "timestamp": "${TIMESTAMP}",
  "backup_dir": "${BACKUP_DIR}",
  "status": "${OVERALL_STATUS}",
  "summary": {
    "backed_up": ${BACKED_UP},
    "skipped": ${SKIPPED},
    "failed": ${FAILED}
  },
  "volumes": ${ENTRIES_JSON}
}
EOF

echo ""
echo "  Manifest  : ${MANIFEST}"
echo "  Summary   : ${BACKED_UP} backed up, ${SKIPPED} skipped, ${FAILED} failed"
echo "  Status    : ${OVERALL_STATUS}"
echo ""

if [ "${OVERALL_STATUS}" != "success" ]; then
  echo "WARNING: Some volumes failed. Review manifest before patching."
  exit 1
fi

echo "Backup complete. To restore: ./scripts/restore.sh ${BACKUP_DIR}"
