#!/usr/bin/env bash

set -euo pipefail

# =============================================================================
# region ANDROID TOOLCHAIN ENVIRONMENT
# =============================================================================

SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
USER_DIRECTORY="$(getent passwd "$(id -u)" | cut -d: -f6)"
USER_DATA_DIRECTORY="${XDG_DATA_HOME:-${USER_DIRECTORY}/.local/share}"

export BULKBITE_ANDROID_TOOLCHAIN_ROOT="${BULKBITE_ANDROID_TOOLCHAIN_ROOT:-${USER_DATA_DIRECTORY}/poloway-android}"
export JAVA_HOME="${BULKBITE_JAVA_HOME:-${BULKBITE_ANDROID_TOOLCHAIN_ROOT}/jdk}"
export ANDROID_HOME="${BULKBITE_ANDROID_SDK_ROOT:-${BULKBITE_ANDROID_TOOLCHAIN_ROOT}/sdk}"
export ANDROID_SDK_ROOT="${ANDROID_HOME}"
export GRADLE_USER_HOME="${BULKBITE_GRADLE_USER_HOME:-${BULKBITE_ANDROID_TOOLCHAIN_ROOT}/gradle}"
export XDG_CONFIG_HOME="${BULKBITE_XDG_CONFIG_HOME:-${BULKBITE_ANDROID_TOOLCHAIN_ROOT}/xdg/config}"
export XDG_STATE_HOME="${BULKBITE_XDG_STATE_HOME:-${BULKBITE_ANDROID_TOOLCHAIN_ROOT}/xdg/state}"
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:+${JAVA_TOOL_OPTIONS} }-Djavax.net.ssl.trustStore=${JAVA_HOME}/lib/security/cacerts -Djavax.net.ssl.trustStorePassword=changeit"
export PATH="${JAVA_HOME}/bin:${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}"

ANDROID_APPLICATION_ID="za.co.bulkbite.admin"
ANDROID_ACTIVITY="${ANDROID_APPLICATION_ID}/.MainActivity"
DEBUG_APK="${FRONTEND_DIRECTORY}/android/app/build/outputs/apk/debug/app-debug.apk"
RELEASE_BUNDLE="${FRONTEND_DIRECTORY}/android/app/build/outputs/bundle/release/app-release.aab"
GRADLE_WRAPPER="${FRONTEND_DIRECTORY}/android/gradlew"
RELEASE_SIGNING_PROPERTIES="${FRONTEND_DIRECTORY}/android/key.properties"

# endregion ANDROID TOOLCHAIN ENVIRONMENT


# =============================================================================
# region COMMAND STATIONS
# =============================================================================

fail() { printf 'BulkBite Android: %s\n' "$1" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "missing command '$1'"; }
require_file() { [[ -f "$1" ]] || fail "expected file does not exist: $1"; }

run_gradle() {
  (cd "${FRONTEND_DIRECTORY}/android" && printf 'sdk.dir=%s\n' "${ANDROID_HOME}" > local.properties && ./gradlew "$@")
}

sync_production() { (cd "${FRONTEND_DIRECTORY}" && npm run mobile:sync); }

doctor() {
  local status=0
  printf 'BulkBite Android toolchain\n  Root: %s\n  JAVA_HOME: %s\n  Android SDK: %s\n' "${BULKBITE_ANDROID_TOOLCHAIN_ROOT}" "${JAVA_HOME}" "${ANDROID_HOME}"
  for command_name in java javac adb; do
    if command -v "${command_name}" >/dev/null 2>&1; then printf '  %-11s %s\n' "${command_name}:" "$(command -v "${command_name}")"; else printf '  %-11s MISSING\n' "${command_name}:"; status=1; fi
  done
  [[ -x "${GRADLE_WRAPPER}" ]] || status=1
  return "${status}"
}

require_release_signing() {
  require_file "${RELEASE_SIGNING_PROPERTIES}"
  for property_name in storeFile storePassword keyAlias keyPassword; do
    property_value="$(sed -n "s/^${property_name}=//p" "${RELEASE_SIGNING_PROPERTIES}" | tail -n 1)"
    [[ -n "${property_value}" && "${property_value}" != REPLACE_* ]] || fail "release signing property '${property_name}' is missing"
  done
}

build_debug() { sync_production; run_gradle assembleDebug; require_file "${DEBUG_APK}"; printf 'Debug APK: %s\n' "${DEBUG_APK}"; }
build_bundle() { require_release_signing; sync_production; run_gradle bundleRelease; require_file "${RELEASE_BUNDLE}"; printf 'Release bundle: %s\n' "${RELEASE_BUNDLE}"; }
require_device() { require_command adb; adb get-state >/dev/null 2>&1 || fail "no authorized Android device is connected"; }
install_debug() { require_device; require_file "${DEBUG_APK}"; adb install -r "${DEBUG_APK}"; }
launch() { require_device; adb shell am start -n "${ANDROID_ACTIVITY}"; }

# endregion COMMAND STATIONS


# =============================================================================
# region ORCHESTRATION
# =============================================================================

case "${1:-doctor}" in
  doctor) doctor ;;
  sync) sync_production ;;
  sync-production) sync_production ;;
  native-debug) sync_production; run_gradle assembleDebug ;;
  build-debug) build_debug ;;
  build-bundle) build_bundle ;;
  install-debug) install_debug ;;
  launch) launch ;;
  deploy-debug) build_debug; install_debug; launch ;;
  devices) require_command adb; adb devices -l ;;
  pair) [[ -n "${2:-}" ]] || fail "usage: android.sh pair <phone-ip:pairing-port>"; adb pair "$2" ;;
  connect) [[ -n "${2:-}" ]] || fail "usage: android.sh connect <phone-ip:debug-port>"; adb connect "$2" ;;
  *) fail "unknown action '$1'" ;;
esac

# endregion ORCHESTRATION
