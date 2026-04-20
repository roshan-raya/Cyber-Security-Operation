# Security review and hardening sign-off

**Purpose:** Close the project timeline weeks 9–10 (“system hardening and security review”) with a **repeatable checklist** and **formal sign-off**. This is an **internal** review suitable for coursework or team delivery—not a substitute for a third-party penetration test or compliance audit.

**Related:** [SECURITY.md](../SECURITY.md) (baseline controls), [ansible/roles/security_scan/](../ansible/roles/security_scan/) (post-patch Trivy OS scan), [docs/recovery-runbook.md](recovery-runbook.md) (recovery).

---

## 1. Scope

| In scope | Out of scope (unless your brief requires it) |
|----------|-----------------------------------------------|
| Patch platform (Ansible targets, SSH, sudo) | Full organisational ISMS certification |
| Monitoring stack (Prometheus, Grafana, Alertmanager) | Windows fleet patching |
| Secrets handling (`.env`, Vault guidance) | Third-party red team / pen test |
| Container and Compose posture | Production cloud account IAM review |

---

## 2. Review checklist

Complete each row before sign-off. Evidence can be a command output, screenshot, PR link, or log path under `docs/evidence/`.

### 2.1 Identity, secrets, and access

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| S1 | `.env` is not committed; production would use a secrets manager (see SECURITY.md §2). | ☐ | |
| S2 | Grafana admin credentials are not default in production deployments (change from template if demoing externally). | ☐ | |
| S3 | Ansible SSH keys live only in Docker volume / are not in Git (see SECURITY.md §8). | ☐ | |
| S4 | Optional: Ansible Vault documented (`ansible/vault/README.md`) and used for any real secrets if applicable. | ☐ | |

### 2.2 Container and runtime hardening

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| C1 | Monitoring images are version-pinned in `docker-compose.yml` (not `latest`). | ☐ | |
| C2 | Prometheus/Grafana run as non-root where applicable; read-only rootfs used per Compose. | ☐ | |
| C3 | No unnecessary `privileged: true` or broad host mounts on new services. | ☐ | |

### 2.3 Network exposure

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| N1 | Operator understanding: 9090/3000 are for lab access; production would restrict by VPN/SG (SECURITY.md §3, §7). | ☐ | |
| N2 | Patch metrics exporter (9101) not published to host; internal scrape only. | ☐ | |

### 2.4 Patch and vulnerability posture

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| P1 | `security_scan` role runs post-patch; critical CVE policy understood (`scan_fail_on_critical` in group vars). | ☐ | |
| P2 | Rollback path exercised at least once before assessment (playbook / chaos scenario 3). | ☐ | |

### 2.5 Monitoring and alerting

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| M1 | Alert rules loaded; Alertmanager routes reviewed for your environment (`alertmanager/alertmanager.yml`). | ☐ | |
| M2 | Scrape intervals meet SLA (≤ 5 min refresh requirement; see `prometheus/prometheus.yml`). | ☐ | |

### 2.6 Recovery and backups

| # | Item | Pass? | Evidence / notes |
|---|------|-------|------------------|
| R1 | `make backup` / `make restore` or runbook steps verified on a non-production clone. | ☐ | |
| R2 | Backup manifests list expected volumes (`backups/*/manifest.json`). | ☐ | |

---

## 3. Findings log (optional)

| ID | Severity | Finding | Remediation | Owner | Status |
|----|----------|---------|-------------|-------|--------|
| F-001 | | | | | Open / Closed |

---

## 4. Formal sign-off

**Review outcome:** ☐ Pass ☐ Pass with conditions (see findings) ☐ Fail (do not release to demo / prod)

**Conditions or exceptions (if any):**

---

**Reviewer**

| Field | Value |
|-------|--------|
| Name | |
| Role (e.g. DevOps lead, module assessor) | |
| Date (YYYY-MM-DD) | |
| Signature or initials | |

**Acknowledgement (optional second reviewer)**

| Field | Value |
|-------|--------|
| Name | |
| Role | |
| Date (YYYY-MM-DD) | |
| Signature or initials | |

---

## 5. Automation cross-reference

| Automation | What it proves |
|------------|----------------|
| `make benchmark` | Performance SLAs + writes `docs/evidence/performance-report.md` |
| `make chaos-test` | Recovery under failure; evidence under `docs/evidence/chaos/` |
| GitHub Actions “Extended validation” workflow | Runs benchmark + chaos on a schedule or manually (see `.github/workflows/extended-validation.yml`) |

Maintainers: keep this checklist version-controlled; export a PDF for submission if your institution requires a static artefact.
