#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
set -a; source "${DEPLOY_DIRECTORY}/.env"; set +a

docker compose --project-directory "${DEPLOY_DIRECTORY}" --env-file "${DEPLOY_DIRECTORY}/.env" -f "${DEPLOY_DIRECTORY}/compose.yaml" \
  exec -T backend bench --site "${SITE_NAME}" backup --with-files --compress
