PYTHON ?= python3
UVICORN ?= uvicorn
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: install test api admin demo demo-api worker worker-loop scheduler scheduler-loop

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
