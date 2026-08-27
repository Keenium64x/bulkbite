# BulkBite production deployment

This stack runs only Frappe and the custom BulkBite app. It contains no ERPNext image or application.

## Server preparation

Install Docker Engine with Compose v2. Copy this repository to a stable server directory, then create the ignored environment file:

```bash
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
```

Replace both password placeholders with independent random values. Keep the stack bound to `127.0.0.1:8088`; the server's existing reverse proxy should terminate TLS and forward `admin.bulkbite.co.za` to that address.

Run the complete idempotent deployment:

```bash
./deploy/scripts/deploy.sh
```

The first run builds the app image, creates `admin.bulkbite.co.za`, installs BulkBite, starts workers and the scheduler, and checks `/api/method/ping`. Later runs back up the live site first, rebuild the checked-out app commit, run migrations, restart services, and repeat the health check.

## Proxy and DNS

`Caddyfile.example` shows the smallest Caddy route. If the server already uses nginx or Traefik, add an equivalent hostname route to `127.0.0.1:8088`. After the proxy route and TLS are verified, create the DNS record for `admin.bulkbite.co.za` pointing to the production proxy's public IP.

Do not point the admin hostname to the current `bulkbite.co.za` IP. The public site is hosted by Netlify and is not the Frappe server.

The `domain/.well-known` templates are for Android App Links and iOS Universal Links. Replace their signing placeholders after the Android upload certificate and Apple Team ID exist, then serve the completed JSON files from `https://admin.bulkbite.co.za/.well-known/` without redirects.

## Operations

Create an immediate backup with `./deploy/scripts/backup.sh`. Frappe backups are stored in the persistent site volume under `sites/admin.bulkbite.co.za/private/backups`. Copy them to independent off-server storage on a schedule.

To inspect the stack:

```bash
docker compose --project-directory deploy --env-file deploy/.env -f deploy/compose.yaml ps
docker compose --project-directory deploy --env-file deploy/.env -f deploy/compose.yaml logs --tail=200 frontend backend queue-long
```

The Docker image is built from the current checkout because this repository does not yet have a Git remote. Once a private remote or image registry is selected, the same Compose and migration flow can deploy a pulled commit or versioned image without changing the application architecture.
