#!/usr/bin/env bash
set -euo pipefail

WEBHOOK_URL="${1:-${WEBHOOK_URL:-}}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
START_STACK="${START_STACK:-1}"

if [ -z "${WEBHOOK_URL}" ]; then
  echo "Usage: $0 <webhook-url>"
  echo "Or set WEBHOOK_URL environment variable."
  exit 1
fi

echo "=== Demo: Ansible patch + webhook ==="
echo "Webhook: ${WEBHOOK_URL}"
echo "Environment: ${ENVIRONMENT}"

if [ "${START_STACK}" = "1" ]; then
  echo "[1/4] Starting docker compose sim stack..."
  docker compose --profile sim up -d
else
  echo "[1/4] Skipping stack startup (START_STACK=${START_STACK})..."
fi

echo "[2/4] Running patch automation..."
if [ "${ENVIRONMENT}" = "all" ]; then
  make patch
else
  make patch ENV="${ENVIRONMENT}"
fi

echo "[3/4] Reading latest patch summary..."
SUMMARY_JSON="$(docker compose exec -T ansible sh -lc 'jq -c "{run_id,environment,duration_seconds,compliance_percentage,total_hosts,patched_hosts,failed_hosts}" /ansible/reports/patch_report_latest.json')"

echo "[4/4] Sending summary to webhook..."
PAYLOAD="$(jq -cn \
  --arg event "ansible-patch-demo" \
  --arg at "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --argjson summary "${SUMMARY_JSON}" \
  '{event:$event,timestamp_utc:$at,summary:$summary}')"

curl -sfS -X POST \
  -H "Content-Type: application/json" \
  --data "${PAYLOAD}" \
  "${WEBHOOK_URL}" >/dev/null

echo ""
echo "Demo completed successfully."
echo "Patch summary:"
echo "${SUMMARY_JSON}" | jq .
