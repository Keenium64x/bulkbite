import { runtimeConfig } from "@/config/runtime"
import { App as CapacitorApp } from "@capacitor/app"
import { SystemBars, SystemBarsStyle } from "@capacitor/core"
import { Network } from "@capacitor/network"
import { reactive } from "vue"


// =============================================================================
// region NATIVE LIFECYCLE STATION
// =============================================================================

export const nativeState = reactive({ connected: true, connectionType: "unknown" })

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
  if (route?.startsWith("/bulkbite")) await router.push(route)
}

export async function initialiseNativeLifecycle(router) {
  if (!runtimeConfig.isNative) return
  SystemBars.setStyle({ style: SystemBarsStyle.Dark }).catch(() => {})
  const network = await Network.getStatus()
  nativeState.connected = network.connected
  nativeState.connectionType = network.connectionType
  Network.addListener("networkStatusChange", status => Object.assign(nativeState, status))
  CapacitorApp.addListener("appUrlOpen", ({ url }) => handleAppUrl(url, router))
  CapacitorApp.addListener("backButton", async ({ canGoBack }) => {
    if (canGoBack && window.history.length > 1) router.back()
    else await CapacitorApp.exitApp()
  })
  const launch = await CapacitorApp.getLaunchUrl()
  if (launch?.url) await handleAppUrl(launch.url, router)
}


// endregion NATIVE LIFECYCLE STATION
