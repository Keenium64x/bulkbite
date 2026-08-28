import { absoluteApiUrl, runtimeConfig } from "@/config/runtime"
import { readSecureValue, removeSecureValue, writeSecureValue } from "@/native/secureStore"
import { isUnavailableHttpStatus, markNativeServerUnavailable, noteNativeResponse } from "@/native/availability"
import { reactive } from "vue"


// =============================================================================
// region NATIVE JWT SESSION STATION
// =============================================================================

const TOKEN_KEY = "tokens"
const EXPIRY_SKEW_MS = 60_000
const INVALID_SESSION_STATUSES = new Set([401, 403])
export const MOBILE_AUTH_SCHEME = "BulkBite"
let refreshRequest = null
let volatileTokens = null

export const nativeSession = reactive({
  ready: !runtimeConfig.isNative,
  authenticated: !runtimeConfig.isNative,
  user: "",
})

class MobileAuthRequestError extends Error {
  constructor(message, { status = 0, unavailable = false } = {}) {
    super(message)
    this.name = "MobileAuthRequestError"
    this.status = Number(status)
    this.invalidSession = INVALID_SESSION_STATUSES.has(this.status)
    this.unavailable = unavailable
  }
}

async function postMobileAuth(method, values) {
  let response
  try {
    response = await fetch(absoluteApiUrl(`/api/method/bulkbite.mobile.${method}`), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify(values),
    })
  } catch (error) {
    markNativeServerUnavailable()
    throw new MobileAuthRequestError(error.message || "BulkBite could not reach the production server.", { unavailable: true })
  }
  if (isUnavailableHttpStatus(response.status)) markNativeServerUnavailable()
  else noteNativeResponse(response)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.exc_type || payload.exception) {
    throw new MobileAuthRequestError(
      payload.message || (method === "login_mobile" ? "Your email or password is incorrect." : "Your mobile session has expired. Sign in again."),
      { status: response.status, unavailable: isUnavailableHttpStatus(response.status) },
    )
  }
  return payload.message || payload
}

async function storeTokenResponse(payload) {
  if (!payload?.access_token || !payload?.refresh_token) throw new Error("BulkBite returned an incomplete mobile session")
  const tokens = {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    tokenType: payload.token_type || MOBILE_AUTH_SCHEME,
    expiresAt: Date.now() + Number(payload.expires_in || 900) * 1000,
  }
  volatileTokens = tokens
  await writeSecureValue(TOKEN_KEY, tokens).catch(() => {})
  return tokens
}

async function readTokenPair() {
  if (volatileTokens?.accessToken) return volatileTokens
  try {
    const tokens = await readSecureValue(TOKEN_KEY)
    if (tokens?.accessToken) volatileTokens = tokens
    return tokens
  } catch {
    return null
  }
}

export async function loginNative(email, password) {
  if (!runtimeConfig.isNative) throw new Error("Native authentication is only available in the installed app")
  const payload = await postMobileAuth("login_mobile", {
    email,
    password,
    device_name: `${runtimeConfig.platform} BulkBite Admin app`,
  })
  await storeTokenResponse(payload)
  setNativeSession(payload.user)
  return payload
}

export async function restoreNativeSession() {
  if (!runtimeConfig.isNative) return { user: window.boot?.user || "" }
  nativeSession.ready = false
  try {
    const accessToken = await getNativeAccessToken()
    if (!accessToken) {
      setNativeSession("")
      return null
    }
    const user = await validateNativeIdentity(accessToken)
    setNativeSession(user)
    return { user }
  } catch (error) {
    if (error?.invalidSession) {
      await clearNativeTokens()
      setNativeSession("")
      return null
    }
    throw error
  } finally {
    nativeSession.ready = true
  }
}

export async function getNativeAccessToken({ forceRefresh = false } = {}) {
  if (!runtimeConfig.isNative) return null
  const tokens = await readTokenPair()
  if (!tokens?.accessToken) return null
  if (!forceRefresh && Number(tokens.expiresAt) > Date.now() + EXPIRY_SKEW_MS) return tokens.accessToken
  if (!tokens.refreshToken) {
    await clearNativeTokens()
    return null
  }
  return refreshNativeAccessToken(tokens.refreshToken)
}

async function refreshNativeAccessToken(refreshToken) {
  if (refreshRequest) return refreshRequest
  refreshRequest = postMobileAuth("refresh_mobile_session", { refresh_token: refreshToken })
    .then(storeTokenResponse)
    .then(tokens => tokens.accessToken)
    .catch(async error => {
      if (error?.invalidSession) await clearNativeTokens()
      throw error
    })
    .finally(() => { refreshRequest = null })
  return refreshRequest
}

export async function clearNativeTokens({ revoke = false } = {}) {
  if (!runtimeConfig.isNative) return
  const tokens = await readTokenPair()
  if (revoke && tokens?.refreshToken) {
    await postMobileAuth("logout_mobile", { refresh_token: tokens.refreshToken }).catch(() => {})
  }
  volatileTokens = null
  await removeSecureValue(TOKEN_KEY).catch(() => {})
  setNativeSession("")
}

async function validateNativeIdentity(accessToken) {
  let response
  try {
    response = await fetch(absoluteApiUrl("/api/method/frappe.auth.get_logged_user"), {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `${MOBILE_AUTH_SCHEME} ${accessToken}`,
      },
      cache: "no-store",
    })
  } catch (error) {
    markNativeServerUnavailable()
    throw new MobileAuthRequestError(error.message || "BulkBite could not validate this device session.", { unavailable: true })
  }
  if (isUnavailableHttpStatus(response.status)) markNativeServerUnavailable()
  else noteNativeResponse(response)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.exc_type || payload.exception) {
    throw new MobileAuthRequestError(payload.message || "Your mobile session could not be validated.", {
      status: response.status,
      unavailable: isUnavailableHttpStatus(response.status),
    })
  }
  const user = String(payload.message || "").trim()
  if (!user || user === "Guest") {
    throw new MobileAuthRequestError("Your mobile session has expired. Sign in again.", { status: 401 })
  }
  return user
}

function setNativeSession(user) {
  nativeSession.user = String(user || "")
  nativeSession.authenticated = Boolean(nativeSession.user && nativeSession.user !== "Guest")
}


// endregion NATIVE JWT SESSION STATION
