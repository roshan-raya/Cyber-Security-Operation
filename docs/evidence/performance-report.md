<<<<<<< HEAD
=======
# Performance Benchmark Report
**Catnip Games International — Patch Management System**
Generated: 2026-04-28T01:34:38Z
Timestamp: 20260428_023201

## Results Summary

| Requirement | Target | Result | Status |
|---|---|---|---|
| Patch window | <= 7200s | 156s | ✅ PASS |
| System backups | Required | 20260428_023437_benchmark-test | ✅ PASS |
| Concurrent updates | >= 5 hosts | 5 hosts | ✅ PASS |
| Monitoring refresh | <= 5 min | 5m global | ✅ PASS |
| Patch success rate | >= 95% | 0.0% | ❌ FAIL |

## Detailed Evidence

### Requirement 1: Patch window
Wall clock: 156s | Reported: 151s | Limit: 7200s

### Requirement 2: System state backups
Backup: 20260428_023437_benchmark-test | Volumes: 0 | Status: success

### Requirement 3: Concurrent updates
Hosts patched: 5 | Strategy: #Whytwoplays:strategy:freerunspatchesconcurrentlyacrosshosts;reportingmustrunonceafter

### Requirement 4: Monitoring refresh rate
Global: 5m | Patch metrics: 15s | Limit: 5m

### Requirement 5: Patch success rate
Compliance: 0.0% | Limit: >= 95%

## Test Configuration
- Hosts tested: 5
- Ansible strategy: free (all hosts in parallel)
- Prometheus scrape interval: 5m
- Test environment: Docker Compose sim profile
>>>>>>> e13e633 (performance-report)
