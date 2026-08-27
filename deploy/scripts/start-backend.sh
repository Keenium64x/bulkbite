#!/usr/bin/env bash

set -euo pipefail

exec /home/frappe/frappe-bench/env/bin/gunicorn \
  --chdir /home/frappe/frappe-bench/sites \
  --bind 0.0.0.0:8000 \
  --threads "${GUNICORN_THREADS:-2}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  --worker-class gthread \
  --worker-tmp-dir /dev/shm \
  --timeout "${GUNICORN_TIMEOUT:-180}" \
  --preload \
  frappe.app:application
