import { Capacitor } from "@capacitor/core"


// =============================================================================
// region RUNTIME CONFIGURATION STATION
// =============================================================================

const platform = Capacitor.getPlatform()
const isNative = Capacitor.isNativePlatform()
export const PRODUCTION_ORIGIN = "https://admin.huispunte.co.za"

export const runtimeConfig = Object.freeze({
  isNative,
  platform,
  isAndroid: platform === "android",
  isIos: platform === "ios",
  apiBaseUrl: isNative ? PRODUCTION_ORIGIN : "",
  webBaseUrl: isNative ? PRODUCTION_ORIGIN : window.location.origin,
  appScheme: isNative ? "bulkbite" : import.meta.env.VITE_BULKBITE_APP_SCHEME || "bulkbite",
})

export function absoluteApiUrl(path = "") {
  if (/^https?:\/\//i.test(path)) {
    if (!runtimeConfig.isNative) return path
    const requestedUrl = new URL(path)
    return `${PRODUCTION_ORIGIN}${requestedUrl.pathname}${requestedUrl.search}${requestedUrl.hash}`
  }
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  return `${runtimeConfig.apiBaseUrl}${normalizedPath}`
}

export function requireNativeConfiguration() {
  if (!runtimeConfig.isNative) return
  if (runtimeConfig.apiBaseUrl !== PRODUCTION_ORIGIN || runtimeConfig.webBaseUrl !== PRODUCTION_ORIGIN) {
    throw new Error("The installed BulkBite app must use the production origin")
  }
}


// endregion RUNTIME CONFIGURATION STATION
