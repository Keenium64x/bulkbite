import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"

const source = path => readFileSync(new URL(path, import.meta.url), "utf8")

test("native Capacitor shell is bundled and does not load a remote server URL", () => {
  const config = source("../capacitor.config.ts")
  assert.doesNotMatch(config, /server:\s*\{[^}]*url:/s)
  assert.match(config, /webDir:\s*"dist-mobile"/)
  assert.match(config, /hostname:\s*"localhost"/)
})

test("native API origin remains locked to live production", () => {
  const runtime = source("../src/config/runtime.js")
  assert.match(runtime, /PRODUCTION_ORIGIN\s*=\s*"https:\/\/admin\.bulkbite\.co\.za"/)
  assert.match(runtime, /apiBaseUrl:\s*isNative\s*\?\s*PRODUCTION_ORIGIN/)
  assert.match(runtime, /requestedUrl\.pathname/)
})

test("availability gate distinguishes offline and unavailable production", () => {
  const availability = source("../src/native/availability.js")
  assert.match(availability, /if \(!network\.connected\)/)
  assert.match(availability, /markNativeOffline\(\)/)
  assert.match(availability, /payload\.message !== "pong"/)
  assert.match(availability, /markNativeServerUnavailable\(\)/)
})

test("ordinary API responses are not classified as a server outage", () => {
  const availability = source("../src/native/availability.js")
  assert.match(availability, /new Set\(\[408, 429, 502, 503, 504\]\)/)
  assert.match(availability, /else markNativeServerReachable\(\)/)
})

test("native login sends only network and gateway failures to outage recovery", () => {
  const auth = source("../src/native/auth.js")
  assert.match(auth, /catch \(error\) \{\s*markNativeServerUnavailable\(\)/)
  assert.match(auth, /if \(isUnavailableHttpStatus\(response\.status\)\) markNativeServerUnavailable\(\)/)
  assert.match(auth, /else noteNativeResponse\(response\)/)
})

test("recovery state supplies plain copy, production host, and retry", () => {
  const block = source("../src/blocks/native-availability-state/NativeAvailabilityState.vue")
  assert.match(block, /BulkBite is temporarily unavailable/)
  assert.match(block, /Your data has not been changed/)
  assert.match(block, /Production server:/)
  assert.match(block, /Try again/)
  assert.match(block, /aria-live="polite"/)
})
