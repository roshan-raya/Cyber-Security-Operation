# Anjali Individual Contribution

## Role
Grafana Dashboard, Metrics Bridge and Project Coordination.

## My Responsibilities
My role focused on making patch management results visible and understandable through monitoring dashboards.

## Work Completed
- Created and managed Grafana dashboards for system health and patch monitoring.
- Helped integrate patch metrics from Ansible into Prometheus and Grafana.
- Worked on dashboard visibility for patch success, compliance, duration and failed hosts.
- Supported project documentation, demo preparation and repository organisation.

## Evidence
- Grafana dashboards:
  - Node Overview
  - Patch Management SLO
  - Patch Management Node Overview
- Prometheus targets page showing patch_metrics as UP.
- Dashboard panels showing patch success rate, compliance and failed hosts.

## System Flow
Ansible generates patch results → metrics exporter exposes them → Prometheus collects them → Grafana visualises them.

## Reflection
This work helped me understand how monitoring tools are used in cybersecurity operations to verify system health, detect failures and support security compliance.


## Dashboard Explanation

The Grafana dashboards were used to visualise system health and patching results.

- Node Overview: Shows system status, CPU, memory and service availability.
- Patch Management SLO: Shows patch compliance, duration and success trends.
- Patch Management Node Overview: Shows patch results per host.

These dashboards allow quick identification of failures and system performance issues.

## Evidence of Work

- Grafana dashboards show:
  - Patch success rate = 100%
  - Patch compliance = 100%
  - Failed hosts = 0

- Prometheus targets show:
  - patch_metrics = UP
  - node-exporter = UP
  - alertmanager = UP

This confirms that the monitoring pipeline is working correctly and displaying real-time data.