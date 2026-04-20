# Recovery Runbook
**Catnip Games International — Patch Management Platform**
Audience: on-call DevOps engineer

---

## Quick Reference Card

| Symptom | First command |
|---|---|
| Patch failed on one host | `make patch-health` then see Scenario 1 |
| Compliance below 95% | See Scenario 1 — identify and rollback failed hosts |
| Grafana shows no data | `make metrics-test` then see Scenario 4 |
| Full data loss / corruption | See Scenario 2 — restore from backup |
| Prometheus not responding | `docker compose restart prometheus` |
| Alertmanager not routing | `docker compose logs alertmanager --tail=50` |

---

## Scenario 1: Patch failure on one or more hosts

**Trigger:** `make patch` exits non-zero, or `make validate-reports` prints FAIL.

**Step 1 — Identify failed hosts**
```bash
docker compose exec ansible \
  sh -c 'jq ".hosts[] | select(.failed == true) | {host, msg}" \
  /ansible/reports/patch_report_latest.json'
```

**Step 2 — Check the failure message**
```bash
docker compose exec ansible \
  sh -c 'jq ".hosts[] | select(.failed == true) | .msg" \
  /ansible/reports/patch_report_latest.json'
```

**Step 3 — Run rollback on the failed host**
```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  --limit <failed_hostname> \
  -e rollback_enabled=true \
  -e patch_environment=rollback
```

Expected output: "ROLLBACK COMPLETED" log line, rollback_performed=true in JSON report.

**Step 4 — Verify the host is healthy after rollback**
```bash
docker compose exec ansible \
  ansible -i inventory/hosts.ini <failed_hostname> -m ping
make patch-health
```

**Step 5 — Investigate root cause, then re-patch**
```bash
make patch-dryrun          # preview what will change
make patch                 # run the actual patch
make validate-reports      # confirm ≥95% compliance
```

---

## Scenario 2: Full restore from volume backup

**When to use:**
- Accidental `docker compose down -v` destroyed volume data
- Grafana database corrupted
- Prometheus TSDB corrupted
- Migrating the stack to a new host

**Prerequisites:** A backup must exist in the `backups/` directory.

**Step 1 — List available backups**
```bash
ls -lt backups/
cat backups/<most_recent>/manifest.json
```

**Step 2 — Stop all services**
```bash
docker compose down
```

**Step 3 — Run the restore script**
```bash
./scripts/restore.sh backups/<timestamp_label>
```
The script will:
- Display the backup manifest
- Ask you to type 'yes' to confirm
- Verify SHA256 checksum of each archive before restoring
- Skip any archive with a checksum mismatch (logs a warning)

**Step 4 — Restart the full stack**
```bash
docker compose --profile sim up -d
sleep 30
```

**Step 5 — Validate everything is healthy**
```bash
make validate
make validate-reports
```

**Step 6 — Confirm in browser**
- Prometheus targets: http://localhost:9090/targets (all scrape targets should be UP)
- Grafana: http://localhost:3000 (Node Overview dashboard should show data)

---

## Scenario 3: Prometheus or Grafana unreachable

**Step 1 — Check container state**
```bash
docker compose ps
```

**Step 2 — Check logs for startup errors**
```bash
docker compose logs prometheus --tail=50
docker compose logs grafana --tail=50
```

**Step 3 — Attempt restart**
```bash
docker compose restart prometheus
docker compose restart grafana
```

**Step 4 — Validate configuration**
```bash
make lint-prometheus
```

**Step 5 — If config is broken, restore from backup (Scenario 2)**

---

## Scenario 4: Patch metrics not appearing in Grafana

**Step 1 — Check metrics exporter endpoint directly**
```bash
make metrics-test
```
Expected: HTTP 200 with `patch_compliance_percentage` and `patch_host_success` lines.

**Step 2 — Check Prometheus scrape status**

Open http://localhost:9090/targets and look for the `patch_metrics` job.
Status should be UP. If it shows DOWN, the ansible container is not running.

**Step 3 — Ensure ansible container is running**
```bash
docker compose ps ansible
docker compose --profile sim up -d
```

**Step 4 — Run a fresh patch to generate metrics**
```bash
make patch
```
Wait 15 seconds (one scrape interval) then refresh Prometheus.

---

## Rollback Decision Tree

```
Patch failure detected?
        │
        ├── Is the host reachable via SSH?
        │         │
        │         ├── YES → Run rollback playbook (Scenario 1, Step 3)
        │         │
        │         └── NO  → Recreate the container:
        │                     docker compose up -d --force-recreate patch-target-N
        │                     Then re-run make patch
        │
        └── Is compliance_percentage below 95%?
                  │
                  ├── YES → Rollback all failed hosts, find root cause, re-patch
                  │
                  └── NO  → Document failure in evidence, re-run patch for
                             failed hosts only using --limit flag
```

---

## Pre-Patch Checklist (run before every patch window)

```bash
docker compose --profile sim up -d   # confirm stack is running
sleep 30
make validate                        # confirm Prometheus and Grafana healthy
make patch-health                    # confirm all targets reachable via SSH
make backup LABEL=pre-patch-$(date +%Y%m%d)   # snapshot all volumes
make patch-dryrun                    # preview changes before applying
```

Only proceed to `make patch` after all five commands above succeed.
