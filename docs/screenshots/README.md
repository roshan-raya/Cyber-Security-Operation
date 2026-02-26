# Screenshots (documentation evidence)

## prometheus_alert_proof.png

Evidence that the `PatchComplianceBelow95` Prometheus alert fires when compliance drops below 95%.

**How to capture:**

1. Start the stack: `docker compose --profile sim up -d`
2. Run failure simulation so compliance drops:
   ```bash
   docker compose exec ansible sh -lc "cd /ansible && ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml -e fail_host=patch-target-3"
   ```
3. Open Prometheus: http://localhost:9090
4. Go to **Status → Alerts**
5. Find **PatchComplianceBelow95** (alert name, expression, firing status, timestamp)
6. Take a screenshot and save it here as `prometheus_alert_proof.png`

Referenced in [Sprint4_Enterprise.md](../Sprint4_Enterprise.md#prometheus-alert-evidence).
