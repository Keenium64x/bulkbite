#!/usr/bin/env bash

set -euo pipefail

cd /home/frappe/frappe-bench

: "${SITE_NAME:?SITE_NAME is required}"
: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}"
: "${DB_ROOT_PASSWORD:?DB_ROOT_PASSWORD is required}"

if [[ ! -d "sites/${SITE_NAME}" ]]; then
  bench new-site "${SITE_NAME}" \
    --mariadb-user-host-login-scope='%' \
    --admin-password="${ADMIN_PASSWORD}" \
    --db-root-username=root \
    --db-root-password="${DB_ROOT_PASSWORD}" \
    --install-app=bulkbite \
    --set-default
else
  bench --site "${SITE_NAME}" install-app bulkbite 2>/dev/null || true
  bench --site "${SITE_NAME}" migrate --skip-search-index
  bench use "${SITE_NAME}"
fi

bench --site "${SITE_NAME}" enable-scheduler
bench --site "${SITE_NAME}" set-config host_name "https://${SITE_NAME}"
bench --site "${SITE_NAME}" set-config -p allow_cors '["https://localhost","capacitor://localhost"]'
bench --site "${SITE_NAME}" set-config mute_emails 0
