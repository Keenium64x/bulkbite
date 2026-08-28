#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region PRODUCTION DOMAIN RECOVERY
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
RELEASE_DIRECTORY="$(cd "${DEPLOY_DIRECTORY}/.." && pwd)"
COMPOSE=(
  docker compose
  --project-name bulkbite
  --project-directory "${DEPLOY_DIRECTORY}"
  --env-file "${DEPLOY_DIRECTORY}/.env"
  -f "${DEPLOY_DIRECTORY}/compose.yaml"
)

fail() {
  printf 'BulkBite production recovery failed: %s\n' "$1" >&2
  exit 1
}

resume_site_setup() {
  [[ "${EUID}" -eq 0 ]] || fail "run this script as root"
  chmod 0755 "${DEPLOY_DIRECTORY}" "${SCRIPT_DIRECTORY}"
  chmod 0755 "${SCRIPT_DIRECTORY}"/*.sh

  "${COMPOSE[@]}" up -d db redis-cache redis-queue
  "${COMPOSE[@]}" run --rm configurator
  "${COMPOSE[@]}" run --rm site-setup
  "${COMPOSE[@]}" up -d --remove-orphans \
    backend websocket queue-short queue-long scheduler frontend
}

activate_domain() {
  "${SCRIPT_DIRECTORY}/sync-production-assets.sh"
  "${SCRIPT_DIRECTORY}/healthcheck.sh"
  "${SCRIPT_DIRECTORY}/enable-production-tls.sh"
  "${SCRIPT_DIRECTORY}/verify-production-host.sh"
  ln -sfn "${RELEASE_DIRECTORY}" /home/codex-bulkbite/current
}

main() {
  resume_site_setup
  activate_domain
  printf 'BulkBite production is active at https://admin.bulkbite.co.za/bulkbite\n'
}

main "$@"

# endregion PRODUCTION DOMAIN RECOVERY
