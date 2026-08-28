import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

const lifecycle = readFileSync(new URL("../src/native/lifecycle.js", import.meta.url), "utf8")
const app = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8")
const login = readFileSync(new URL("../src/pages/NativeLoginPage.vue", import.meta.url), "utf8")

test("Android Back does not traverse WebView history", () => {
  assert.match(lifecycle, /export async function handleNativeBack/)
  assert.doesNotMatch(lifecycle, /router\.back\(\)/)
  assert.doesNotMatch(lifecycle, /window\.history\.length/)
})

test("Back closes transient UI, returns auxiliary routes to app root, then exits", () => {
  assert.match(lifecycle, /nativeBackConsumer && await nativeBackConsumer\(\)/)
  assert.match(lifecycle, /currentPath !== "\/bulkbite"/)
  assert.match(lifecycle, /router\.replace\("\/bulkbite"\)/)
  assert.match(lifecycle, /await exitApp\(\)/)
})

test("successful native login replaces the current entry and never stores a password", () => {
  assert.match(app, /handleNativeAuthenticated[\s\S]*router\.replace\("\/bulkbite"\)/)
  assert.doesNotMatch(login, /localStorage|sessionStorage|writeSecureValue/)
})

test("native resume revalidates the secure server session", () => {
  assert.match(lifecycle, /appStateChange/)
  assert.match(lifecycle, /if \(isActive\) restoreSessionAfterResume\(\)/)
  assert.match(lifecycle, /await restoreNativeSession\(\)/)
})
