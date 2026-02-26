.PHONY: up down logs status clean validate validate-reports lint-prometheus patch patch-dryrun patch-health patch-report metrics-test patch-staging patch-production patch-blue patch-green patch-canary patch-immutable patch-drift

up:
	docker compose up -d

# Full stack: node exporters + Ansible + patch targets
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
	@echo "=== Validation ==="
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

# Validate reports, compliance >= 95%, SLA duration <= 2h, no failed hosts (run after make patch)
validate-reports:
	docker compose exec ansible sh -lc '\
	echo "=== Report validation ==="; \
	test -f /ansible/reports/patch_report_latest.json || { echo "FAIL: JSON report missing"; exit 1; }; \
	test -f /ansible/reports/patch_report_latest.csv || { echo "FAIL: CSV report missing"; exit 1; }; \
	test -f /ansible/reports/patch_metrics.prom || { echo "FAIL: Metrics file missing"; exit 1; }; \
	COMPLIANCE=$$(jq -r ".compliance_percentage" /ansible/reports/patch_report_latest.json); \
	echo "Compliance: $$COMPLIANCE%"; \
	awk "BEGIN {exit !($$COMPLIANCE >= 95)}" || { echo "FAIL: Compliance below 95%"; exit 1; }; \
	DUR=$$(jq -r ".duration_seconds" /ansible/reports/patch_report_latest.json); \
	echo "Duration: $$DUR s"; \
	awk "BEGIN {exit !($$DUR <= 7200)}" || { echo "FAIL: Duration exceeds 2h SLA"; exit 1; }; \
	grep "\"failed\": true" /ansible/reports/patch_report_latest.json && { echo "FAIL: Some hosts failed"; exit 1; } || echo "No failed hosts"; \
	echo "=== PASS ==="'

# Patch orchestration (requires: docker compose --profile sim up -d)
# ENV=dev|staging|prod selects inventory. LIMIT=blue|green limits to that group (e.g. make patch ENV=prod LIMIT=blue)
patch:
	docker compose exec ansible rm -f /ansible/reports/patch_report_latest.json /ansible/reports/patch_metrics.prom
	docker compose exec ansible sh -c 'ENV='"$(ENV)"'; LIMIT='"$(LIMIT)"'; \
	if [ -n "$$LIMIT" ] && [ -n "$$ENV" ]; then \
	  ansible-playbook -i inventory/$$ENV.ini playbooks/patch_orchestrator.yml --limit $$LIMIT -e patch_environment=$$ENV -e patch_group=$$LIMIT; \
	elif [ -n "$$ENV" ]; then \
	  ansible-playbook -i inventory/$$ENV.ini playbooks/patch_orchestrator.yml -e patch_environment=$$ENV -e patch_group=$$ENV; \
	else \
	  ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml; \
	fi'

patch-dryrun:
	docker compose exec ansible ansible-playbook playbooks/patch_dryrun.yml

patch-health:
	docker compose exec ansible ansible-playbook playbooks/health_check.yml

# Environment separation
patch-staging:
	docker compose exec ansible ansible-playbook -i inventory/staging.ini playbooks/patch_orchestrator.yml -e patch_environment=staging -e patch_group=staging

patch-production:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml -e patch_environment=production -e patch_group=production

# Blue/green production
patch-blue:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit blue -e patch_environment=production -e patch_group=blue

patch-green:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit green -e patch_environment=production -e patch_group=green

# Canary: patch one host first, then all
patch-canary:
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml --limit canary -e patch_group=canary
	@echo "Canary passed; running full patch..."
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml

# Immutable: recreate one node then patch
patch-immutable:
	@echo "Recreating patch-target-1 (immutable strategy)..."
	docker compose --profile sim up -d --force-recreate patch-target-1
	@sleep 10
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml

# Drift detection (report only)
patch-drift:
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/drift_check.yml

patch-report:
	@docker compose exec ansible sh -c 'if [ -f /ansible/reports/patch_report_latest.json ]; then cat /ansible/reports/patch_report_latest.json; else LATEST=$$(ls -t /ansible/reports/patch_report_*.json 2>/dev/null | head -1); if [ -n "$$LATEST" ]; then cat "$$LATEST"; else echo "No report found. Run: make patch"; fi; fi'

# Test patch metrics exporter
metrics-test:
	@docker compose exec ansible curl -sf http://localhost:9101/metrics || (echo "Metrics exporter not reachable. Is ansible container up?"; exit 1)
