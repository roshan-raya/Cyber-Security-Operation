.PHONY: up down logs status clean validate lint-prometheus patch patch-dryrun patch-health patch-report metrics-test patch-staging patch-production patch-blue patch-green

up:
	docker compose up -d

# Full stack including simulated node exporters + Ansible + patch targets (Sprint 2)
up-sim:
	docker compose --profile sim up -d

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps

clean: down
	docker compose down -v

# Lint Prometheus config and rule files (run with stack up, or use: docker compose run --rm prometheus promtool ...)
lint-prometheus:
	docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
	docker compose exec prometheus promtool check rules /etc/prometheus/alert.rules.yml

validate:
	@echo "=== Sprint 1.1 Validation ==="
	@FAIL=0; \
	RUNNING=$$(docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$RUNNING" -eq 2 ]; then \
	  echo "[PASS] Containers running (2/2 monitoring only)"; \
	elif [ "$$RUNNING" -eq 4 ]; then \
	  echo "[PASS] Containers running (4/4 with sim)"; \
	elif [ "$$RUNNING" -ge 12 ]; then \
	  echo "[PASS] Containers running ($$RUNNING - full sim + Alertmanager)"; \
	elif [ "$$RUNNING" -ge 11 ]; then \
	  echo "[PASS] Containers running ($$RUNNING - full sim with Ansible + patch targets)"; \
	else \
	  echo "[FAIL] Containers running (expected 2, 4, or 11+, got $$RUNNING)"; FAIL=1; \
	fi; \
	if curl -sf -o /dev/null http://localhost:9090/-/ready 2>/dev/null; then \
	  echo "[PASS] Prometheus ready endpoint returns 200"; \
	else \
	  echo "[FAIL] Prometheus ready endpoint (http://localhost:9090/-/ready) did not return 200"; FAIL=1; \
	fi; \
	if curl -sf -o /dev/null http://localhost:3000/api/health 2>/dev/null; then \
	  echo "[PASS] Grafana health returns 200"; \
	else \
	  echo "[FAIL] Grafana health (http://localhost:3000/api/health) did not return 200"; FAIL=1; \
	fi; \
	echo "=== Manual checks ==="; \
	echo "  - Open http://localhost:9090/targets (expect 3 targets UP)"; \
	echo "  - Open http://localhost:3000 and login with .env credentials"; \
	echo "  - Open Node Overview dashboard and confirm metrics after scrape interval"; \
	if [ "$$FAIL" -eq 1 ]; then exit 1; fi

# Sprint 2/4: Ansible patch orchestration (requires: docker compose --profile sim up -d)
# Default: all targets from inventory/hosts.ini (Sprint 2 backward compatible)
# Clear stale report artifacts before run so a failed playbook doesn't show old success output
patch:
	docker compose exec ansible rm -f /ansible/reports/patch_report_latest.json /ansible/reports/patch_metrics.prom
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml

patch-dryrun:
	docker compose exec ansible ansible-playbook playbooks/patch_dryrun.yml

patch-health:
	docker compose exec ansible ansible-playbook playbooks/health_check.yml

# Sprint 4: environment separation
patch-staging:
	docker compose exec ansible ansible-playbook -i inventory/staging.ini playbooks/patch_orchestrator.yml -e patch_environment=staging -e patch_group=staging

patch-production:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml -e patch_environment=production -e patch_group=production

# Sprint 4: blue/green production
patch-blue:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit blue -e patch_environment=production -e patch_group=blue

patch-green:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit green -e patch_environment=production -e patch_group=green

patch-report:
	@docker compose exec ansible sh -c 'if [ -f /ansible/reports/patch_report_latest.json ]; then cat /ansible/reports/patch_report_latest.json; else LATEST=$$(ls -t /ansible/reports/patch_report_*.json 2>/dev/null | head -1); if [ -n "$$LATEST" ]; then cat "$$LATEST"; else echo "No report found. Run: make patch"; fi; fi'

# Sprint 3: test patch metrics exporter (requires: docker compose --profile sim up -d)
metrics-test:
	@docker compose exec ansible curl -sf http://localhost:9101/metrics || (echo "Metrics exporter not reachable. Is ansible container up?"; exit 1)
