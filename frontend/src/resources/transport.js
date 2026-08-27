import { absoluteApiUrl, developmentTunnelHeaders, runtimeConfig } from "@/config/runtime"
import { MOBILE_AUTH_SCHEME, getNativeAccessToken } from "@/native/auth"


// =============================================================================
// region FRAPPE TRANSPORT STATION
// =============================================================================

export function resolveRequestUrl(url) {
  if (!url) throw new Error("A request URL is required")
  const path = url.startsWith("/") || /^https?:\/\//i.test(url) ? url : `/api/method/${url}`
  return runtimeConfig.isNative ? absoluteApiUrl(path) : path
}

export async function buildRequestHeaders(headers = {}, { json = true } = {}) {
  const nextHeaders = { Accept: "application/json", ...(json ? { "Content-Type": "application/json; charset=utf-8" } : {}), ...headers }
  if (runtimeConfig.isNative) {
    Object.assign(nextHeaders, developmentTunnelHeaders())
    const token = await getNativeAccessToken()
    if (token) nextHeaders.Authorization = `${MOBILE_AUTH_SCHEME} ${token}`
  } else {
    nextHeaders["X-Frappe-Site-Name"] = window.site_name || window.location.hostname
    const csrfToken = window.csrf_token || window.boot?.csrf_token
    if (csrfToken && csrfToken !== "{{ csrf_token }}") nextHeaders["X-Frappe-CSRF-Token"] = csrfToken
  }
  return nextHeaders
}

export async function authenticatedFetch(url, options = {}, retry = true) {
  const bodyIsForm = options.body instanceof FormData
  const headers = await buildRequestHeaders(options.headers || {}, { json: options.body != null && !bodyIsForm })
  let response
  try {
    response = await fetch(resolveRequestUrl(url), {
      ...options,
      headers,
      credentials: runtimeConfig.isNative ? "omit" : "same-origin",
    })
  } catch (error) {
    if (shouldRetryNativeRead(options, retry)) {
      await new Promise(resolve => window.setTimeout(resolve, 350))
      return authenticatedFetch(url, options, false)
    }
    throw error
  }
  if (runtimeConfig.isNative && response.status === 401 && retry) {
    const token = await getNativeAccessToken({ forceRefresh: true })
    if (token) return authenticatedFetch(url, options, false)
  }
  if (shouldRetryNativeRead(options, retry) && [408, 429, 502, 503, 504].includes(response.status)) {
    await new Promise(resolve => window.setTimeout(resolve, 350))
    return authenticatedFetch(url, options, false)
  }
  return response
}

function shouldRetryNativeRead(options, retry) {
  return runtimeConfig.isNative && retry && String(options.method || "GET").toUpperCase() === "GET"
}


// endregion FRAPPE TRANSPORT STATION
