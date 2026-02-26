# Sprint 1 — Architecture

Architecture and design for the Sprint 1 monitoring baseline: Prometheus, Grafana, and simulated node exporters, all run via Docker Compose.

---

## 1. Goals

- Provide a **reproducible**, Docker-based monitoring stack.
- Scrape **self-monitoring** (Prometheus) and **two simulated game nodes** (node_exporter).
- Pre-provision **Grafana** with a Prometheus datasource and one dashboard (Node Overview).
- Align with **Infrastructure-as-Code**: version-controlled config, no manual setup.
- Establish patterns for **security** (least privilege, dedicated network, no hardcoded secrets).

---

## 2. High-level architecture

```
                    +------------------+
                    |     Operator     |
                    |  (browser/curl)  |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                                       |
         v                                       v
+----------------+                    +----------------+
|   Prometheus   |                    |    Grafana     |
|   :9090        |<--- scrape --------|    :3000       |
+--------+-------+                    +----------------+
         |                                       ^
         | scrape                                 | query
         v                                       |
+----------------+                    +----------------+
| node-exporter-1|  node-exporter-2   |  (Prometheus   |
| :9100          |  :9100             |   as DS)       |
+----------------+--------------------+----------------+
         |
         |  (simulated game nodes; same host metrics)
         v
    [ Host /proc, /sys, / ]
```

- **Prometheus** scrapes itself and both node exporters on a **5-minute** interval (configurable; see `prometheus/prometheus.yml`).
- **Grafana** uses Prometheus as the only provisioned datasource and displays the **Node Overview** dashboard (up, CPU, memory).
- All services run on a single **Docker network** (`monitoring`). Only Prometheus (9090) and Grafana (3000) are bound to the host.

---

## 3. Components

| Component       | Image               | Role                                      | Port (host) |
|----------------|---------------------|-------------------------------------------|-------------|
| Prometheus     | prom/prometheus     | Scrape and store metrics; evaluate rules  | 9090        |
| Grafana        | grafana/grafana     | Visualisation; pre-provisioned DS + dashboard | 3000    |
| node-exporter-1| prom/node-exporter  | Simulated node 1 metrics                 | —           |
| node-exporter-2| prom/node-exporter  | Simulated node 2 metrics                  | —           |

Node exporters are not published to the host; they are reached by Prometheus via Docker DNS (`node-exporter-1:9100`, `node-exporter-2:9100`).

---

## 4. Configuration layout

- **Prometheus**
  - `prometheus/prometheus.yml`: global scrape/eval intervals, `rule_files`, scrape configs for `prometheus` and `node-exporter` jobs.
  - `prometheus/alert.rules.yml`: rule file; currently empty group with commented example (e.g. InstanceDown).
- **Grafana**
  - `grafana/provisioning/datasources/datasource.yml`: Prometheus datasource (uid: `prometheus`).
  - `grafana/provisioning/dashboards/dashboards.yml`: file provider for dashboards.
  - `grafana/provisioning/dashboards/node-overview.json`: Node Overview dashboard (up, CPU %, memory %).

Scrape interval is set to **5 minutes** for requirement alignment; a comment in `prometheus.yml` explains how to temporarily reduce it for testing.

---

## 5. Data flow

1. Prometheus scrapes `http://localhost:9090/metrics`, `http://node-exporter-1:9100/metrics`, `http://node-exporter-2:9100/metrics` every 5m.
2. Alert rules (when added) are evaluated at `evaluation_interval` (5m).
3. Grafana sends PromQL queries to Prometheus (proxy mode) when dashboards are viewed.
4. Node Overview dashboard shows: **Targets Up** (`up`), **CPU Usage %** (derived from `node_cpu_seconds_total`), **Memory Usage %** (derived from `node_memory_*`).

---

## 6. Security design (summary)

- **Least privilege:** Non-root users; read-only root filesystem where possible; no privileged containers.
- **Secrets:** Grafana admin from env (e.g. `.env`); no secrets in repo.
- **Network:** Single Docker network; only Prometheus and Grafana ports exposed; node exporters internal only.
- **Details:** See **SECURITY.md**.

---

## 7. Future alignment (Sprint 2+)

- **Ansible:** `ansible/playbooks` and `ansible/inventory` are placeholders for deploying node_exporter (and later patching) to real Linux hosts.
- **Alerting:** Add receivers and routing in Prometheus; enable Alertmanager when needed.
- **Multi-datacenter:** Separate scrape configs or federations; use labels (e.g. `datacenter: dc1`) already present on node-exporter targets as a pattern.

This document should be updated when new components (e.g. Alertmanager, more dashboards, Ansible roles) are introduced.
