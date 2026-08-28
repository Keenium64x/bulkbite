#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region TLS CONTRACT
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
HOSTNAME="admin.bulkbite.co.za"
EXPECTED_ADDRESS="188.166.144.156"
ACME_ROOT="/var/www/letsencrypt"
NGINX_TARGET="/etc/nginx/conf.d/bulkbite-admin.conf"
HTTP_SOURCE="${DEPLOY_DIRECTORY}/host/nginx-bulkbite-http.conf"
HTTPS_SOURCE="${DEPLOY_DIRECTORY}/host/nginx-bulkbite-https.conf"
RENEWAL_HOOK="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx"

# endregion TLS CONTRACT


# =============================================================================
# region TLS STATIONS
# =============================================================================

fail() {
  printf 'BulkBite TLS activation failed: %s\n' "$1" >&2
  exit 1
}

validate_tls_preflight() {
  [[ "${EUID}" -eq 0 ]] || fail "run this script as root"
  for command_name in certbot curl getent install nginx openssl systemctl; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "missing required command: ${command_name}"
  done
  [[ -f "${HTTP_SOURCE}" ]] || fail "missing HTTP nginx source"
  [[ -f "${HTTPS_SOURCE}" ]] || fail "missing HTTPS nginx source"

  curl -fsS \
    --max-time 8 \
    -H "Host: ${HOSTNAME}" \
    http://127.0.0.1:8088/api/method/ping |
    grep -q pong || fail "BulkBite is not healthy on port 8088"

  getent ahostsv4 "${HOSTNAME}" |
    awk '{print $1}' |
    grep -qx "${EXPECTED_ADDRESS}" ||
    fail "${HOSTNAME} does not resolve to ${EXPECTED_ADDRESS} from this server"
}

issue_certificate() {
  install -d -m 0755 "${ACME_ROOT}/.well-known/acme-challenge"
  install -o root -g root -m 0644 "${HTTP_SOURCE}" "${NGINX_TARGET}"
  nginx -t
  systemctl reload nginx

  certbot certonly \
    --webroot \
    --webroot-path "${ACME_ROOT}" \
    --cert-name "${HOSTNAME}" \
    --domain "${HOSTNAME}" \
    --non-interactive \
    --agree-tos \
    --register-unsafely-without-email \
    --keep-until-expiring
}

install_https_proxy() {
  install -d -m 0755 "$(dirname "${RENEWAL_HOOK}")"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'nginx -t' \
    'systemctl reload nginx' |
    install -o root -g root -m 0755 /dev/stdin "${RENEWAL_HOOK}"

  install -o root -g root -m 0644 "${HTTPS_SOURCE}" "${NGINX_TARGET}"
  nginx -t
  systemctl reload nginx
}

verify_tls() {
  curl -fsS \
    --max-time 12 \
    "https://${HOSTNAME}/api/method/ping" |
    grep -q pong || fail "public HTTPS health check did not return pong"

  echo | openssl s_client \
    -connect "${HOSTNAME}:443" \
    -servername "${HOSTNAME}" \
    2>/dev/null |
    openssl x509 -noout -checkend 604800 >/dev/null ||
    fail "the production certificate expires in less than seven days"
}

main() {
  validate_tls_preflight
  issue_certificate
  install_https_proxy
  verify_tls
  printf 'BulkBite HTTPS is live at https://%s/bulkbite\n' "${HOSTNAME}"
}

main "$@"

# endregion TLS STATIONS
