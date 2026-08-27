#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region HOST CONTRACT
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
PROJECT_DIRECTORY="$(cd "${DEPLOY_DIRECTORY}/.." && pwd)"
LEGACY_DIRECTORY="/opt/frappe"
BACKUP_ROOT="/opt/backups/frappe-retired"
NGINX_TARGET="/etc/nginx/conf.d/bulkbite-admin.conf"
NGINX_SOURCE="${DEPLOY_DIRECTORY}/host/nginx-bulkbite-http.conf"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIRECTORY="${BACKUP_ROOT}/${TIMESTAMP}"
BULKBITE_HEALTHY=0
NGINX_MUTATED=0
NGINX_TARGET_PREEXISTED=0
NGINX_BACKUP_FILE="${BACKUP_DIRECTORY}/bulkbite-admin.conf.before-activation"

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

# endregion HOST CONTRACT


# =============================================================================
# region VALIDATION STATIONS
# =============================================================================

fail() {
  printf 'BulkBite activation failed: %s\n' "$1" >&2
  exit 1
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "run this script as root"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

require_file() {
  [[ -f "$1" ]] || fail "missing required file: $1"
}

port_is_listening() {
  ss -lntH | awk '{print $4}' | grep -Eq "(^|:)${1}$"
}

bulkbite_is_healthy() {
  curl -fsS \
    --max-time 8 \
    -H 'Host: admin.bulkbite.co.za' \
    http://127.0.0.1:8088/api/method/ping |
    grep -q pong
}

validate_preflight() {
  require_root
  for command_name in docker nginx curl ss install cp; do
    require_command "${command_name}"
  done

  docker compose version >/dev/null
  require_file "${DEPLOY_DIRECTORY}/.env"
  require_file "${DEPLOY_DIRECTORY}/compose.yaml"
  require_file "${DEPLOY_DIRECTORY}/Containerfile"
  require_file "${NGINX_SOURCE}"
  require_file "${LEGACY_DIRECTORY}/.env"
  require_file "${LEGACY_DIRECTORY}/compose.yaml"
  require_file "${LEGACY_DIRECTORY}/compose.override.yaml"

  local available_kib
  available_kib="$(df --output=avail / | tail -n 1 | tr -d ' ')"
  (( available_kib >= 7340032 )) || fail "at least 7 GiB of free disk is required before the image build"

  if port_is_listening 8088 && ! bulkbite_is_healthy; then
    fail "port 8088 is occupied by a service that is not BulkBite"
  fi

  nginx -t
  "${BULKBITE_COMPOSE[@]}" config --quiet
}

# endregion VALIDATION STATIONS


# =============================================================================
# region LEGACY FRAPPE RECOVERY
# =============================================================================

legacy_frappe_is_running() {
  [[ -n "$("${LEGACY_COMPOSE[@]}" ps --status running -q 2>/dev/null)" ]]
}

backup_legacy_frappe() {
  install -d -m 0700 "${BACKUP_DIRECTORY}"
  cp --preserve=all \
    "${LEGACY_DIRECTORY}/.env" \
    "${LEGACY_DIRECTORY}/compose.yaml" \
    "${LEGACY_DIRECTORY}/compose.override.yaml" \
    "${BACKUP_DIRECTORY}/"

  if legacy_frappe_is_running; then
    for site_name in fcemanager.co.za poloway.co.za; do
      if [[ -d "${LEGACY_DIRECTORY}/workspace/frappe-bench/sites/${site_name}" ]]; then
        "${LEGACY_COMPOSE[@]}" exec -T backend \
          bash -lc "cd /workspace/frappe-bench && bench --site '${site_name}' backup --with-files --compress"
      fi
    done
  fi

  for site_name in fcemanager.co.za poloway.co.za; do
    local site_directory="${LEGACY_DIRECTORY}/workspace/frappe-bench/sites/${site_name}"
    if [[ -d "${site_directory}" ]]; then
      install -d -m 0700 "${BACKUP_DIRECTORY}/${site_name}"
      cp --preserve=all "${site_directory}/site_config.json" "${BACKUP_DIRECTORY}/${site_name}/"
      if [[ -d "${site_directory}/private/backups" ]]; then
        cp -a "${site_directory}/private/backups" "${BACKUP_DIRECTORY}/${site_name}/"
      fi
    fi
  done
}

stop_legacy_frappe() {
  if legacy_frappe_is_running; then
    "${LEGACY_COMPOSE[@]}" down --remove-orphans
  fi
}

restore_legacy_frappe_after_failure() {
  local exit_code=$?

  if (( exit_code != 0 && NGINX_MUTATED == 1 )); then
    if (( NGINX_TARGET_PREEXISTED == 1 )); then
      cp --preserve=all "${NGINX_BACKUP_FILE}" "${NGINX_TARGET}"
    else
      rm -f "${NGINX_TARGET}"
    fi
    nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
  fi

  if (( exit_code != 0 && BULKBITE_HEALTHY == 0 )); then
    printf 'BulkBite did not become healthy. Removing partial BulkBite containers and restoring legacy Frappe.\n' >&2
    "${BULKBITE_COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
    "${LEGACY_COMPOSE[@]}" up -d >/dev/null 2>&1 || true
  fi
  exit "${exit_code}"
}

# endregion LEGACY FRAPPE RECOVERY


# =============================================================================
# region BULKBITE ACTIVATION
# =============================================================================

deploy_bulkbite() {
  "${SCRIPT_DIRECTORY}/deploy.sh"
  bulkbite_is_healthy || fail "loopback health check did not return pong"
  BULKBITE_HEALTHY=1
}

install_http_proxy() {
  install -d -m 0755 /var/www/letsencrypt/.well-known/acme-challenge

  if [[ -f "${NGINX_TARGET}" ]]; then
    NGINX_TARGET_PREEXISTED=1
    cp --preserve=all "${NGINX_TARGET}" "${NGINX_BACKUP_FILE}"
  fi

  install -o root -g root -m 0644 "${NGINX_SOURCE}" "${NGINX_TARGET}"
  NGINX_MUTATED=1
  nginx -t
  systemctl reload nginx

  curl -fsS \
    --max-time 8 \
    -H 'Host: admin.bulkbite.co.za' \
    http://127.0.0.1/api/method/ping |
    grep -q pong || fail "host nginx did not route admin.bulkbite.co.za to BulkBite"
}

report_result() {
  printf '\nBulkBite is healthy on http://127.0.0.1:8088.\n'
  printf 'Legacy Frappe backup: %s\n' "${BACKUP_DIRECTORY}"
  printf 'Legacy Frappe containers are stopped; their workspace, volumes, images, and backups remain.\n'
  printf 'OmniRoute, Trilium, OpenClaw, and host nginx were not stopped.\n'
  printf 'Next: run %s as root to enable HTTPS.\n' "${SCRIPT_DIRECTORY}/enable-production-tls.sh"
}

main() {
  validate_preflight
  trap restore_legacy_frappe_after_failure EXIT
  backup_legacy_frappe
  stop_legacy_frappe
  deploy_bulkbite
  install_http_proxy
  trap - EXIT
  report_result
}

main "$@"

# endregion BULKBITE ACTIVATION
