#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"

set -a
source "${DEPLOY_DIRECTORY}/.env"
set +a

health_url="http://${BULKBITE_BIND_ADDRESS:-127.0.0.1}:${BULKBITE_HTTP_PORT:-8088}/api/method/ping"

for attempt in $(seq 1 30); do
  if curl -fsS -H "Host: ${SITE_NAME}" "${health_url}" | grep -q pong; then
    printf 'BulkBite is healthy at %s via Host %s\n' "${health_url}" "${SITE_NAME}"
    exit 0
  fi
  sleep 2
done

printf 'BulkBite health check failed after 60 seconds.\n' >&2
exit 1
