# Sprint 4 — Enterprise Patch Platform

Sprint 4 adds role-based Ansible, environment separation (staging/production), blue/green patching, Alertmanager, compliance reporting, CI/CD via GitHub Actions, and security hardening.

---

## 1. Architecture (ASCII)

```
                    +------------------+
                    |  GitHub Actions  |
                    |  (push/cron/manual)|
                    +--------+---------+
                             | docker compose --profile sim up -d; make patch
                             v
+----------------+    +----------------+    +----------------+
|   Prometheus   |<---|    Ansible     |--->| 5 Patch Targets|
|   :9090        |    | (roles: common,|    | (staging: 1,2  |
|   + Alerting   |    |  health_check,  |    |  production:   |
|   -> Alertmgr  |    |  patch, report)|    |  blue: 3,4      |
+--------+-------+    +--------+-------+    |  green: 5)     |
         |                    |             +----------------+
         | scrape              | metrics :9101
         v                     v
+----------------+    +----------------+
|  Alertmanager  |    | patch_metrics  |
|  :9093         |    | (env, group,   |
|  (routes alerts)|   |  compliance %) |
+----------------+    +----------------+
         |
         v
+----------------+
|    Grafana     |
|  (dashboards + |
|   env filter)  |
+----------------+
```

---

## 2. Role-based Ansible

- **ansible/roles/common** — Record start time, set patch_failed default.
- **ansible/roles/health_check** — Ping, uptime, ensure sshd active.
- **ansible/roles/patch** — Gather facts, apt update/upgrade, reboot if required, validate; rescue sets patch_failed.
- **ansible/roles/reporting** — Ensure reports dir, build report list (with environment/group), write timestamped + latest JSON, write latest CSV, generate Prometheus metrics (including patch_compliance_percentage), summary.

**Playbook:** `playbooks/patch_orchestrator.yml` runs roles in order: common → health_check → patch → reporting.  
**Make:** `make patch` runs this playbook with default inventory (all targets). Existing `make patch-health` still uses `health_check.yml`; `make patch-report` shows latest JSON.

---

## 3. Environment separation

- **staging.ini** — `patch_targets` = patch-target-1, patch-target-2; `patch_environment=staging`.
- **production.ini** — `patch_targets` = production (blue + green); `patch_environment=production`.

**Make targets:**
- `make patch-staging` — `ansible-playbook -i inventory/staging.ini playbooks/patch_orchestrator.yml -e patch_environment=staging -e patch_group=staging`
- `make patch-production` — `ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml -e patch_environment=production -e patch_group=production`

Metrics and reports include `environment` (staging/production/unspecified).

---

## 4. Blue/Green production

In **production.ini**:
- **[blue]** — patch-target-3, patch-target-4  
- **[green]** — patch-target-5  

**Make targets:**
- `make patch-blue` — `ansible-playbook -i inventory/production.ini ... --limit blue -e patch_environment=production -e patch_group=blue`
- `make patch-green` — same with `--limit green -e patch_environment=production -e patch_group=green`

Reporting and metrics include `group` (blue/green/all). Dashboards show Blue Success % and Green Success %.

---

## 5. Alert flow

1. **Prometheus** evaluates alert rules (patch_alerts, patch_alerts_critical).
2. Firing alerts are sent to **Alertmanager** (config: `alertmanager/alertmanager.yml`).
3. Alertmanager routes by severity; receiver `console` is configured (webhook_configs empty; add Slack/email in production).
4. **New rules:** PatchFailureCritical (patch_host_success == 0, 2m), PatchHostUnreachable (patch_metrics down), PatchComplianceLow (patch_compliance_percentage < 80%).

---

## 6. CI/CD workflow

**File:** `.github/workflows/patch.yml`

- **Triggers:** push to main, manual (workflow_dispatch), cron at 02:00 UTC daily.
- **Steps:** checkout → Docker Buildx → `docker compose --profile sim up -d` → wait 30s → `make patch` → `make patch-report` (continue-on-error).
- **Runner:** ubuntu-latest. No hardcoded secrets; use GitHub secrets for production credentials if needed.

---

## 7. Security posture

- **SSH:** Root login disabled on patch targets; StrictModes yes; key-based only. Ansible uses persistent key in `ansible_ssh` volume.
- **Metrics:** Exporter (9101) internal-only; no host publish. No secrets in metrics.
- **Ansible:** Non-root container; `ansible_become: true` for privileged tasks only.
- **Production:** Use TLS for Prometheus/Grafana (reverse proxy); restrict Alertmanager and metrics to internal network; document in SECURITY.md.

