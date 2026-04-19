.PHONY: up up-sim down logs status clean lint-prometheus validate validate-reports patch patch-dryrun patch-health patch-staging patch-production patch-blue patch-green patch-canary patch-immutable patch-drift patch-report metrics-test

up:
	docker compose up -d prometheus grafana alertmanager

up-sim:
	docker compose --profile sim up -d

down:
	docker compose down

logs:
	docker compose logs -f

status:
	docker compose ps

clean:
	docker compose down -v

lint-prometheus:
	docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
	docker compose exec prometheus promtool check rules /etc/prometheus/alert.rules.yml

validate:
	@echo "=== Validation ==="
	@FAIL=0; \
	RUNNING=$$(docker compose ps --status running -q 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$RUNNING" -ge 3 ]; then \
	  echo "[PASS] Monitoring containers running ($$RUNNING)"; \
	else \
	  echo "[FAIL] Monitoring containers running (expected >=3, got $$RUNNING)"; FAIL=1; \
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
	echo "  - Open http://localhost:9090/targets"; \
	echo "  - Open http://localhost:3000 and confirm Node Overview dashboard"; \
	if [ "$$FAIL" -eq 1 ]; then exit 1; fi

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

patch-staging:
	docker compose exec ansible ansible-playbook -i inventory/staging.ini playbooks/patch_orchestrator.yml -e patch_environment=staging -e patch_group=staging

patch-production:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml -e patch_environment=production -e patch_group=production

patch-blue:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit blue -e patch_environment=production -e patch_group=blue

patch-green:
	docker compose exec ansible ansible-playbook -i inventory/production.ini playbooks/patch_orchestrator.yml --limit green -e patch_environment=production -e patch_group=green

patch-canary:
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml --limit canary -e patch_group=canary
	@echo "Canary passed; running full patch..."
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml

patch-immutable:
	@echo "Recreating patch-target-1 (immutable strategy)..."
	docker compose --profile sim up -d --force-recreate patch-target-1
	@sleep 10
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/patch_orchestrator.yml

patch-drift:
	docker compose exec ansible ansible-playbook -i inventory/hosts.ini playbooks/drift_check.yml

patch-report:
	@docker compose exec ansible sh -c 'if [ -f /ansible/reports/patch_report_latest.json ]; then cat /ansible/reports/patch_report_latest.json; else LATEST=$$(ls -t /ansible/reports/patch_report_*.json 2>/dev/null | head -1); if [ -n "$$LATEST" ]; then cat "$$LATEST"; else echo "No report found. Run: make patch"; fi; fi'

metrics-test:
	@docker compose exec ansible curl -sf http://localhost:9101/metrics || (echo "Metrics exporter not reachable. Is ansible container up?"; exit 1)
