import { runtimeConfig } from "@/config/runtime"
import { App as CapacitorApp } from "@capacitor/app"
import { SystemBars, SystemBarsStyle } from "@capacitor/core"
import { Network } from "@capacitor/network"
import { checkNativeProductionAvailability, markNativeOffline } from "@/native/availability"
import { nativeSession, restoreNativeSession } from "@/native/auth"
import { flushOfflineMutations } from "@/native/offlineSync"
export { nativeState } from "@/native/state"
import { nativeState } from "@/native/state"
import { syncOfflineMutation } from "@/resources/api"


// =============================================================================
// region NATIVE LIFECYCLE STATION
// =============================================================================

let nativeBackConsumer = null
let activeNativeSynchronization = null
let lastNativeSynchronizationAt = 0
const NATIVE_SYNCHRONIZATION_FRESHNESS_MS = 15_000

export function registerNativeBackConsumer(consumer) {
  nativeBackConsumer = typeof consumer === "function" ? consumer : null
  return () => {
    if (nativeBackConsumer === consumer) nativeBackConsumer = null
  }
}

export function routeFromAppUrl(value) {
  try {
    const url = new URL(value)
    if (url.protocol === "https:" && url.hostname === "admin.bulkbite.co.za") return `${url.pathname}${url.search}${url.hash}`
    if (url.protocol === `${runtimeConfig.appScheme}:`) {
      if (url.hostname === "open") return url.searchParams.get("path") || "/bulkbite"
      const path = `/${url.hostname}${url.pathname}`.replace(/\/{2,}/g, "/")
      return `${path}${url.search}${url.hash}`
    }
  } catch {}
  return null
}

async function handleAppUrl(value, router) {
  const route = routeFromAppUrl(value)
  if (route?.startsWith("/bulkbite")) await router.replace(route)
}

export async function handleNativeBack(router, exitApp = () => CapacitorApp.exitApp()) {
  if (nativeBackConsumer && await nativeBackConsumer()) return "consumed"
  const currentPath = router.currentRoute?.value?.path || "/bulkbite"
  if (nativeSession.authenticated && currentPath !== "/bulkbite") {
    await router.replace("/bulkbite")
    return "root"
  }
  await exitApp()
  return "exit"
}

export async function synchronizeNativeState({ force = false } = {}) {
	if (!nativeState.connected) return false
	if (activeNativeSynchronization) return activeNativeSynchronization
	if (!force && Date.now() - lastNativeSynchronizationAt < NATIVE_SYNCHRONIZATION_FRESHNESS_MS) return true

	activeNativeSynchronization = runNativeSynchronization().finally(() => {
		lastNativeSynchronizationAt = Date.now()
		activeNativeSynchronization = null
	})
	return activeNativeSynchronization
}

async function runNativeSynchronization() {
	const available = await checkNativeProductionAvailability({ announce: false })
	if (!available) return false
	if (nativeSession.authenticated) await restoreNativeSession().catch(() => {})
	if (nativeSession.authenticated) await flushOfflineMutations(syncOfflineMutation).catch(() => {})
	return true
}

export async function initialiseNativeLifecycle(router) {
  if (!runtimeConfig.isNative) return
  SystemBars.setStyle({ style: SystemBarsStyle.Dark }).catch(() => {})
  const network = await Network.getStatus()
	nativeState.connected = network.connected
	nativeState.connectionType = network.connectionType
	Network.addListener("networkStatusChange", status => {
		const connectionChanged = status.connected !== nativeState.connected || status.connectionType !== nativeState.connectionType
		Object.assign(nativeState, status)
		if (!connectionChanged) return
		if (!status.connected) markNativeOffline()
		else synchronizeNativeState({ force: true }).catch(() => {})
	})
  CapacitorApp.addListener("appUrlOpen", ({ url }) => handleAppUrl(url, router))
  CapacitorApp.addListener("appStateChange", ({ isActive }) => {
		if (isActive) synchronizeNativeState().catch(() => {})
  })
  CapacitorApp.addListener("backButton", () => handleNativeBack(router))
  const launch = await CapacitorApp.getLaunchUrl()
  if (launch?.url) await handleAppUrl(launch.url, router)
}


// endregion NATIVE LIFECYCLE STATION