---

## 8. Compliance and reporting

- **patch_report_latest.json** — Same structure as timestamped report; includes `compliance_percentage`, `environment`, `group`.
- **patch_report_latest.csv** — Header: host,changed,rebooted,failed,duration_seconds,timestamp,group,environment.
- **Metric:** `patch_compliance_percentage` = (sum(patch_host_success) / count(patch_host_success)) * 100, with labels environment and group.

---

## 9. Grafana (Sprint 4 panels)

- **Patch Compliance %** — From `patch_compliance_percentage`, filtered by Environment variable.
- **Failed Hosts Count** — `count(patch_host_success == 0)`.
- **Blue Success %** / **Green Success %** — Success rate by group, filtered by Environment.
- **Environment** — Template variable: `label_values(patch_host_success, environment)`; Include All option.

Existing Sprint 1–3 panels remain unchanged.

---

## 10. Final validation commands

After implementing Sprint 4, run:

1. **Start stack:**  
   `docker compose --profile sim up -d`

2. **Patch all (default inventory):**  
   `make patch`

3. **Metrics exporter:**  
   `make metrics-test`

4. **Prometheus targets:**  
   Visit http://localhost:9090/targets and confirm: **prometheus**, **node-exporter**, **patch_metrics**, **alertmanager** are UP.

5. **Grafana:**  
   Visit http://localhost:3000 and confirm **Node Overview** shows Sprint 4 panels (Patch Compliance %, Failed Hosts Count, Blue Success %, Green Success %, Environment variable).

6. **Environment / blue-green runs:**  
   ```bash
   make patch-staging
   make patch-production
   make patch-blue
   make patch-green
   ```

7. **Reports:**  
   Check that `ansible/reports/patch_report_latest.json` and `ansible/reports/patch_report_latest.csv` exist and contain correct host, changed, rebooted, failed, duration_seconds, timestamp, group, environment (and JSON includes top-level compliance_percentage and duration_seconds).

---

## 11. Production recommendations

- Pin Alertmanager and all images; run image scanning in CI.
- Configure Alertmanager with real receivers (Slack, PagerDuty, email).
- Use secrets manager for Grafana admin and any CI secrets.
- Run staging before production; use blue/green for zero-downtime patching.
- Put Prometheus, Grafana, and operator tools behind TLS and access control.

---

## 12. Failure simulation and rollback (demo)

**Failure simulation:** Pass `-e fail_host=<hostname>` to force that host to fail during the patch block (e.g. `-e fail_host=patch-target-3`). Compliance drops and `patch_host_success` for that host becomes 0; CI fails if compliance &lt; 95%.

**Rollback (optional):** In the patch role, if the block hits rescue and `rollback_enabled` is true, the role runs `roles/patch/tasks/rollback.yml` to reinstall baseline packages (pass `-e rollback_enabled=true -e 'rollback_packages=[\"curl\",\"vim\"]'`). Sets `rollback_performed: true` on the host.

**Prometheus alert:** Rule `PatchComplianceBelow95` (group `patching`) fires when `patch_compliance_percentage < 95` for 1m. The reporting role already exports `patch_compliance_percentage` in `patch_metrics.prom`.

**Demo script (copy/paste):**

```bash
# Clean pass
make patch

# Simulate failure on patch-target-3 (compliance drops + alert should fire)
docker compose exec ansible sh -lc "cd /ansible && ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml -e fail_host=patch-target-3" || true

# Evidence outputs
docker compose exec ansible sh -lc "grep compliance /ansible/reports/patch_report_latest.json"
docker compose exec ansible sh -lc "grep '\"failed\": true' /ansible/reports/patch_report_latest.json" || true
docker compose exec ansible sh -lc "grep patch_compliance_percentage /ansible/reports/patch_metrics.prom"
docker compose exec prometheus sh -lc "wget -qO- http://localhost:9090/api/v1/alerts | head -c 2000"
```

**Fail one host and run rollback:**

```bash
docker compose exec ansible sh -lc "cd /ansible && ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml -e fail_host=patch-target-3 -e rollback_enabled=true -e 'rollback_packages=[\"curl\",\"vim\"]'"
```

---

## 13. Project notes / Changelog

**fix(ansible): remove deprecated fact vars and align with facts API**

- common: set patch_start_epoch via `ansible_facts['date_time']['epoch']`
- patch: validate uptime via `ansible_facts['uptime_seconds']`
- Reduces deprecation warnings and improves forward compatibility with ansible-core 2.24+
