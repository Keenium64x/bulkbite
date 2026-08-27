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

if [[ -s /run/secrets/gemini_api_key ]]; then
	SITE_NAME="${SITE_NAME}" python3 <<'PY'
import json
import os
import stat
import tempfile
from pathlib import Path

site_config_path = Path("sites") / os.environ["SITE_NAME"] / "site_config.json"
secret_path = Path("/run/secrets/gemini_api_key")
site_config = json.loads(site_config_path.read_text())
site_config.update(
	{
		"gemini_api_key": secret_path.read_text().strip(),
		"gemini_private_receipt_approved": 1,
		"document_ai_model": "gemini-2.5-flash-lite",
	}
)

existing_mode = stat.S_IMODE(site_config_path.stat().st_mode)
with tempfile.NamedTemporaryFile("w", dir=site_config_path.parent, delete=False) as temporary_file:
	json.dump(site_config, temporary_file, indent=1, sort_keys=True)
	temporary_file.write("\n")
	temporary_path = Path(temporary_file.name)

temporary_path.chmod(existing_mode)
temporary_path.replace(site_config_path)
PY
fi
