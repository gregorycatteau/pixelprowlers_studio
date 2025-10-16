ENV_FILE ?= backend/.env.dev
DATABASE_URL ?= postgresql://striker_dev:Theokdiopa@localhost:5432/pxp_dev?sslmode=disable
REDIS_URL ?= redis://localhost:6379/0

ifeq ($(strip $(DATABASE_URL)),)
DATABASE_URL := postgresql://striker_dev:Theokdiopa@localhost:5432/pxp_dev?sslmode=disable
endif
ifeq ($(strip $(REDIS_URL)),)
REDIS_URL := redis://localhost:6379/0
endif

.PHONY: dev-env redis-up dev-check migrate import-agents init-dev run-back run-front dev smoke

dev-env:
	@echo "APP_ENV=dev" > $(ENV_FILE)
	@echo "DJANGO_DEBUG=true" >> $(ENV_FILE)
	@echo "DJANGO_SECRET_KEY=dev-secret-change-me" >> $(ENV_FILE)
	@echo "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1" >> $(ENV_FILE)
	@echo "DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000" >> $(ENV_FILE)
	@echo "CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000" >> $(ENV_FILE)
	@echo "DATABASE_URL=$(DATABASE_URL)" >> $(ENV_FILE)
	@echo "REDIS_URL=$(REDIS_URL)" >> $(ENV_FILE)
	@echo "DJANGO_LOG_LEVEL=DEBUG" >> $(ENV_FILE)
	@echo "SECURE_SSL_REDIRECT=0" >> $(ENV_FILE)
	@echo "NUXT_PUBLIC_APP_ENV=dev" >> $(ENV_FILE)
	@echo "OK: backend/.env.dev écrit"

redis-up:
	@if command -v redis-server >/dev/null 2>&1; then \
		echo "redis-server détecté localement"; \
	elif command -v docker >/dev/null 2>&1; then \
		if docker ps --format '{{.Names}}' | grep -q '^pxp_dev_redis$$'; then \
			echo "redis docker déjà actif"; \
		else \
			docker run --name pxp_dev_redis -p 6379:6379 -d redis:7-alpine; \
		fi; \
	else \
		echo "redis-server indisponible et docker absent → démarre ton propre Redis"; \
		exit 1; \
	fi

dev-check:
	./scripts/dev-check.sh

migrate:
	cd backend && APP_ENV=dev poetry run python manage.py migrate --noinput

import-agents:
	cd backend && APP_ENV=dev poetry run python manage.py import_agents --path backend/agents_v21

init-dev:
	cd backend && APP_ENV=dev poetry run python manage.py init_dev_env

run-back:
	cd backend && APP_ENV=dev poetry run python manage.py runserver 0.0.0.0:8000

run-front:
	cd frontend && npm run dev

dev:
	$(MAKE) redis-up
	$(MAKE) dev-check
	$(MAKE) init-dev
	( $(MAKE) run-back & )
	( cd frontend && npm run dev )

smoke:
	cd docs/auth && BASE_URL=$${BASE_URL:-http://localhost:8000} bash smoke-dojo.http

# ──────────────────────────────────────────────────────────────────────────────
# E2E Playwright targets (test env separation)
#  - Frontend test port: 3100
#  - Backend test port: 8100
#  - By default, Playwright webServer will spawn these via npm scripts
#  - Set PW_SKIP_WEBSERVER=1 to attach to already running services
# ──────────────────────────────────────────────────────────────────────────────
PW_BASE_URL ?= http://127.0.0.1:3100
PW_BACKEND_HEALTH_URL ?= http://127.0.0.1:8100/ready/

.PHONY: test-e2e pw-report pw-open-report pw-clean pw-docker-run test-env-up test-env-down pw-doctor

test-e2e:
	cd frontend && PPW_BASE_URL=$(PW_BASE_URL) PPW_BACKEND_HEALTH_URL=$(PW_BACKEND_HEALTH_URL) npx playwright test

pw-report:
	cd frontend && npx playwright show-report

pw-open-report: pw-report

pw-clean:
	rm -rf frontend/playwright-report frontend/test-results frontend/reports frontend/blob-report || true

# Run E2E inside official Playwright container (recommended on Kali)
pw-docker-run:
	PPW_BASE_URL=$(PW_BASE_URL) PPW_BACKEND_HEALTH_URL=$(PW_BACKEND_HEALTH_URL) docker compose -f docker-compose.playwright.yml run --rm \
		-e PPW_BASE_URL -e PPW_BACKEND_HEALTH_URL -e PW_SKIP_WEBSERVER=1 playwright

# Optional helpers if you choose to pre-start the test stack manually
test-env-up:
	@echo "INFO: Playwright will start the test servers unless PW_SKIP_WEBSERVER=1 is set."
	@echo "INFO: To start manually, run:  cd frontend && npm run dev:all:test"

test-env-down:
	@echo "INFO: Stop any manually started test servers if you launched them yourself."
	@echo "INFO: No docker-compose.test.yml defined yet for a multi-service test stack."

pw-doctor:
	cd frontend && npx playwright install --with-deps && npx playwright --version
