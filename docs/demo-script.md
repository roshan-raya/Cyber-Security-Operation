**Catnip Games International — Patch Management System**

---

## Pre-demo checklist (10 minutes before assessment)

Run these commands and confirm all pass before the assessor arrives:

```bash
docker compose --profile sim up -d
sleep 30
make validate
make patch-health
```

Browser tabs to have open:
- http://localhost:9090 (Prometheus)
- http://localhost:9090/targets
- http://localhost:9090/alerts
- http://localhost:3000 (Grafana)
- https://webhook.site/YOUR-UUID (for alert demo)
- Terminal at project root

---

## Demo Sequence (~12 minutes total)

### Part 1 — Architecture overview (2 minutes)

Open `docs/technical-architecture.md` and walk through the ASCII diagram.

Say: "Catnip Games manages 300 Linux servers across two data centres. This system
automates patch deployment using Ansible for orchestration, Prometheus for metrics,
and Grafana for visibility. Everything here is reproducible — one command starts
a full 5-node simulation."

Point out:
- The CI/CD pipeline enforcing 95% compliance as a hard gate
- The two-play structure: patching (parallel) then reporting (localhost)
- Port 9101 for patch metrics from the Ansible container to Prometheus

---

### Part 2 — Live patch deployment (3 minutes)

```bash
make patch
```

While it runs, explain what each role does:
- `common` — records start time so duration is accurate
- `health_check` — confirms SSH and uptime before touching packages
- `patch` — apt update, safe upgrade, reboot if /var/run/reboot-required exists
- `reporting` — writes JSON, CSV, and .prom files on localhost

After completion:
```bash
make validate-reports
```

Point to compliance_percentage and duration_seconds in the output.

---

### Part 3 — Monitoring and alerting (3 minutes)

```bash
# Show live metric values
curl -s "http://localhost:9090/api/v1/query?query=patch_compliance_percentage" \
  | python3 -m json.tool

curl -s "http://localhost:9090/api/v1/query?query=patch_scan_critical_cves" \
  | python3 -m json.tool
```

Open http://localhost:9090/targets — show all scrape targets UP.
Open http://localhost:3000 — navigate to Dashboards → Patch Management SLO.

Walk through the SLO dashboard panels:
- Compliance gauge (green = above 95% SLO)
- Duration stat (green = under 2-hour SLO)
- Per-host success row (all green = all hosts healthy)
- Firing alerts count (0 = system healthy)

---

### Part 4 — Trigger a real alert (2 minutes)

```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  -e fail_host=patch-target-1 \
  -e rollback_enabled=false
```

Say: "I'm using the built-in failure simulation flag to drop compliance to 80%.
Prometheus evaluates alert rules every minute."

```bash
sleep 90
```

Open http://localhost:9090/alerts — show PatchComplianceBelow95 firing.
Open webhook.site — show the critical alert POST arriving.

---

### Part 5 — Rollback demonstration (2 minutes)

```bash
docker compose exec ansible \
  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml \
  --limit patch-target-1 \
  -e rollback_enabled=true \
  -e fail_host=patch-target-1
```

Point out: "The rescue block captures the failure, loads rollback.yml, and reinstalls
packages from the snapshot taken at the start of the run — before any changes were
made. The guard clause in rollback.yml prevents it from running blind if the snapshot
was never captured."

---

### Part 6 — Backup demonstration (1 minute)

```bash
make backup LABEL=demo
cat backups/*/manifest.json
```

Point out SHA256 checksums, volume names, and status: success in the manifest.

---

## Q&A preparation

**Q: What does your SLO dashboard show?**
"The SLO dashboard has four summary panels at the top: compliance percentage against
the 95% SLO, last patch result, duration against the 2-hour SLO, and firing alert
count. Below that are time-series trend panels showing compliance and duration over
time so you can see if the system is degrading. The bottom row shows per-host success
as a colour-coded status grid — red means that host failed its last patch."

**Q: Why did you add a phased rollout?**
"The original patch_orchestrator uses strategy: free which patches all hosts in
parallel. In production that means a bad package could take down all 300 servers
simultaneously. The canary playbook adds serial batching with max_fail_percentage
thresholds — if the first host fails, the run halts before touching anyone else.
This is how real production patching works at scale."

**Q: What does Ansible Vault add?**
"It encrypts sensitive values — Grafana passwords, API keys — so they can be
committed to the repository as ciphertext. Without Vault, secrets live in .env
files which get committed by mistake more often than you'd think. The ciphertext
is useless without the vault password, which is never committed."

**Q: How do you prove resilience and performance SLOs?**
"We ship `make chaos-test` for three failure injections with evidence under
`docs/evidence/chaos/`, and `make benchmark` which re-runs a full patch, checks
backups and Prometheus scrape config, and writes `docs/evidence/performance-report.md`."

---

## Optional — Sprint 3 verification (before assessment)

With the stack running:

```bash
make benchmark
make chaos-test-1
make chaos-test-2
make chaos-test-3
```

See [docs/chaos-testing.md](chaos-testing.md) and TC-015–TC-017 in [docs/test-cases.md](test-cases.md).
