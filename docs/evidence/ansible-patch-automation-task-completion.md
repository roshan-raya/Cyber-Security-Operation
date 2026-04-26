# Ansible Patch Automation — Evidence of Task Completion
**Catnip Games International (DevOps Team)**  
Date: 2026-04-22

## 1) Objective Covered
Design and implement an automated patch management system for Linux infrastructure using Ansible, with monitoring/reporting integration, to reduce patch inconsistency risk across environments.

This evidence document is intentionally scoped to **Ansible patch automation only**.

## 2) Scope Clarification
- The business scenario references ~300 Linux servers across two data centres.
- This repository implements a **production-style design** and validates it in a **local simulation fleet (5 hosts)**.
- Evidence below shows the automation patterns required for larger fleets: grouped inventory, phased rollout, patch orchestration, rollback path, and compliance reporting.

## 3) Completion Checklist (Implemented)
| Requirement | Implementation Evidence | Status |
|---|---|---|
| Automated Linux patch orchestration | `ansible/playbooks/patch_orchestrator.yml` with role chain `common -> health_check -> patch -> security_scan` | ✅ Complete |
| Multi-environment inventory model | `ansible/inventory/dev.ini`, `staging.ini`, `production.ini`, `hosts.ini` | ✅ Complete |
| Two-DC / grouped rollout model | `hosts.ini` groups: `dc1`, `dc2`, `canary`, `blue`, `green`, `patch_targets` | ✅ Complete |
| Safe rollout controls | Canary/phased options via `patch-canary` and `patch_canary.yml`; targeted rollout via `patch-blue`, `patch-green`, `--limit` | ✅ Complete |
| Dry-run capability | `ansible/playbooks/patch_dryrun.yml` (`check_mode: true`) | ✅ Complete |
| Rollback path | `ansible/playbooks/rollback.yml`, `ansible/roles/patch/tasks/rollback.yml`, toggle `rollback_enabled` | ✅ Complete |
| Patch evidence artifacts | Reporting role writes JSON/CSV/Prometheus metrics in `/ansible/reports` | ✅ Complete |
| Compliance/SLA validation gate | `make validate-reports` checks compliance %, duration, and failed hosts | ✅ Complete |
| CI enforcement | `.github/workflows/ci.yml` runs lint/syntax/patch/report gates | ✅ Complete |

## 4) File-Level Evidence (Ansible Only)
- Control configuration:
  - `ansible/ansible.cfg`
  - `ansible/inventory/group_vars/all.yml`
- Playbooks:
  - `ansible/playbooks/patch_orchestrator.yml`
  - `ansible/playbooks/patch_dryrun.yml`
  - `ansible/playbooks/health_check.yml`
  - `ansible/playbooks/rollback.yml`
  - `ansible/playbooks/patch_canary.yml`
  - `ansible/playbooks/drift_check.yml`
- Roles:
  - `ansible/roles/common/tasks/main.yml`
  - `ansible/roles/health_check/tasks/main.yml`
  - `ansible/roles/patch/tasks/main.yml`
  - `ansible/roles/patch/tasks/rollback.yml`
  - `ansible/roles/security_scan/tasks/main.yml`
  - `ansible/roles/reporting/tasks/main.yml`
  - `ansible/roles/reporting/templates/patch_report.csv.j2`
  - `ansible/roles/reporting/templates/patch_metrics.prom.j2`

## 5) Execution Evidence Procedure
Run the following to generate objective proof of completion.

```bash
cd /Users/roshanrayamajhi/Desktop/CSOPROJECT
docker compose --profile sim up -d

# 1) Dry-run (no package changes applied)
make patch-dryrun

# 2) Health gate
make patch-health

# 3) Full automated patch orchestration
make patch

# 4) Validate reporting/SLA gates
make validate-reports
```

Expected artifacts after `make patch`:
- `/ansible/reports/patch_report_latest.json`
- `/ansible/reports/patch_report_latest.csv`
- `/ansible/reports/patch_metrics.prom`
- `/ansible/reports/patch_report_latest.json.sha256`
- `/ansible/reports/audit_trail.log`

## 6) Acceptance Criteria Mapping
- **Automated maintenance:** centralised Ansible orchestration applies updates across host groups.
- **Security operations alignment:** patching + optional security scan role + rollback controls + audit trail.
- **Automation practices:** reusable roles, inventory-based targeting, dry-run mode, phased rollout options, CI validation.
- **Monitoring/reporting integration:** Ansible reporting emits Prometheus-readable metrics and structured patch reports.

## 7) Known Limitation (Transparent Statement)
- The repository validates behavior on a 5-host simulation rather than 300 real servers.
- This is a deliberate lab implementation; the same inventory-and-role structure is ready to scale with dynamic inventory and production host onboarding.

## 8) Completion Statement
The Ansible patch automation objective is implemented and evidenced in this repository through:
- orchestrated patch playbooks,
- environment-aware inventory design,
- dry-run/canary/rollback controls,
- report generation and compliance checks,
- and CI-enforced automation quality gates.

**Conclusion:** Task completion criteria for the Ansible patch automation scope are satisfied.
