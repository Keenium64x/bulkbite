import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

const controller = readFileSync(new URL("../src/native/pullToRefresh.js", import.meta.url), "utf8")
const shell = readFileSync(new URL("../src/blocks/bulkbite-app-shell/BulkbiteAppShell.vue", import.meta.url), "utf8")
const app = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8")
const indicator = readFileSync(new URL("../src/components/native/NativePullToRefresh.vue", import.meta.url), "utf8")

test("pull refresh only starts in native mode at the top scroll boundary", () => {
  assert.match(controller, /!runtimeConfig\.isNative/)
  assert.match(controller, /isScrollSurfaceAtTop\(scrollSurface\)/)
  assert.match(controller, /verticalDistance <= 0/)
  assert.match(controller, /horizontalDistance > Math\.max/)
})

test("sub-threshold pulls reset without refreshing", () => {
  assert.match(controller, /const shouldRefresh = pullToRefreshArmed\.value/)
  assert.match(controller, /if \(!shouldRefresh\) \{\s*resetPull\(\)\s*return false/s)
})

test("an armed pull runs one existing workflow refresh at a time", () => {
  assert.match(controller, /activeRefresh \|\|=/)
  assert.match(app, /:refresh-action="refreshWorkspaceManually"/)
  assert.match(shell, /useNativePullToRefresh\(refreshCurrentWorkflow\)/)
  assert.match(controller, /bulkbite:native-refresh-replay/)
})

test("the native indicator reports pull, release, success, and failure states", () => {
  assert.match(indicator, /Pull to refresh/)
  assert.match(indicator, /Release to refresh/)
  assert.match(indicator, /BulkBite is up to date/)
  assert.match(indicator, /Refresh failed/)
  assert.match(indicator, /aria-live="polite"/)
})
