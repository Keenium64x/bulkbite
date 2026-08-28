import { absoluteApiUrl, runtimeConfig } from "@/config/runtime"
import { readSecureValue, removeSecureValue, writeSecureValue } from "@/native/secureStore"
import { isUnavailableHttpStatus, markNativeServerUnavailable, noteNativeResponse } from "@/native/availability"


// =============================================================================
// region NATIVE JWT SESSION STATION
// =============================================================================

const TOKEN_KEY = "tokens"
const EXPIRY_SKEW_MS = 60_000
export const MOBILE_AUTH_SCHEME = "BulkBite"
let refreshRequest = null
let volatileTokens = null

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
    throw error
  }
  if (isUnavailableHttpStatus(response.status)) markNativeServerUnavailable()
  else noteNativeResponse(response)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.exc_type || payload.exception) {
    throw new Error(payload.message || (method === "login_mobile" ? "Your email or password is incorrect." : "Your mobile session has expired. Sign in again."))
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
  return payload
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
      await clearNativeTokens()
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
}


// endregion NATIVE JWT SESSION STATION
