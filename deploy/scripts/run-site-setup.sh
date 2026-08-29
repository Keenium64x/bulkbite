#!/usr/bin/env bash

set -euo pipefail

# Docker Compose mounts local secrets with their host ownership and mode. Copy
# the root-only host secret into container-private tmpfs, then drop privileges.
chown frappe:frappe /run/bulkbite-secrets
chmod 0700 /run/bulkbite-secrets
install -o frappe -g frappe -m 0400 \
  /run/secrets/gemini_api_key \
  /run/bulkbite-secrets/gemini_api_key

exec /usr/sbin/runuser -u frappe -- bash /workspace/setup-site.sh
