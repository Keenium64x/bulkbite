#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
PROJECT_DIRECTORY="$(cd "${DEPLOY_DIRECTORY}/.." && pwd)"
COMPOSE=(docker compose --project-directory "${DEPLOY_DIRECTORY}" --env-file "${DEPLOY_DIRECTORY}/.env" -f "${DEPLOY_DIRECTORY}/compose.yaml")

[[ -f "${DEPLOY_DIRECTORY}/.env" ]] || { printf 'Copy deploy/.env.example to deploy/.env and set production secrets.\n' >&2; exit 1; }

set -a
source "${DEPLOY_DIRECTORY}/.env"
set +a

: "${SITE_NAME:?SITE_NAME is required}"

# Docker Compose bind-mounts local secrets without translating the host mode.
# The Frappe container runs as a non-root user and must be able to read this file.
test -s "${DEPLOY_DIRECTORY}/secrets/gemini_api_key.txt"
chmod 0755 "${DEPLOY_DIRECTORY}" "${DEPLOY_DIRECTORY}/scripts"
chmod 0755 "${DEPLOY_DIRECTORY}"/scripts/*.sh
chmod 0644 "${DEPLOY_DIRECTORY}/secrets/gemini_api_key.txt"

if [[ -d "${PROJECT_DIRECTORY}/.git" ]]; then
  BULKBITE_TAG="$(git -C "${PROJECT_DIRECTORY}" rev-parse --short=12 HEAD)"
  export BULKBITE_TAG
fi

if "${COMPOSE[@]}" ps --status running backend 2>/dev/null | grep -q backend; then
  "${COMPOSE[@]}" exec -T backend bench --site "${SITE_NAME}" backup --with-files --compress
fi

docker build \
  --file "${DEPLOY_DIRECTORY}/Containerfile" \
  --tag "${BULKBITE_IMAGE:-bulkbite}:${BULKBITE_TAG:-local}" \
  "${PROJECT_DIRECTORY}"

"${COMPOSE[@]}" up -d db redis-cache redis-queue
"${COMPOSE[@]}" run --rm configurator
"${COMPOSE[@]}" run --rm site-setup
"${COMPOSE[@]}" up -d --remove-orphans backend websocket queue-short queue-long scheduler frontend

"${SCRIPT_DIRECTORY}/healthcheck.sh"
