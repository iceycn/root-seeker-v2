#!/usr/bin/env bash

set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BASE_URL="http://${HOST}:${PORT}"

echo "== RootSeeker API Demo =="
echo "base_url: ${BASE_URL}"

echo
echo "-- 1) health check"
curl -sS "${BASE_URL}/healthz"
echo

echo
echo "-- 2) list skills"
curl -sS "${BASE_URL}/skills"
echo

echo
echo "-- 3) run default case"
RUN_RESPONSE="$(curl -sS -X POST "${BASE_URL}/cases/run-default" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "API demo incident",
    "symptom": "error ratio high in prod",
    "service_name": "order-service",
    "source": "api-demo",
    "metadata": {
      "trace_id": "trace-api-demo-001",
      "tenant": "demo",
      "environment": "prod"
    }
  }')"
echo "${RUN_RESPONSE}"
echo

CASE_ID="$(echo "${RUN_RESPONSE}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["case"]["case_id"])')"
echo "case_id: ${CASE_ID}"

echo
echo "-- 4) get case"
curl -sS "${BASE_URL}/cases/${CASE_ID}"
echo

echo
echo "-- 5) get report"
curl -sS "${BASE_URL}/reports/${CASE_ID}"
echo
