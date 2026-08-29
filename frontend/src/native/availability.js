import { reactive } from "vue"
import { Network } from "@capacitor/network"
import { absoluteApiUrl, runtimeConfig } from "@/config/runtime"


// =============================================================================
// region PRODUCTION AVAILABILITY STATION
// =============================================================================

const UNAVAILABLE_HTTP_STATUSES = new Set([408, 429, 502, 503, 504])
let activeHealthCheck = null

export const nativeAvailability = reactive({
  status: runtimeConfig.isNative ? "checking" : "available",
  checking: runtimeConfig.isNative,
  lastCheckedAt: null,
})

export const productionHost = new URL(runtimeConfig.webBaseUrl).host

export function isUnavailableHttpStatus(status) {
  return UNAVAILABLE_HTTP_STATUSES.has(Number(status))
}

export function markNativeOffline() {
  if (!runtimeConfig.isNative) return
  nativeAvailability.status = "offline"
  nativeAvailability.checking = false
}

export function markNativeServerUnavailable() {
  if (!runtimeConfig.isNative) return
  nativeAvailability.status = "server-unavailable"
  nativeAvailability.checking = false
}

export function markNativeServerReachable() {
  if (!runtimeConfig.isNative) return
  nativeAvailability.status = "available"
  nativeAvailability.checking = false
  nativeAvailability.lastCheckedAt = Date.now()
}

export function noteNativeResponse(response) {
  if (!runtimeConfig.isNative) return
  if (isUnavailableHttpStatus(response?.status)) markNativeServerUnavailable()
  else markNativeServerReachable()
}

export async function checkNativeProductionAvailability({ force = false, announce = true } = {}) {
	if (!runtimeConfig.isNative) return true
	if (activeHealthCheck && !force) return activeHealthCheck

	if (announce) {
		nativeAvailability.checking = true
		nativeAvailability.status = "checking"
	}
	activeHealthCheck = runHealthCheck({ announce }).finally(() => { activeHealthCheck = null })
	return activeHealthCheck
}

async function runHealthCheck({ announce = true } = {}) {
	const network = await Network.getStatus().catch(() => ({ connected: true }))
	if (!network.connected) {
		if (announce) markNativeOffline()
		return false
	}

  try {
    const response = await fetch(absoluteApiUrl("/api/method/ping"), {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
		const payload = await response.json().catch(() => ({}))
		if (!response.ok || payload.message !== "pong") {
			if (announce) markNativeServerUnavailable()
			return false
		}
		markNativeServerReachable()
		return true
	} catch {
		if (announce) markNativeServerUnavailable()
		return false
	}
}


// endregion PRODUCTION AVAILABILITY STATION
