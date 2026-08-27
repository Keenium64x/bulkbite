import { Capacitor } from "@capacitor/core"


// =============================================================================
// region RUNTIME CONFIGURATION STATION
// =============================================================================

const trimTrailingSlash = value => String(value || "").replace(/\/+$/, "")
const configuredApiUrl = trimTrailingSlash(import.meta.env.VITE_BULKBITE_API_URL)
const configuredWebUrl = trimTrailingSlash(import.meta.env.VITE_BULKBITE_WEB_URL)
const platform = Capacitor.getPlatform()
const isNative = Capacitor.isNativePlatform()

export const runtimeConfig = Object.freeze({
  isNative,
  platform,
  isAndroid: platform === "android",
  isIos: platform === "ios",
  apiBaseUrl: isNative ? configuredApiUrl || "https://admin.bulkbite.co.za" : configuredApiUrl,
  webBaseUrl: configuredWebUrl || configuredApiUrl || "https://admin.bulkbite.co.za",
  appScheme: import.meta.env.VITE_BULKBITE_APP_SCHEME || "bulkbite",
  allowDevelopmentHttp: import.meta.env.VITE_BULKBITE_ALLOW_HTTP === "true",
})

export function absoluteApiUrl(path = "") {
  if (/^https?:\/\//i.test(path)) return path
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  return `${runtimeConfig.apiBaseUrl}${normalizedPath}`
}

export function developmentTunnelHeaders() {
  try {
    const hostname = new URL(runtimeConfig.apiBaseUrl).hostname
    return [".ngrok-free.app", ".ngrok-free.dev"].some(suffix => hostname.endsWith(suffix))
      ? { "ngrok-skip-browser-warning": "bulkbite-mobile" }
      : {}
  } catch {
    return {}
  }
}

export function requireNativeConfiguration() {
  if (!runtimeConfig.isNative) return
  if (!/^https?:\/\//i.test(runtimeConfig.apiBaseUrl)) {
    throw new Error("VITE_BULKBITE_API_URL must be an absolute HTTP(S) URL")
  }
  if (!runtimeConfig.allowDevelopmentHttp && !runtimeConfig.apiBaseUrl.startsWith("https://")) {
    throw new Error("Production mobile builds require an HTTPS BulkBite API URL")
  }
}


// endregion RUNTIME CONFIGURATION STATION
