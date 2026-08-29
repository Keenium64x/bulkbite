# BulkBite production deployment

## Normal release command

After the one-time host installation below, every application release is sent from the repository root with:

```bash
./deploy-bulkbite
```

The command builds the web frontend, checks the deployment scripts and Python source, creates a content-addressed release archive, uploads it through the restricted `bulkbite-codex` SSH account, and follows the server job until production verification finishes. If the dedicated SSH key is locked, the same command asks for its passphrase once and loads it into the current SSH agent.

The server job survives an interrupted laptop connection. Running `./deploy-bulkbite` again packages the same content under the same release ID and reconnects to the existing job instead of rebuilding a completed image.

The server keeps its production environment, Gemini key, Compose contract, privileged operator, extracted releases, and current-release pointer outside the deployment account's writable boundary. That account owns only its SSH metadata and incoming package directory, cannot call Docker directly, and may invoke only the fixed root-owned release operator.

### One-time host installation

Copy these four files from `deploy/host/` to one directory on the server:

- `bulkbite-release`
- `bulkbite_codex_ed25519.pub`
- `compose.production.yaml`
- `install-single-command-deployer.sh`

Run the installer once as root from that directory:

```bash
sudo ./install-single-command-deployer.sh
```

The installer imports the current production environment and Gemini key into `/etc/bulkbite`, installs the dedicated restricted SSH public key, installs the operator at `/usr/local/sbin/bulkbite-release`, validates its narrow sudo rule, and records the currently active release. It does not restart or rebuild the application.

### Release safety

Each release follows these stations:

1. Validate and checksum the uploaded archive.
2. Extract it into a new root-owned release directory.
3. Reuse the exact image when it already exists, otherwise build it while production remains online.
4. Back up the Frappe site before migration.
5. Run migration, start the candidate services, and synchronize assets.
6. Verify loopback health, public API health, the application shell, the exact built CSS file, and the latest included APK.
7. Mark the candidate current only after every check passes.

Only the isolated `bulkbite` Compose project is controlled. OmniRoute, Trilium, host nginx, and unrelated containers are outside the operator.

This stack runs only Frappe and the custom BulkBite app. It contains no ERPNext image or application.

## Server preparation

Install Docker Engine with Compose v2. Copy this repository to a stable server directory, then create the ignored environment file:

```bash
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
```

Replace both password placeholders with independent random values. Keep the stack bound to `127.0.0.1:8088`; the server's existing reverse proxy should terminate TLS and forward `admin.bulkbite.co.za` to that address.

Store the approved Gemini key in `deploy/secrets/gemini_api_key.txt`. The one-command production installer moves it to a root-controlled path and applies the container user's read permission. Compose mounts it only into the one-time site setup container, which writes the site configuration needed by the reviewed receipt and invoice workflow.

Run the complete idempotent deployment:

```bash
./deploy/scripts/deploy.sh
```

The first run builds the app image, creates `admin.bulkbite.co.za`, installs BulkBite, starts workers and the scheduler, and checks `/api/method/ping`. Later runs back up the live site first, rebuild the checked-out app commit, run migrations, restart services, and repeat the health check.

## Shared production host activation

The prepared DigitalOcean host already runs nginx plus OmniRoute, Trilium, OpenClaw, and a retired Frappe Compose project at `/opt/frappe`. Use the host activation stations from the staged release as root:

```bash
./deploy/scripts/activate-production-host.sh
./deploy/scripts/enable-production-tls.sh
./deploy/scripts/verify-production-host.sh
```

The activation station backs up `fcemanager.co.za` and `poloway.co.za`, stops only the `/opt/frappe` Compose project without deleting its volumes or workspace, deploys the isolated `bulkbite` project on `127.0.0.1:8088`, and adds a dedicated nginx HTTP route. It automatically restarts the legacy Frappe project if BulkBite fails before its first healthy response.

After the activation station has already created and verified the retired-site backups, use `resume-production-host.sh` for interrupted first deployments. It does not create another backup or restore the retired project. It stops that project when needed, builds the release image only when its exact tag is absent, then resumes the persistent BulkBite site and proxy stations. Re-running it after the image exists skips the image build.

The TLS station uses a dedicated ACME webroot, installs a certificate-renewal hook that validates and reloads nginx, and installs the final HTTPS nginx route only after DNS resolves to `188.166.144.156`. The proof station verifies the public app and confirms that ports `8080`, `18789`, and `20128` remain available for the preserved services.

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
