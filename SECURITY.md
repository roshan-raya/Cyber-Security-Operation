# Security Considerations — Patch Management & Monitoring Platform

Baseline security considerations for the Sprint 1 monitoring stack and future expansion. Apply in line with your organisation’s policies and compliance requirements.

---

## 1. Least privilege

- **Containers:** Prometheus and Grafana run as non-root users (`nobody` / `grafana`). Node exporters run as `nobody`. No containers use `privileged: true`.
- **Filesystem:** Prometheus and Grafana use `read_only: true` with dedicated writable volumes only where needed (e.g. time-series DB, Grafana DB).
- **Recommendation:** Keep running as non-root; add no new privileged containers. For host metrics, node_exporter uses bind mounts with minimal host paths (`/proc`, `/sys`, `/`) and appropriate exclusions.

---

## 2. Secrets and credentials

- **No hardcoded secrets:** Grafana admin password and user are set via environment variables (`GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`) sourced from `.env`. `.env` is in `.gitignore` and must never be committed.
- **Use `.env.example`** as a template only; copy to `.env` and set strong, unique values. In production, use a secrets manager (e.g. HashiCorp Vault, cloud provider secrets) and inject env vars at deploy time.
- **Recommendation:** Rotate Grafana admin credentials regularly; use LDAP/OAuth/SSO when Grafana is deployed in production.

**Sprint 2 (Ansible):** SSH keys are generated inside the Ansible container on first run and the public key is shared to patch targets via a Docker volume. No keys are committed to the repo. For production, use a dedicated SSH key (or key per environment) from a secrets manager and inject into the Ansible container; document key rotation and scope in runbooks.

**Sprint 3 (Patch metrics):** The metrics exporter (port 9101) is exposed only on the Docker network; no host publish. Metrics contain no secrets (duration, success/changed flags, timestamp; host labels are inventory hostnames). For production, keep the exporter internal or put it behind a reverse proxy with access control.

---

## 3. Networking

- **Dedicated network:** All monitoring services run on a single Docker network (`monitoring`). Only Prometheus and Grafana need to be exposed to the host; node exporters are scraped by Prometheus over the internal network.
- **Port exposure:**
  - **Prometheus (9090):** Exposed for operator access and Grafana. In production, restrict to VPN, bastion, or private network only.
  - **Grafana (3000):** Exposed for operator access. In production, put behind a reverse proxy (TLS) and restrict access.
  - **Node exporters (9100):** Not exposed to the host; only reachable from Prometheus on the Docker network.
- **Recommendation:** Document which ports are open on each environment. Use firewall rules (e.g. host iptables, cloud security groups) to allow only required IPs (e.g. admin workstations, CI, bastion) to 9090 and 3000. Do not expose monitoring endpoints to the public internet.

---

## 4. Container and image security

- **Version pinning (reproducibility):** Images are pinned to explicit versions in `docker-compose.yml` (e.g. `prom/prometheus:v2.52.0`, `grafana/grafana:10.4.2`, `prom/node-exporter:v1.8.0`) instead of `latest`. This ensures reproducible builds, controlled rollouts, and easier audit. Update versions deliberately and re-test.
- **Recommendation:** Run image scanning in CI (e.g. Trivy, Snyk) and avoid running as root or with unnecessary capabilities.

---

## 5. Prometheus and Grafana hardening

- **Prometheus:** Lifecycle API (`--web.enable-lifecycle`) is enabled for config reloads. Restrict who can call it (e.g. reverse proxy auth or network isolation). In high-security environments, consider disabling it and using restarts for config changes. Healthchecks use the `/-/ready` endpoint for orchestration.
- **Grafana:** Sign-up is disabled (`GF_USERS_ALLOW_SIGN_UP=false`). Anonymous access is disabled (`GF_AUTH_ANONYMOUS_ENABLED=false`). Credentials are set only via environment (no hardcoding). Use strong admin passwords and, in production, enable HTTPS and consider additional auth (e.g. reverse proxy auth, OAuth). Healthchecks use `/api/health` for orchestration and `make validate`.

---

## 6. Data and retention

- **Prometheus:** Retention is set (e.g. 15d) to limit disk use. Ensure volumes are on encrypted storage where required by policy.
- **Grafana:** Provisioning and dashboards are in version-controlled config; no secrets should be stored in dashboard JSON. Store Grafana DB on encrypted storage in production.

---

## 7. Firewall and port exposure summary

| Service         | Port  | Intended exposure                          |
|----------------|-------|--------------------------------------------|
| Prometheus     | 9090  | Operators / Grafana only; restrict by IP   |
| Grafana        | 3000  | Operators only; use TLS in production     |
| Node exporters | 9100  | Internal Docker network only (no host bind)|

Ensure host and/or cloud firewalls align with this. Document any exceptions and review periodically.

**Sprint 1 scope:** Node-exporter metrics in this repository are **container-scoped** (two simulated nodes in Docker). Later sprints will deploy node_exporter to **real Linux nodes** in the data centres; firewall and network design will apply to those targets.
