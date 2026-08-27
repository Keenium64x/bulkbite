# BulkBite mobile application

BulkBite uses one Vue source tree in `frontend/src`. The web build is served by Frappe at `/bulkbite`. The mobile build packages the same application into Capacitor Android and iOS shells.

The installed app does not use a committed remote `server.url`. It loads its bundled files and calls `https://admin.bulkbite.co.za` over HTTPS. Browser sessions keep Frappe cookies and CSRF. Native sessions use short-lived access tokens with rotating refresh tokens stored by Android Keystore or iOS Keychain.

## Local mobile development

Run Frappe and Vite locally, then expose Vite through an HTTPS tunnel. Build a debug app with the tunnel URL:

```bash
cd frontend
BULKBITE_DEVELOPMENT_API_URL=https://your-tunnel.example ./scripts/android.sh build-debug
```

The tunnel must reach the Vite server on port 8080. Vite proxies Frappe paths to `bulkbite.localhost:8006` with the correct site header.

## Production mobile build

Android release signing uses ignored `android/key.properties` and an upload keystore. Start from `android/key.properties.example`, then run `./scripts/android.sh build-bundle`.

The resulting bundle is `android/app/build/outputs/bundle/release/app-release.aab`. iOS uses the same `dist-mobile` bundle, but final compilation and signing require macOS with Xcode.

Before release, test login, token rotation, logout, receipt and invoice uploads, barcode camera access, offline messaging, and deep links on physical devices.
