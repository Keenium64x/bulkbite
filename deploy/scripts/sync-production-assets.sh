#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region ASSET SYNC CONTRACT
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"

set -a
source "${DEPLOY_DIRECTORY}/.env"
set +a

COMPOSE=(
  docker compose
  --project-name bulkbite
  --project-directory "${DEPLOY_DIRECTORY}"
  --env-file "${DEPLOY_DIRECTORY}/.env"
  -f "${DEPLOY_DIRECTORY}/compose.yaml"
)

[[ "${EUID}" -eq 0 ]] || { printf 'Run this script as root.\n' >&2; exit 1; }

# endregion ASSET SYNC CONTRACT


# =============================================================================
# region ASSET SYNC STATIONS
# =============================================================================

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

"${COMPOSE[@]}" restart frontend

asset_index="$(${COMPOSE[@]} exec -T backend bash -lc '
  sed -n "s/.*href=\"\/assets\/bulkbite\/frontend\/assets\/\([^\"]*\.css\)\".*/\1/p" \
    apps/bulkbite/bulkbite/public/frontend/index.html | head -n 1
')"
[[ -n "${asset_index}" ]] || { printf 'BulkBite CSS asset was not found in the built index.\n' >&2; exit 1; }

for attempt in $(seq 1 30); do
  if curl -fsS --max-time 8 \
      -H "Host: ${SITE_NAME:-admin.bulkbite.co.za}" \
      http://127.0.0.1:8088/api/method/ping |
      grep -q pong \
    && curl -fsS --max-time 8 \
      -H "Host: ${SITE_NAME:-admin.bulkbite.co.za}" \
      "http://127.0.0.1:8088/assets/bulkbite/frontend/assets/${asset_index}" \
      >/dev/null \
    && curl -fsS --max-time 8 \
      -H "Host: ${SITE_NAME:-admin.bulkbite.co.za}" \
      http://127.0.0.1:8088/assets/frappe/dist/css/login.bundle.JH677HQF.css \
      >/dev/null; then
    printf 'BulkBite production assets are available.\n'
    exit 0
  fi
  sleep 2
done

printf 'BulkBite asset verification failed.\n' >&2
exit 1

# endregion ASSET SYNC STATIONS
