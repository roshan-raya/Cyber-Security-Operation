# Sprint 2 — Automated Patch Orchestration

Sprint 2 adds Ansible-based patch orchestration: an Ansible control node in Docker and five simulated Linux patch targets (SSH + sudo), all on the monitoring network.

---

## 1. Architecture

```
Ansible control node (container)
    |
    | SSH (key-based, devops user)
    v
5 x Patch target containers (Ubuntu 22.04, openssh-server, sudo, curl)
    |
    v
Prometheus / Grafana (Sprint 1) — monitoring unchanged
```

- **Ansible service:** Built from `ansible/Dockerfile` (Python 3.12 slim, ansible-core, openssh-client). No exposed ports. Mounts playbooks, inventory, and shared SSH volume. Profile: `sim`.
- **Patch targets:** `patch-target-1` … `patch-target-5`. Built from `ansible/target/Dockerfile` (Ubuntu 22.04, openssh-server, sudo, curl, user `devops` with passwordless sudo). Port 22 internal only. Profile: `sim`.
- All services use the same Docker **monitoring** network. No privileged containers.

---

## 2. SSH and credentials

- **Key-based only:** No passwords in the repo. Ansible uses an SSH key; patch targets accept only that key.
- **Key generation:** On first start, the Ansible container entrypoint creates `/ansible/.ssh/id_rsa` (and `.pub`) if missing and copies the public key to the shared volume `/ssh_pubkey`. Patch target entrypoints wait for `id_rsa.pub` on that volume and install it as `devops`’s `authorized_keys`.
- **User:** `devops` on targets; `ansible_user=devops` and `ansible_ssh_private_key_file=/ansible/.ssh/id_rsa` in inventory.
- **Least privilege:** Non-root Ansible image; targets use a non-root user with sudo only as needed. Document production credential handling (e.g. secrets manager, dedicated SSH key per environment) in SECURITY.md or runbooks.

---

## 3. Concurrency (≥5 hosts in parallel)

- **ansible.cfg:** `forks = 10`. Ansible runs up to 10 hosts in parallel, so all 5 patch targets are updated concurrently.
- **Validation:** Run `make patch` and check logs: you should see tasks executing on multiple hosts in the same “batch” and total run time much lower than 5× single-host time. Optionally use `ANSIBLE_DEBUG=1` or verbose output to confirm parallelism.

---

## 4. Playbooks

| Playbook           | Purpose |
|--------------------|--------|
| `playbooks/patch.yml` | Full patch: facts, apt update, safe upgrade, reboot if required, wait, uptime check, JSON report. Block/rescue sets `patch_failed` on error; report is always written. |
| `playbooks/patch_dryrun.yml` | Same flow in **check mode** (no changes). |
| `playbooks/health_check.yml` | Ping, uptime, ensure `ssh` service started. |

Reports are written under `/ansible/reports/` inside the container (backed by volume `ansible_reports`). Use `make patch-report` to print the latest report.

---

## 5. Logging and reporting

- **Log:** `ansible.cfg` sets `log_path = /ansible/patch.log`. All playbook runs append to this file inside the Ansible container.
- **JSON report:** `patch.yml` writes `patch_report_<epoch>.json` with:
  - `hosts`: list of `{ host, changed, rebooted, failed, duration_seconds }` per host
  - `duration_seconds`: total run time for the playbook
- **Structured summary:** Printed at the end of `patch.yml` (path to the report file).

---

## 6. Failure handling

- **Per-host failure:** The main patch block has a `rescue` that sets `patch_failed: true` for that host. Report generation runs anyway and includes `failed: true` for the host.
- **Reboot:** If `/var/run/reboot-required` exists, the playbook reboots the host, waits for connection, re-gathers facts, and validates uptime.
- **Connectivity:** `make patch-health` verifies SSH and sshd before running `make patch`. On failure, fix targets or networking and re-run.

---

## 7. Makefile (Sprint 2)

- `make patch` — run full patch playbook.
- `make patch-dryrun` — run patch in check mode.
- `make patch-health` — run health_check playbook.
- `make patch-report` — print latest `patch_report_*.json` from the Ansible container.

All require the stack to be up with the `sim` profile (`docker compose --profile sim up -d`).

---

## 8. Risk considerations

- **Reboot:** Reboot is automatic when required; targets are unavailable briefly. For production, use maintenance windows and/or serial/rolling updates.
- **Concurrency:** `forks=10` is suitable for 5 targets; for larger fleets, tune and test.
- **Credentials:** Simulation uses a key generated in the Ansible container and shared via volume. Production should use dedicated keys and secret management; document in SECURITY.md.

See **docs/Sprint2_Testing.md** for validation steps and example report output.
