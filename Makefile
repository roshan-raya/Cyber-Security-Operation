.PHONY: up down logs status clean validate validate-reports health-check lint-prometheus patch patch-dryrun patch-health patch-report metrics-test patch-staging patch-production patch-blue patch-green patch-canary patch-immutable patch-drift thehive-up thehive-init thehive-init-force thehive-rekey thehive-canonicalize-templates thehive-templates thehive-setup thehive-status thehive-logs misp-up misp-status misp-init misp-feeds misp-verify misp-reset-login-lockout misp-integration-test misp-setup misp-logs cortex-up cortex-status cortex-init cortex-analysers cortex-connect-thehive cortex-verify cortex-setup cortex-logs ingest-alerts ingest-alerts-dry enrich-alerts export-iocs kpi-report kpi-prometheus kpi-server kpi-server-stop check-escalations check-escalations-dry start-logs start-logs-fast start-logs-no-integrations stop-logs logs-status logs-summary view-logs view-ids-logs view-firewall-logs watch-metrics watch-metrics-catnip git-hooks

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

# Alias for stack / endpoint health (same as validate)
health-check: validate

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

thehive-up:
	docker compose up -d cassandra thehive
	@echo "Waiting for TheHive to start (this takes ~2 minutes)..."
	@sleep 120

thehive-init:
	python3 thehive/setup/init_thehive.py

thehive-init-force:
	python3 thehive/setup/init_thehive.py --force

thehive-rekey:
	python3 thehive/setup/init_thehive.py --rekey-only

thehive-canonicalize-templates:
	python3 thehive/setup/canonicalize_templates.py

thehive-templates:
	python3 thehive/setup/import_templates.py

thehive-setup: thehive-up thehive-init thehive-templates
	@echo "TheHive setup complete. Access at http://localhost:9000"

thehive-status:
	@code=$$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/api/v1/status); \
	if [ "$$code" = "200" ] || [ "$$code" = "401" ]; then \
	  echo "{ \"status\": \"reachable\", \"http_code\": $$code, \"endpoint\": \"/api/v1/status\" }" | python3 -m json.tool; \
	else \
	  echo "TheHive not reachable"; \
	fi

thehive-logs:
	docker compose logs -f thehive cassandra

misp-up:
	docker compose up -d misp-db misp-redis misp-modules misp
	@echo "Waiting for MISP to initialise (this takes 3-5 minutes)..."
	@sleep 180

misp-status:
	@curl -sf -o /dev/null -w "%{http_code}" http://localhost:8080/users/login \
	  && echo " MISP reachable at http://localhost:8080" \
	  || echo "MISP not reachable"

misp-init:
	python3 misp/setup/init_misp.py

misp-feeds:
	python3 misp/setup/configure_feeds.py

misp-verify:
	python3 misp/setup/verify_misp.py

# Clears MISP brute-force / login throttling (MySQL table bruteforces). Use after "maximum login attempts" lockout.
misp-reset-login-lockout:
	@docker compose exec -T misp-db sh -c 'mysql -umisp -p"$$MYSQL_PASSWORD" misp -e "DELETE FROM bruteforces;"'
	@echo "MISP login lockout cleared (bruteforces table emptied)."

misp-integration-test:
	python3 misp/setup/misp_thehive_integration.py

misp-setup: misp-up misp-init misp-feeds misp-verify
	@echo "MISP setup complete. Access at http://localhost:8080"

misp-logs:
	docker compose logs -f misp misp-db misp-redis

cortex-up:
	docker compose up -d cortex-db cortex
	@echo "Waiting for Cortex to start (this takes ~2 minutes)..."
	@sleep 120

cortex-status:
	@curl -sf http://localhost:9001/api/status \
	  && echo "Cortex reachable at http://localhost:9001" \
	  || echo "Cortex not reachable"

cortex-init:
	python3 cortex/setup/init_cortex.py

cortex-analysers:
	python3 cortex/setup/configure_analysers.py

