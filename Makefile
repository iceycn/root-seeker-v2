PYTHON ?= python3
UVICORN ?= uvicorn
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: install test api admin demo demo-api worker worker-loop scheduler scheduler-loop \
        docker-up docker-down docker-build docker-logs docker-ps \
        k8s-deploy k8s-remove k8s-status k8s-build

# ==============================
# Local Development
# ==============================

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	pytest

api:
	$(UVICORN) apps.api.main:app --reload --host $(HOST) --port $(PORT)

admin:
	$(UVICORN) apps.admin.main:app --reload --host $(HOST) --port 8010

demo:
	$(PYTHON) scripts/demo_default_flow.py

demo-api:
	bash scripts/demo_api_flow.sh

worker:
	rootseeker-worker --seed-demo

worker-loop:
	rootseeker-worker --loop --interval-seconds 2 --max-empty-polls 5 --seed-demo

scheduler:
	rootseeker-scheduler

scheduler-loop:
	rootseeker-scheduler --loop --interval-seconds 60 --retries 2

# ==============================
# Docker Compose
# ==============================

docker-build:
	docker compose build

docker-up:
	@test -f .env || cp .env.docker .env
	@bash -c 'source scripts/sync-compose-storage.sh && sync_storage_compose_profiles && docker compose up -d --build'
	@echo ""
	@echo "RootSeeker V2 is starting!"
	@echo "  API:      http://localhost:8000"
	@echo "  Admin:    http://localhost:8010"
	@echo "  Zoekt:    http://localhost:6070"
	@echo "  Qdrant:   http://localhost:6333"
	@echo "  GitNexus: http://localhost:7474"
	@echo "  MySQL:    internal compose network only (when backend=mysql)"
	@echo "  Health:   curl http://localhost:8000/healthz"
	@echo "            curl http://localhost:7474/healthz"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-ps:
	docker compose ps

# ==============================
# Kubernetes
# ==============================

k8s-build: docker-build
	docker build -t rootseeker:latest .
	docker build -t rootseeker-zoekt:latest -f docker/Dockerfile.zoekt docker/
	docker build -t rootseeker-gitnexus:latest -f docker/Dockerfile.gitnexus .

k8s-deploy:
	kubectl apply -k k8s/
	@echo ""
	@echo "RootSeeker V2 deployed! Wait for pods:"
	@echo "  kubectl get pods -n rootseeker -w"

k8s-remove:
	kubectl delete -k k8s/ --ignore-not-found=true

k8s-status:
	kubectl get all -n rootseeker
