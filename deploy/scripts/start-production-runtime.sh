#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"

set -a
source "${DEPLOY_DIRECTORY}/.env"
set +a

: "${BULKBITE_IMAGE:?BULKBITE_IMAGE is required}"
: "${BULKBITE_TAG:?BULKBITE_TAG is required}"

COMPOSE=(
  docker compose
  --project-name bulkbite
  --project-directory "${DEPLOY_DIRECTORY}"
  --env-file "${DEPLOY_DIRECTORY}/.env"
  -f "${DEPLOY_DIRECTORY}/compose.yaml"
)

[[ "${EUID}" -eq 0 ]] || { printf 'Run this script as root.\n' >&2; exit 1; }

printf 'Using image %s:%s.\n' "${BULKBITE_IMAGE}" "${BULKBITE_TAG}"
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" rm --stop --force backend frontend
"${COMPOSE[@]}" up -d --no-deps backend frontend

if ! "${COMPOSE[@]}" exec -T backend \
    bash -lc "test -s assets/assets.json \
      && test \"\$(tr -d '[:space:]' < assets/assets.json)\" != '{}' \
      && test -s assets/bulkbite/frontend/index.html"; then
  printf 'Rebuilding the shared Frappe and BulkBite asset manifest.\n'
  "${COMPOSE[@]}" exec -T \
    -e NODE_OPTIONS=--max-old-space-size=1536 \
    backend \
    bench build --production
fi

"${COMPOSE[@]}" exec -T backend bash -lc '
  set -euo pipefail
  for app_name in frappe bulkbite; do
    source_directory="apps/${app_name}/${app_name}/public"
    target_directory="assets/${app_name}"
    if [[ -L "${target_directory}" ]]; then
      unlink "${target_directory}"
    fi
    mkdir -p "${target_directory}"
    cp -a "${source_directory}/." "${target_directory}/"
  done
'

"${COMPOSE[@]}" exec -T backend \
  bench --site "${SITE_NAME:-admin.bulkbite.co.za}" clear-cache

for attempt in $(seq 1 30); do
  if curl -fsS \
      --max-time 8 \
      -H "Host: ${SITE_NAME:-admin.bulkbite.co.za}" \
      http://127.0.0.1:8088/api/method/ping |
      grep -q pong \
    && curl -fsS \
      --max-time 8 \
      -H "Host: ${SITE_NAME:-admin.bulkbite.co.za}" \
      http://127.0.0.1:8088/assets/bulkbite/frontend/index.html |
      grep -q '<div id="app">'; then
    printf 'BulkBite runtime is healthy on http://127.0.0.1:8088.\n'
    exit 0
  fi
  sleep 2
done

"${COMPOSE[@]}" logs --no-color --tail=120 backend frontend >&2
printf 'BulkBite backend did not become healthy within 60 seconds.\n' >&2
exit 1
