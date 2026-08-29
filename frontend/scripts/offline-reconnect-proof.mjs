import assert from "node:assert/strict"


// =============================================================================
// region INDEXEDDB AND RECONNECT PROOF
// =============================================================================


const stores = new Map()
const request = operation => {
  const result = {}
  queueMicrotask(() => {
    try { result.result = operation(); result.onsuccess?.() }
    catch (error) { result.error = error; result.onerror?.() }
  })
  return result
}

globalThis.indexedDB = {
  open() {
    const openRequest = {}
    queueMicrotask(() => {
      const database = {
        objectStoreNames: { contains: name => stores.has(name) },
        createObjectStore(name) { if (!stores.has(name)) stores.set(name, new Map()) },
        transaction(name) {
          const transaction = { oncomplete: null }
          transaction.objectStore = () => ({
            put: value => request(() => { stores.get(name).set(value.clientMutationId || value.key, structuredClone(value)); queueMicrotask(() => transaction.oncomplete?.()); return value }),
            get: key => request(() => stores.get(name).get(key)),
            getAll: () => request(() => [...stores.get(name).values()].map(value => structuredClone(value))),
            delete: key => request(() => { stores.get(name).delete(key); queueMicrotask(() => transaction.oncomplete?.()) }),
            count: () => request(() => stores.get(name).size),
          })
          return transaction
        },
        close() {},
      }
      openRequest.result = database
      openRequest.onupgradeneeded?.()
      openRequest.onsuccess?.()
    })
    return openRequest
  },
}
globalThis.Capacitor = { getPlatform: () => "android", isNativePlatform: () => true, Plugins: {} }
globalThis.CapacitorCustomPlatform = { name: "android" }
globalThis.window = { location: { origin: "https://admin.bulkbite.co.za" }, addEventListener() {}, removeEventListener() {}, Capacitor: globalThis.Capacitor }
globalThis.document = { createElement: () => ({ content: {}, style: {}, setAttribute() {} }), documentElement: { classList: { toggle() {} }, style: { setProperty() {} }, dataset: {} }, body: { classList: { toggle() {} } } }

const { nativeState } = await import("../src/native/state.js")
const store = await import("../src/native/offlineStore.js")
const sync = await import("../src/native/offlineSync.js")

nativeState.connected = false
const payload = { plan_title: "Offline proof", customer_mix: [{ plan_type: "Standard", customer_count: 40 }] }
const saved = await sync.syncDraftMutation(async () => { throw new Error("The server must not be called while disconnected.") }, "save_production_plan", payload)
assert.equal(saved.queued, true)
assert.equal((await store.listQueuedMutations()).length, 1)
await store.saveFormDraft("production-plan", { payload, queuedMutationId: saved.mutation.clientMutationId })

const restartedStore = await import(`../src/native/offlineStore.js?restart=${Date.now()}`)
assert.deepEqual((await restartedStore.loadFormDraft("production-plan")).payload, payload)
assert.equal((await restartedStore.listQueuedMutations()).length, 1)

nativeState.connected = true
let writes = 0
let serverRecord = null
const exactOnceServer = async mutation => {
  writes += 1
  serverRecord ||= { name: "PLAN-001", ...mutation.payload }
  return { result: serverRecord }
}
assert.equal(await sync.flushOfflineMutations(exactOnceServer), true)
assert.equal(writes, 1)
assert.equal((await store.listQueuedMutations()).length, 0)
assert.deepEqual((await store.loadSyncOutcome(saved.mutation.clientMutationId)).result, serverRecord)
assert.equal(await sync.flushOfflineMutations(exactOnceServer), true)
assert.equal(writes, 1)

const conflictMutation = { clientMutationId: "conflict-device", operation: "save_production_plan", payload: { name: "PLAN-001", plan_title: "Device version" }, baseModified: "old", createdAt: Date.now() }
await store.queueMutation(conflictMutation)
const conflictEndpoint = async mutation => {
  if (!mutation.overwriteConflict) throw new Error('CONFLICT: {"server":{"name":"PLAN-001","plan_title":"Server version"}}')
  return { result: { ...mutation.payload, modified: "new" } }
}
await sync.flushOfflineMutations(conflictEndpoint)
assert.equal(store.offlineState.conflict.clientMutationId, conflictMutation.clientMutationId)
assert.equal(await sync.resolveOfflineConflict(conflictEndpoint, "server"), true)
assert.equal((await store.listQueuedMutations()).length, 0)
assert.equal((await store.loadSyncOutcome(conflictMutation.clientMutationId)).action, "server")

const deviceMutation = { ...conflictMutation, clientMutationId: "conflict-device-wins", createdAt: Date.now() + 1 }
await store.queueMutation(deviceMutation)
await sync.flushOfflineMutations(conflictEndpoint)
assert.equal(await sync.resolveOfflineConflict(conflictEndpoint, "local"), true)
assert.equal((await store.loadSyncOutcome(deviceMutation.clientMutationId)).action, "local")
assert.equal((await store.listQueuedMutations()).length, 0)

console.log("Offline reconnect proof passed: persisted restart, exact-once replay, server-wins, and device-wins.")


// endregion INDEXEDDB AND RECONNECT PROOF
