import { runtimeConfig } from "@/config/runtime"
import { App as CapacitorApp } from "@capacitor/app"
import { SystemBars, SystemBarsStyle } from "@capacitor/core"
import { Network } from "@capacitor/network"
import { reactive } from "vue"
import { checkNativeProductionAvailability, markNativeOffline } from "@/native/availability"
import { nativeSession, restoreNativeSession } from "@/native/auth"


// =============================================================================
// region NATIVE LIFECYCLE STATION
// =============================================================================

export const nativeState = reactive({ connected: true, connectionType: "unknown" })
let nativeBackConsumer = null

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

async function restoreSessionAfterResume() {
  if (!nativeState.connected) return
  const available = await checkNativeProductionAvailability({ force: true })
  if (!available) return
  await restoreNativeSession().catch(() => {})
}

export async function initialiseNativeLifecycle(router) {
  if (!runtimeConfig.isNative) return
  SystemBars.setStyle({ style: SystemBarsStyle.Dark }).catch(() => {})
  const network = await Network.getStatus()
  nativeState.connected = network.connected
  nativeState.connectionType = network.connectionType
  Network.addListener("networkStatusChange", status => {
    Object.assign(nativeState, status)
    if (!status.connected) markNativeOffline()
    else checkNativeProductionAvailability({ force: true })
  })
  CapacitorApp.addListener("appUrlOpen", ({ url }) => handleAppUrl(url, router))
  CapacitorApp.addListener("appStateChange", ({ isActive }) => {
    if (isActive) restoreSessionAfterResume()
  })
  CapacitorApp.addListener("backButton", () => handleNativeBack(router))
  const launch = await CapacitorApp.getLaunchUrl()
  if (launch?.url) await handleAppUrl(launch.url, router)
}


// endregion NATIVE LIFECYCLE STATION
