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
