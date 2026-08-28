import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

const source = readFileSync(new URL("../src/native/auth.js", import.meta.url), "utf8")

test("native session restoration validates the current server identity", () => {
  assert.match(source, /export async function restoreNativeSession\(\)/)
  assert.match(source, /getNativeAccessToken\(\)/)
  assert.match(source, /frappe\.auth\.get_logged_user/)
  assert.match(source, /Authorization: `\$\{MOBILE_AUTH_SCHEME\} \$\{accessToken\}`/)
  assert.match(source, /user === "Guest"/)
})

test("temporary production outages preserve secure refresh credentials", () => {
  assert.match(source, /if \(error\?\.invalidSession\) await clearNativeTokens\(\)/)
  assert.doesNotMatch(source, /\.catch\(async error => \{\s*await clearNativeTokens\(\)\s*throw error/s)
  assert.match(source, /MobileAuthRequestError\([^)]*\{ unavailable: true \}\)/s)
})

test("only rejected credentials clear a restored native session", () => {
  assert.match(source, /const INVALID_SESSION_STATUSES = new Set\(\[401, 403\]\)/)
  assert.match(source, /if \(error\?\.invalidSession\) \{\s*await clearNativeTokens\(\)/s)
  assert.match(source, /nativeSession\.authenticated = Boolean/)
})

test("explicit logout still revokes the token family and clears local storage", () => {
  assert.match(source, /postMobileAuth\("logout_mobile"/)
  assert.match(source, /removeSecureValue\(TOKEN_KEY\)/)
  assert.match(source, /setNativeSession\(""\)/)
})
