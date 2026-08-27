#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"

COMPOSE=(
  docker compose
  --project-name bulkbite
  --project-directory "${DEPLOY_DIRECTORY}"
  --env-file "${DEPLOY_DIRECTORY}/.env"
  -f "${DEPLOY_DIRECTORY}/compose.yaml"
)

[[ "${EUID}" -eq 0 ]] || { printf 'Run this script as root.\n' >&2; exit 1; }

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" up -d --no-deps --force-recreate backend frontend

for attempt in $(seq 1 30); do
  if curl -fsS \
    --max-time 8 \
    -H 'Host: admin.bulkbite.co.za' \
    http://127.0.0.1:8088/api/method/ping |
    grep -q pong; then
    printf 'BulkBite runtime is healthy on http://127.0.0.1:8088.\n'
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" logs --no-color --tail=120 backend frontend >&2
printf 'BulkBite backend did not become healthy within 60 seconds.\n' >&2
exit 1
