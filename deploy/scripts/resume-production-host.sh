#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region RESUMABLE HOST CONTRACT
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
PROJECT_DIRECTORY="$(cd "${DEPLOY_DIRECTORY}/.." && pwd)"
LEGACY_DIRECTORY="/opt/frappe"
BACKUP_ROOT="/opt/backups/frappe-retired"
NGINX_SOURCE="${DEPLOY_DIRECTORY}/host/nginx-bulkbite-http.conf"
NGINX_TARGET="/etc/nginx/conf.d/bulkbite-admin.conf"

set -a
source "${DEPLOY_DIRECTORY}/.env"
set +a

: "${SITE_NAME:?SITE_NAME is required}"
: "${BULKBITE_IMAGE:?BULKBITE_IMAGE is required}"
: "${BULKBITE_TAG:?BULKBITE_TAG is required}"

IMAGE_REFERENCE="${BULKBITE_IMAGE}:${BULKBITE_TAG}"

LEGACY_COMPOSE=(
  docker compose
  --project-name frappe
  --project-directory "${LEGACY_DIRECTORY}"
  --env-file "${LEGACY_DIRECTORY}/.env"
  -f "${LEGACY_DIRECTORY}/compose.yaml"
  -f "${LEGACY_DIRECTORY}/compose.override.yaml"
)

BULKBITE_COMPOSE=(
  docker compose
  --project-name bulkbite
  --project-directory "${DEPLOY_DIRECTORY}"
  --env-file "${DEPLOY_DIRECTORY}/.env"
  -f "${DEPLOY_DIRECTORY}/compose.yaml"
)

# endregion RESUMABLE HOST CONTRACT


# =============================================================================
# region RESUMABLE STATIONS
# =============================================================================

fail() {
  printf 'BulkBite resume failed: %s\n' "$1" >&2
  exit 1
}

validate_resume_preflight() {
  [[ "${EUID}" -eq 0 ]] || fail "run this script as root"
  for command_name in docker curl install nginx; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "missing required command: ${command_name}"
  done

  [[ -f "${DEPLOY_DIRECTORY}/compose.yaml" ]] || fail "missing BulkBite Compose file"
  [[ -f "${DEPLOY_DIRECTORY}/Containerfile" ]] || fail "missing BulkBite Containerfile"
  [[ -s "${DEPLOY_DIRECTORY}/secrets/gemini_api_key.txt" ]] || fail "missing or empty Gemini secret"
  [[ -f "${NGINX_SOURCE}" ]] || fail "missing BulkBite nginx source"
  [[ -f "${LEGACY_DIRECTORY}/.env" ]] || fail "missing retired Frappe environment"

  # Compose exposes these host files inside containers running as `frappe`.
  chmod 0755 "${DEPLOY_DIRECTORY}" "${DEPLOY_DIRECTORY}/scripts"
  chmod 0755 "${DEPLOY_DIRECTORY}"/scripts/*.sh
  chmod 0644 "${DEPLOY_DIRECTORY}/secrets/gemini_api_key.txt"

  find "${BACKUP_ROOT}" -mindepth 2 -maxdepth 3 -type d -name backups -print -quit |
    grep -q . || fail "no retired Frappe site backup directory was found"

  docker compose version >/dev/null
  "${BULKBITE_COMPOSE[@]}" config --quiet
  nginx -t
}

stop_retired_frappe() {
  if [[ -n "$("${LEGACY_COMPOSE[@]}" ps --status running -q 2>/dev/null)" ]]; then
    printf 'Stopping only the retired FCEMANAGER and Poloway Frappe project.\n'
    "${LEGACY_COMPOSE[@]}" down --remove-orphans
  else
    printf 'Retired Frappe project is already stopped.\n'
  fi
}

build_image_once() {
  if docker image inspect "${IMAGE_REFERENCE}" >/dev/null 2>&1; then
    printf 'Using existing image %s.\n' "${IMAGE_REFERENCE}"
    return
  fi

  printf 'Building %s from the existing Docker cache.\n' "${IMAGE_REFERENCE}"
  docker build \
    --file "${DEPLOY_DIRECTORY}/Containerfile" \
    --tag "${IMAGE_REFERENCE}" \
    "${PROJECT_DIRECTORY}"
}

configure_site_and_start_services() {
  "${BULKBITE_COMPOSE[@]}" up -d db redis-cache redis-queue
  "${BULKBITE_COMPOSE[@]}" run --rm configurator
  "${BULKBITE_COMPOSE[@]}" run --rm site-setup
  "${BULKBITE_COMPOSE[@]}" up -d --remove-orphans \
    backend websocket queue-short queue-long scheduler frontend
  "${SCRIPT_DIRECTORY}/healthcheck.sh"
}

install_http_proxy() {
  install -d -m 0755 /var/www/letsencrypt/.well-known/acme-challenge
  install -o root -g root -m 0644 "${NGINX_SOURCE}" "${NGINX_TARGET}"
  nginx -t
  systemctl reload nginx

  curl -fsS \
    --max-time 8 \
    -H "Host: ${SITE_NAME}" \
    http://127.0.0.1/api/method/ping |
    grep -q pong || fail "host nginx did not route ${SITE_NAME} to BulkBite"
}

report_resume_result() {
  printf '\nBulkBite is running at http://127.0.0.1:8088.\n'
  printf 'Image: %s\n' "${IMAGE_REFERENCE}"
  printf 'The retired Frappe project remains stopped and recoverable.\n'
  printf 'Next station after DNS resolves: %s\n' "${SCRIPT_DIRECTORY}/enable-production-tls.sh"
}

main() {
  validate_resume_preflight
  stop_retired_frappe
  build_image_once
  configure_site_and_start_services
  install_http_proxy
  report_resume_result
}

main "$@"

# endregion RESUMABLE STATIONS
