# Grafana Dashboard Guide — Anjali

## Purpose
This guide explains the Grafana dashboards used in the automated patch management project.

## Dashboard 1: Node Overview
This dashboard shows system health and patch monitoring.

Key panels:
- Targets Up: shows whether monitored services are reachable
- CPU Usage: shows system processing load
- Memory Usage: shows memory usage
- Patch Run Duration: shows how long patching took
- Patch Success Rate: shows whether patching succeeded
- Patch Compliance: shows whether systems meet patching requirements
- Failed Hosts Count: shows if any host failed
- Per-host Patch Success: shows patch result for each machine

## Dashboard 2: Patch Management SLO
This dashboard focuses on service-level objectives.

It helps check:
- compliance target
- patch duration
- active alerts
- patch success trends

## Dashboard 3: Patch Management Node Overview
This dashboard gives detailed patch results per host and environment.

It helps identify:
- which host succeeded
- which host failed
- blue and green patch success
- system resource stability

## How to Interpret the Dashboard
A healthy patching result should show:
- patch success rate = 100%
- compliance above 95%
- failed hosts = 0
- patch_metrics target = UP in Prometheus

If failed hosts are greater than 0, or patch_metrics is down, the system needs investigation.

## My Contribution
My contribution was to make patching results visible through dashboards so the team can verify patch success and system health without manually checking raw logs.