# Chaos Testing — Patch Management Platform
**Catnip Games International**

Chaos testing validates that this system recovers correctly from real-world failures
that could occur during a production patch window.

## Why chaos testing matters

A patch management system that only works under ideal conditions is not production
ready. These tests prove that failures are handled gracefully — hosts recover,
reports reflect reality, and no silent failures occur.

## Scenarios

### Scenario 1: Target node failure mid-patch

**What it tests:** A patch target becomes unreachable mid-run (container crash,
network failure, power loss).

**Failure injected:** `docker compose stop patch-target-3` during a patch run.

**Expected behaviour:**
- Other hosts complete patching successfully
- Unreachable host is reported as failed (not silently skipped)
- After host recovers, it can be re-patched individually
- Compliance percentage reflects the actual state

**Recovery command:**
```bash
docker compose start patch-target-3
make patch ENV=hosts LIMIT=patch-target-3
```

---

### Scenario 2: Metrics exporter goes down

**What it tests:** The Prometheus metrics endpoint becomes unavailable during
a monitoring window.

**Failure injected:** The chaos script terminates the `metrics_exporter.py` process
inside the ansible container (the image has no `pkill`; it uses a short Python
`/proc` scan, same outcome as `pkill -f`).

**Expected behaviour:**
- Prometheus detects the patch_metrics target as DOWN within 15 seconds
- PatchHostUnreachable alert fires (critical severity)
- Alert routes to critical receivers (webhook + Slack + PagerDuty)
- After exporter restarts, metrics resume and alert resolves

**Recovery command:**
```bash
docker compose exec ansible \
  sh -c 'nohup python3 /ansible/metrics_exporter.py >/tmp/metrics_exporter.log 2>&1 &'
```

---

### Scenario 3: Patch failure with automatic rollback

**What it tests:** A patch fails mid-run and the rollback mechanism executes
automatically.

**Failure injected:** `-e fail_host=patch-target-1 -e rollback_enabled=true`

**Expected behaviour:**
- Failure simulation triggers on patch-target-1
- Rescue block executes rollback.yml
- rollback_performed=true in patch report
- patch-target-1 remains reachable via SSH after rollback
- Host can be re-patched after root cause is resolved

**Recovery command:**
```bash
make patch ENV=hosts LIMIT=patch-target-1
```

---

## Running chaos tests

```bash
# Optional: set a webhook URL only if you want script-level summary posts
# (Alertmanager notification routing is configured separately in alertmanager.yml)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

# All scenarios
make chaos-test

# Individual scenarios
make chaos-test-1
make chaos-test-2
make chaos-test-3
```

Evidence is saved to `docs/evidence/chaos/` after each run.
If a webhook URL is set, the script posts Scenario 3 rollback status and a final run summary.

## Evidence files

| File | Contents |
|---|---|
| `chaos_summary.log` | One line per run with pass/fail counts |
| `*_scenario1_node_failure.txt` | Ansible output from node failure test |
| `*_scenario2_exporter_down.txt` | Metrics before/after exporter kill |
| `*_scenario3_rollback.txt` | Full rollback playbook output |
