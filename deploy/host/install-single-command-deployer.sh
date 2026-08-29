#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region ONE-TIME INSTALLATION CONTRACT
# =============================================================================

DEPLOY_USER="codex-bulkbite"
DEPLOY_ROOT="/home/codex-bulkbite"
SOURCE_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIRECTORY="/etc/bulkbite"
STATE_DIRECTORY="/var/lib/bulkbite"
OPERATOR_TARGET="/usr/local/sbin/bulkbite-release"
COMPOSE_TARGET="${CONFIG_DIRECTORY}/compose.production.yaml"
RUNTIME_ENVIRONMENT="${CONFIG_DIRECTORY}/runtime.env"
GEMINI_SECRET="${CONFIG_DIRECTORY}/gemini_api_key.txt"
SUDOERS_TARGET="/etc/sudoers.d/bulkbite-release"
DEPLOY_PUBLIC_KEY_SOURCE="${SOURCE_DIRECTORY}/bulkbite_codex_ed25519.pub"

fail() {
  printf 'BulkBite deployer installation failed: %s\n' "$1" >&2
  exit 1
}

find_existing_release_file() {
  local relative_path="$1"
  local current_directory
  current_directory="$(readlink -f "${DEPLOY_ROOT}/current" 2>/dev/null || true)"
  if [[ -n "${current_directory}" && -f "${current_directory}/${relative_path}" ]]; then
    printf '%s\n' "${current_directory}/${relative_path}"
    return
  fi
  find "${DEPLOY_ROOT}/releases" -mindepth 2 -maxdepth 4 -type f -path "*/${relative_path}" -print | sort -r | head -n 1
}

normalize_runtime_environment() {
  local environment_file="$1"
  sed -i \
    -e '/^BULKBITE_TAG=/d' \
    -e '/^BULKBITE_IMAGE=/d' \
    -e '/^BULKBITE_BIND_ADDRESS=/d' \
    -e '/^BULKBITE_HTTP_PORT=/d' \
    "${environment_file}"
  chmod 0600 "${environment_file}"
}

install_restricted_deployment_key() {
  local deploy_home
  deploy_home="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
  [[ "${deploy_home}" == "${DEPLOY_ROOT}" ]] || fail "deployment account has an unexpected home directory"
  [[ -s "${DEPLOY_PUBLIC_KEY_SOURCE}" ]] || fail "dedicated deployment public key is missing"

  local public_key authorized_key
  public_key="$(cat "${DEPLOY_PUBLIC_KEY_SOURCE}")"
  [[ "${public_key}" == ssh-ed25519\ * ]] || fail "deployment public key is not ED25519"
  authorized_key="restrict ${public_key}"

  install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" -m 0700 "${DEPLOY_ROOT}/.ssh"
  printf '%s\n' "${authorized_key}" > "${DEPLOY_ROOT}/.ssh/authorized_keys"
  chown "${DEPLOY_USER}:${DEPLOY_USER}" "${DEPLOY_ROOT}/.ssh/authorized_keys"
  chmod 0600 "${DEPLOY_ROOT}/.ssh/authorized_keys"
}

