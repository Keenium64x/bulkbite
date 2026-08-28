# BulkBite mobile application

BulkBite uses one Vue source tree in `frontend/src`. The web build is served by Frappe at `/bulkbite`. The mobile build packages the same application into Capacitor Android and iOS shells.

The installed app loads the live application from `https://admin.huispunte.co.za/bulkbite`. It also forces every native authentication, API, upload, and export request to the same production origin over HTTPS. Build-time environment values cannot replace that origin. Browser sessions keep Frappe cookies and CSRF. Native sessions use short-lived access tokens with rotating refresh tokens stored by Android Keystore or iOS Keychain.

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
