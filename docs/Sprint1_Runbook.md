# Sprint 1 — Runbook

Operational runbook for the Sprint 1 monitoring stack: startup, validation, common operations, and troubleshooting.

---

## 1. Prerequisites

- Docker and Docker Compose (Compose V2: `docker compose`) installed.
- Ports **3000** and **9090** free on the host.
- `.env` created from `.env.example` with Grafana admin credentials set.

---

## 2. Startup

```bash
# From project root
cp .env.example .env   # if not already done; edit .env with secure password
docker compose up -d              # monitoring only (Prometheus + Grafana)
# or with simulated node exporters (Sprint 1 full stack):
docker compose --profile sim up -d
# or
make up
make up-sim   # full stack with sim nodes
```

Check that all containers are running:

```bash
docker compose ps
# or
make status
```

Expected: **Without** `--profile sim`: `prometheus`, `grafana` (2 containers). **With** `--profile sim`: `prometheus`, `grafana`, `node-exporter-1`, `node-exporter-2` (4 containers). After healthchecks pass, Prometheus and Grafana show as `healthy` in `docker compose ps`.

---

## 3. Health & Readiness Checks

- **Prometheus:** Healthcheck hits `http://localhost:9090/-/ready` every 10s (timeout 5s, 3 retries, 5s start period). Container is marked healthy when the endpoint returns 200.
- **Grafana:** Healthcheck hits `http://localhost:3000/api/health` every 10s (timeout 5s, 3 retries, 15s start period). Container is marked healthy when the endpoint returns 200.
- **Startup order:** Grafana `depends_on` Prometheus with `condition: service_healthy`, so Grafana only starts after Prometheus is healthy.
- **Automated validation:** Run `make validate` to verify (1) containers running (2 = monitoring only, 4 = with sim), (2) Prometheus ready returns 200, (3) Grafana health returns 200. Output is explicit `[PASS]` / `[FAIL]` per check. Container count uses `docker compose ps --status running -q` for accuracy.

---

## 4. Validation (sanity check)

| Step | Command / action | Expected |
|------|------------------|----------|
| 1 | `curl -s http://localhost:9090/-/ready` | HTTP 200 |
| 2 | Open http://localhost:9090/targets | 3 targets (prometheus, node-exporter ×2), all UP |
| 3 | Open http://localhost:3000 | Grafana login page |
| 4 | Login with `.env` credentials | Grafana home |
| 5 | Dashboards → Node Overview | Dashboard with Targets Up, CPU %, Memory % (may need 1–2 scrape cycles) |

Full validation steps are also in **README.md**.

### Verify targets and dashboard after scrape interval

- Default scrape interval is **5 minutes**. After startup:
  1. Open http://localhost:9090/targets and confirm all 3 targets are **UP** (prometheus, node-exporter-1, node-exporter-2).
  2. Wait at least one full scrape interval (e.g. 5 minutes), then open Grafana → **Node Overview** dashboard.
  3. Confirm **Targets Up** shows values for all three; **CPU Usage %** and **Memory Usage %** show time series (may take 1–2 scrape cycles to fill). If panels are empty, re-check targets and wait another interval.

---

## 5. Common operations

### View logs

```bash
docker compose logs -f
# or
make logs
```

Per service:

```bash
docker compose logs -f prometheus
docker compose logs -f grafana
```

### Stop the stack

```bash
docker compose down
# or
make down
```

### Stop and remove volumes (clean slate)

```bash
make clean
# or
docker compose down -v
```

### Lint Prometheus config and rules

```bash
make lint-prometheus
# or
docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec prometheus promtool check rules /etc/prometheus/alert.rules.yml
```

Requires the stack to be up (at least Prometheus running).

### Reload Prometheus config (no restart)

```bash
curl -X POST http://localhost:9090/-/reload
```

Only works if Prometheus was started with `--web.enable-lifecycle` (as in this stack).

### Restart a single service

```bash
docker compose restart prometheus
docker compose restart grafana
```

---

## 6. Troubleshooting

### Containers exit or fail to start

- Run `docker compose logs` for the failing service.
- Check port conflicts: `lsof -i :9090` and `lsof -i :3000` (or equivalent).
- Ensure `prometheus/prometheus.yml` and `prometheus/alert.rules.yml` exist and are valid YAML.
- Ensure `grafana/provisioning` structure and YAML/JSON are valid.

### Prometheus targets down

- Confirm all containers are on the same network:  
  `docker network inspect $(docker compose ps -q prometheus | xargs docker inspect -f '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}')`
- From inside the prometheus container:  
  `docker compose exec prometheus wget -qO- http://node-exporter-1:9100/metrics | head`
- Ensure no typos in service names in `prometheus.yml` (`node-exporter-1`, `node-exporter-2`).

### Grafana login fails

- Verify `.env` exists and contains `GF_SECURITY_ADMIN_USER` and `GF_SECURITY_ADMIN_PASSWORD`.
- Restart Grafana after changing `.env`: `docker compose up -d grafana`.

### Dashboard shows “No data”

- Confirm all 3 targets are UP at http://localhost:9090/targets.
- Default scrape interval is **5 minutes**; wait at least one full interval or temporarily lower `scrape_interval` in `prometheus/prometheus.yml` for testing (see README).
- In Grafana → Explore, choose Prometheus and run `up`; you should see series. If not, check Grafana datasource URL (should be `http://prometheus:9090`).

### Alert rules not loading

- Check syntax of `prometheus/alert.rules.yml` (valid YAML, correct group structure).
- Check Prometheus logs for “error loading rules” or “invalid rule”.
- Reload config: `curl -X POST http://localhost:9090/-/reload`.

---

## 7. File and path reference

| Purpose | Path |
|--------|------|
| Compose definition | `docker-compose.yml` |
| Prometheus config | `prometheus/prometheus.yml` |
| Alert rules | `prometheus/alert.rules.yml` |
| Grafana datasource | `grafana/provisioning/datasources/datasource.yml` |
| Dashboard provisioning | `grafana/provisioning/dashboards/dashboards.yml` |
| Node Overview dashboard | `grafana/provisioning/dashboards/node-overview.json` |
| Env template | `.env.example` |
| Env (local, git-ignored) | `.env` |

---

## 8. Escalation and docs

- **Architecture:** docs/Sprint1_Architecture.md  
- **Security:** SECURITY.md  
- **User-facing run/validate/troubleshoot:** README.md  

For production, extend this runbook with alerting contacts, backup/restore of Prometheus/Grafana data, and change-management procedures.