main() {
  [[ "${EUID}" -eq 0 ]] || fail "run this installer as root"
  id "${DEPLOY_USER}" >/dev/null 2>&1 || fail "deployment account ${DEPLOY_USER} does not exist"
  for command_name in docker sha256sum visudo; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "${command_name} is required"
  done

  install -d -o root -g root -m 0711 "${DEPLOY_ROOT}"
  install -d -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" -m 0700 "${DEPLOY_ROOT}/incoming"
  install -d -o root -g root -m 0711 "${DEPLOY_ROOT}/releases"
  install -d -o root -g root -m 0700 "${CONFIG_DIRECTORY}" "${STATE_DIRECTORY}"
  install_restricted_deployment_key

  if [[ ! -s "${RUNTIME_ENVIRONMENT}" ]]; then
    existing_environment="$(find_existing_release_file 'deploy/.env')"
    [[ -n "${existing_environment}" ]] || fail "no existing production deploy/.env was found"
    install -o root -g root -m 0600 "${existing_environment}" "${RUNTIME_ENVIRONMENT}"
  fi
  normalize_runtime_environment "${RUNTIME_ENVIRONMENT}"

  if [[ ! -s "${GEMINI_SECRET}" ]]; then
    existing_secret="$(find_existing_release_file 'deploy/secrets/gemini_api_key.txt')"
    [[ -n "${existing_secret}" ]] || fail "no existing Gemini secret was found"
    install -o root -g root -m 0600 "${existing_secret}" "${GEMINI_SECRET}"
  fi

  [[ -s "${SOURCE_DIRECTORY}/bulkbite-release" ]] || fail "bulkbite-release is missing beside the installer"
  [[ -s "${SOURCE_DIRECTORY}/compose.production.yaml" ]] || fail "Compose contract is missing beside the installer"
  install -o root -g root -m 0755 "${SOURCE_DIRECTORY}/bulkbite-release" "${OPERATOR_TARGET}"
  install -o root -g root -m 0644 "${SOURCE_DIRECTORY}/compose.production.yaml" "${COMPOSE_TARGET}"

  operator_digest_before="$(sha256sum "${OPERATOR_TARGET}" | awk '{print $1}')"
  compose_digest_before="$(sha256sum "${COMPOSE_TARGET}" | awk '{print $1}')"

  printf '%s\n' \
    "${DEPLOY_USER} ALL=(root) NOPASSWD: ${OPERATOR_TARGET} start *" \
    "${DEPLOY_USER} ALL=(root) NOPASSWD: ${OPERATOR_TARGET} wait *" \
    "${DEPLOY_USER} ALL=(root) NOPASSWD: ${OPERATOR_TARGET} status" \
    > "${SUDOERS_TARGET}.tmp"
  chmod 0440 "${SUDOERS_TARGET}.tmp"
  visudo -cf "${SUDOERS_TARGET}.tmp" >/dev/null
  mv "${SUDOERS_TARGET}.tmp" "${SUDOERS_TARGET}"
  rm -f /etc/sudoers.d/codex-bulkbite-production

  if [[ ! -s "${STATE_DIRECTORY}/current-release" && -L "${DEPLOY_ROOT}/current" ]]; then
    basename "$(readlink -f "${DEPLOY_ROOT}/current")" > "${STATE_DIRECTORY}/current-release"
  fi

  [[ "$(sha256sum "${OPERATOR_TARGET}" | awk '{print $1}')" == "${operator_digest_before}" ]] || fail "operator changed during installation"
  [[ "$(sha256sum "${COMPOSE_TARGET}" | awk '{print $1}')" == "${compose_digest_before}" ]] || fail "Compose contract changed during installation"

  current_release_directory="$(readlink -f "${DEPLOY_ROOT}/current" 2>/dev/null || true)"
  [[ -n "${current_release_directory}" && -d "${current_release_directory}/deploy/scripts" ]] || fail "current release scripts were not found"
  current_release_id="$(basename "${current_release_directory}")"
  BULKBITE_TAG="${current_release_id}" \
  BULKBITE_RELEASE_SCRIPTS="${current_release_directory}/deploy/scripts" \
  BULKBITE_GEMINI_SECRET="${GEMINI_SECRET}" \
    docker compose \
      --project-name bulkbite \
      --project-directory "${CONFIG_DIRECTORY}" \
      --env-file "${RUNTIME_ENVIRONMENT}" \
      --file "${COMPOSE_TARGET}" \
      config --quiet

  "${OPERATOR_TARGET}" status >/dev/null

  printf 'BulkBite single-command deployer installed.\n'
  printf 'Future deployment command: ./deploy-bulkbite\n'
}

main "$@"

# endregion ONE-TIME INSTALLATION CONTRACT
