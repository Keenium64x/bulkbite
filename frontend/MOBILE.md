# BulkBite mobile application

BulkBite uses one Vue source tree in `frontend/src`. The web build is served by Frappe at `/bulkbite`. The mobile build packages the same application into Capacitor Android and iOS shells.

The installed app packages the Vue application shell so it can still explain an offline or unavailable server before production content loads. Every native authentication, API, upload, and export request is forced to `https://admin.bulkbite.co.za` over HTTPS. Build-time environment values cannot replace that origin. The local shell does not contain operational data and never falls back to local or development APIs. Browser sessions keep Frappe cookies and CSRF. Native sessions use short-lived access tokens with rotating refresh tokens stored by Android Keystore or iOS Keychain.

At startup, the installed app checks the device network and `https://admin.bulkbite.co.za/api/method/ping`. If production is unavailable, it shows the BulkBite recovery state and keeps retry available. A successful retry resumes native authentication and data loading.

## Debug APK

The debug APK uses the production website and API. It cannot open without an internet connection and a healthy production site. Build it with:

```bash
cd frontend
./scripts/android.sh build-debug
```

## Production mobile build

Android release signing uses ignored `android/key.properties` and an upload keystore. Start from `android/key.properties.example`, then run `./scripts/android.sh build-bundle`.

The resulting bundle is `android/app/build/outputs/bundle/release/app-release.aab`. iOS uses the same `dist-mobile` bundle, but final compilation and signing require macOS with Xcode.

Before release, test login, token rotation, logout, receipt and invoice uploads, barcode camera access, offline messaging, and deep links on physical devices.
