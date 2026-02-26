# Sprint 2 — Testing and validation

How to validate the Ansible patch orchestration (Sprint 2) and what to expect.

---

## 1. Prerequisites

- Docker and Docker Compose (Compose v2).
- Stack up with **sim** profile so Ansible and all 5 patch targets are running.

```bash
docker compose --profile sim up -d
# or
make up-sim
```

Give patch targets a few seconds to pick up the SSH public key from the shared volume (entrypoints wait up to ~30s). Then run the steps below.

---

## 2. Validation sequence

### Step 1: Health check (all hosts reachable)

```bash
make patch-health
```

**Expected:** All 5 hosts return `pong`, show uptime, and report “SSH OK, uptime OK, sshd active”. Any failure here must be fixed before patching (SSH, network, or container state).

### Step 2: Dry run (no changes)

```bash
make patch-dryrun
```

**Expected:** Playbook runs in check mode on all 5 hosts; no actual package or config changes. You may see “would change” or “reboot_required” for some hosts. No failures.

### Step 3: Full patch run

```bash
make patch
```

**Expected:**

- All 5 hosts are updated in parallel (forks=10).
- Output shows tasks running across multiple hosts in the same batch.
- Run completes with a “Patch run complete” summary and path to the report file.
- If any host hits an error, that host gets `patch_failed: true` in the report; others still complete and the report is still written.

### Step 4: Confirm logging and report

- **Log:** Inside the Ansible container, `/ansible/patch.log` should exist and contain logs from the run (append-only). You can inspect with:
  ```bash
  docker compose exec ansible tail -100 /ansible/patch.log
  ```
- **Report:** Latest JSON report:
  ```bash
  make patch-report
  ```
  Or list and read manually:
  ```bash
  docker compose exec ansible ls -la /ansible/reports/
  docker compose exec ansible cat /ansible/reports/patch_report_<epoch>.json
  ```

### Step 5: Concurrency

- Total run time for `make patch` should be clearly less than 5× the time for a single host (e.g. tens of seconds for all 5, not minutes).
- Ansible output (YAML callback) shows multiple hosts in the same task block, indicating parallel execution.

---

## 3. Example patch report (JSON)

After `make patch`, the latest report looks conceptually like:

```json
{
  "hosts": [
    {
      "host": "patch-target-1",
      "changed": true,
      "rebooted": false,
      "failed": false,
      "duration_seconds": 45
    },
    {
      "host": "patch-target-2",
      "changed": false,
      "rebooted": false,
      "failed": false,
      "duration_seconds": 45
    }
  ],
  "duration_seconds": 45
}
```

- **host:** Inventory hostname.
- **changed:** Whether the upgrade task reported changes on that host.
- **rebooted:** Whether a reboot was performed.
- **failed:** Whether the patch block hit the rescue (error) on that host.
- **duration_seconds:** Per-host value is currently the same as the playbook run duration; top-level `duration_seconds` is the total run time.

---

## 4. Failure scenarios

| Scenario            | What to do |
|---------------------|------------|
| `make patch-health` fails (connection/timeout) | Ensure all 5 patch targets are running and on the same Docker network as the Ansible container. Check that the Ansible container has written the public key to the shared volume (restart ansible once if needed). |
| One host fails during `make patch` | That host gets `failed: true` in the report. Fix the host (logs, disk, packages) and re-run; other hosts are already patched. |
| No report file      | Ensure the playbook reached the “Write patch report JSON” task (no earlier fatal failure on all hosts). Check `/ansible/reports/` in the container and that the volume is mounted. |
| patch.log missing   | Confirm `ansible.cfg` is present in the image and `log_path = /ansible/patch.log` is set. Run a simple playbook and check again. |

---

## 5. Monitoring still operational

After Sprint 2, the Sprint 1 stack is unchanged:

- `make validate` still checks Prometheus ready and Grafana health (and container counts: 2, 4, or 11+ for full sim).
- Prometheus and Grafana do not depend on Ansible or patch targets.
- With `--profile sim`, you get both monitoring (Prometheus, Grafana, node exporters) and Ansible + 5 patch targets; all share the monitoring network.

No manual SSH is required for normal operation; key generation and distribution are handled by the container entrypoints and shared volume.
