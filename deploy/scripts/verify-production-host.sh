#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region PRODUCTION PROOF
# =============================================================================

HOSTNAME="admin.huispunte.co.za"
EXPECTED_ADDRESS="188.166.144.156"
PRESERVED_PORTS=(8080 18789 20128)

fail() {
  printf 'BulkBite production verification failed: %s\n' "$1" >&2
  exit 1
}

verify_listener() {
  local port="$1"
  ss -lntH | awk '{print $4}' | grep -Eq "(^|:)${port}$" || fail "preserved listener ${port} is missing"
}

main() {
  getent ahostsv4 "${HOSTNAME}" | awk '{print $1}' | grep -qx "${EXPECTED_ADDRESS}" || fail "DNS does not point to ${EXPECTED_ADDRESS}"

  curl -fsS --max-time 8 -H "Host: ${HOSTNAME}" http://127.0.0.1:8088/api/method/ping | grep -q pong || fail "loopback BulkBite health failed"
  curl -fsS --max-time 12 "https://${HOSTNAME}/api/method/ping" | grep -q pong || fail "public API health failed"
  curl -fsS --max-time 12 -o /dev/null "https://${HOSTNAME}/bulkbite" || fail "public application route failed"

  for port in "${PRESERVED_PORTS[@]}"; do
    verify_listener "${port}"
  done

  printf 'BulkBite production verification passed.\n'
  printf 'Application: https://%s/bulkbite\n' "${HOSTNAME}"
  printf 'Preserved listeners: %s\n' "${PRESERVED_PORTS[*]}"
}

main "$@"

# endregion PRODUCTION PROOF