cortex-connect-thehive:
	@KEY=$$(cat cortex/setup/cortex_api_key.txt 2>/dev/null | tr -d '\r\n'); \
	if [ -z "$$KEY" ]; then echo "Missing cortex/setup/cortex_api_key.txt (run make cortex-init)"; exit 1; fi; \
	export CORTEX_API_KEY=$$KEY; \
	docker compose up -d --force-recreate thehive && \
	THEHIVE_URL=$${THEHIVE_URL:-http://localhost:9000} CORTEX_URL=$${CORTEX_URL:-http://localhost:9001} python3 cortex/setup/connect_thehive.py

cortex-verify:
	@THIVE_CODE=$$(curl -s -o /dev/null -w "%{http_code}" -m 5 $${THEHIVE_URL:-http://localhost:9000}/api/v1/status 2>/dev/null || echo 000); \
	if [ "$$THIVE_CODE" = "200" ] || [ "$$THIVE_CODE" = "401" ]; then \
	  THEHIVE_URL=$${THEHIVE_URL:-http://localhost:9000} CORTEX_URL=$${CORTEX_URL:-http://localhost:9001} python3 cortex/setup/verify_cortex.py; \
	else \
	  net=$$(docker inspect -f '{{range $$k, $$v := .NetworkSettings.Networks}}{{$$k}}{{end}}' thehive 2>/dev/null); \
	  if [ -z "$$net" ]; then echo "TheHive not reachable (HTTP $$THIVE_CODE) and thehive container not found."; exit 1; fi; \
	  docker run --rm --network "$$net" -v "$$PWD:/work" -w /work \
	    -e CORTEX_URL=http://cortex:9001 -e THEHIVE_URL=http://thehive:9000 \
	    python:3.12-slim bash -c "pip install -q requests && python3 cortex/setup/verify_cortex.py"; \
	fi

cortex-setup: cortex-up cortex-init cortex-analysers cortex-connect-thehive cortex-verify
	@echo "Cortex setup complete. Access at http://localhost:9001"

cortex-logs:
	docker compose logs -f cortex cortex-db

ingest-alerts:
	python3 cortex/automation/alert_ingestor.py

ingest-alerts-dry:
	python3 cortex/automation/alert_ingestor.py --dry-run

enrich-alerts:
	python3 cortex/automation/alert_enricher.py

export-iocs:
	python3 cortex/automation/misp_exporter.py

kpi-report:
	python3 cortex/automation/kpi_tracker.py --output both --save

kpi-prometheus:
	python3 cortex/automation/kpi_tracker.py --output prometheus

kpi-server:
	python3 cortex/automation/kpi_metrics_server.py &
	@echo "KPI metrics server started on port 9102"

kpi-server-stop:
	@pkill -f kpi_metrics_server.py || echo "Server not running"

check-escalations:
	python3 cortex/automation/escalation_manager.py

check-escalations-dry:
	python3 cortex/automation/escalation_manager.py --dry-run

start-logs:
	python3 log_generator/orchestrator.py &
	@echo "Log generator started. Metrics on port 9104"

start-logs-fast:
	python3 log_generator/orchestrator.py --rate fast &
	@echo "Log generator started (fast mode)"

start-logs-no-integrations:
	python3 log_generator/orchestrator.py --no-thehive --no-misp &
	@echo "Log generator started (no integrations)"

stop-logs:
	@pkill -f "log_generator/orchestrator.py" || echo "Not running"
	@pkill -f "log_generator/generator.py" || echo "Not running"

logs-status:
	@curl -s http://localhost:9104/health || echo "Log generator not running"

logs-summary:
	@cat log_generator/state/metrics.json 2>/dev/null \
	  | python3 -m json.tool || echo "No metrics yet. Run: make start-logs"

view-logs:
	@tail -f log_generator/logs/combined.log

view-ids-logs:
	@tail -f log_generator/logs/ids_alert.log

view-firewall-logs:
	@tail -f log_generator/logs/firewall_block.log

# macOS has no `watch` by default; use this instead of: watch -n 5 'curl ... | grep ...'
watch-metrics:
	@while true; do \
		clear; \
		echo "=== $$(date '+%Y-%m-%d %H:%M:%S') — log_generator /metrics (Ctrl+C) ==="; \
		curl -s http://localhost:9104/metrics \
			| grep -E 'catnip_log_events_total|catnip_thehive_cases|catnip_misp_iocs' \
			|| echo "(no matching lines — is make start-logs running?)"; \
		sleep 5; \
	done

watch-metrics-catnip:
	@while true; do \
		clear; \
		echo "=== $$(date '+%Y-%m-%d %H:%M:%S') — all catnip_* (Ctrl+C) ==="; \
		curl -s http://localhost:9104/metrics | grep catnip \
			|| echo "(no catnip_* lines — is make start-logs running?)"; \
		sleep 5; \
	done

# One-time per clone: use repo hooks (strips Made-with: Cursor from commit messages).
git-hooks:
	git config core.hooksPath .githooks
	@chmod +x .githooks/commit-msg 2>/dev/null || true
	@echo "core.hooksPath=.githooks (commit-msg strips Cursor attribution)"
