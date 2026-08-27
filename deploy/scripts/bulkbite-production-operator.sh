#!/usr/bin/env bash

set -euo pipefail

# Installed as a root-owned fixed-path operator. The sudo rule must permit only
# this file, never the release copy or the Docker command directly.
APP_CONTAINERS=(
  bulkbite-backend-1
  bulkbite-frontend-1
  bulkbite-websocket-1
  bulkbite-scheduler-1
  bulkbite-queue-short-1
  bulkbite-queue-long-1
)
ALL_CONTAINERS=(
  "${APP_CONTAINERS[@]}"
  bulkbite-db-1
  bulkbite-redis-cache-1
  bulkbite-redis-queue-1
)

case "${1:-}" in
  status)
    /usr/bin/docker inspect \
      --format '{{.Name}} {{.State.Status}} restart={{.RestartCount}} exit={{.State.ExitCode}} error={{.State.Error}}' \
      "${ALL_CONTAINERS[@]}"
    /usr/bin/ss -lntH | /usr/bin/awk '{print $4}' | /usr/bin/grep -E '(:8088|:18789|:20128|:8080)$' || true
    ;;
  logs)
    for container_name in "${APP_CONTAINERS[@]}"; do
      printf '\n===== %s =====\n' "${container_name}"
      /usr/bin/docker logs --tail 160 "${container_name}" 2>&1 || true
    done
    ;;
  restart-app)
    /usr/bin/docker restart "${APP_CONTAINERS[@]}"
    ;;
  health)
    /usr/bin/curl -fsS \
      --max-time 8 \
      -H 'Host: admin.bulkbite.co.za' \
      http://127.0.0.1:8088/api/method/ping
    ;;
  *)
    printf 'Usage: %s {status|logs|restart-app|health}\n' "$0" >&2
    exit 2
    ;;
esac
