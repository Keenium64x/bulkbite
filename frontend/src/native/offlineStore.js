import { reactive } from "vue"


// =============================================================================
// region INDEXEDDB OFFLINE DRAFT STORE
// =============================================================================


const DATABASE_NAME = "bulkbite-offline"
const DATABASE_VERSION = 1
const QUEUE_STORE = "mutation-queue"
const DRAFT_STORE = "form-drafts"

export const offlineState = reactive({ pending: 0, syncing: false, conflict: null, lastSyncedAt: null, error: "" })

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(QUEUE_STORE)) database.createObjectStore(QUEUE_STORE, { keyPath: "clientMutationId" })
      if (!database.objectStoreNames.contains(DRAFT_STORE)) database.createObjectStore(DRAFT_STORE, { keyPath: "key" })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function runTransaction(storeName, mode, operation) {
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, mode)
    const request = operation(transaction.objectStore(storeName))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => database.close()
  })
}

export async function saveFormDraft(key, value) {
  await runTransaction(DRAFT_STORE, "readwrite", store => store.put({ key, value, savedAt: Date.now() }))
}

export async function loadFormDraft(key) {
  return (await runTransaction(DRAFT_STORE, "readonly", store => store.get(key)))?.value || null
}

export async function clearFormDraft(key) {
  await runTransaction(DRAFT_STORE, "readwrite", store => store.delete(key))
}

export async function queueMutation(mutation) {
  await runTransaction(QUEUE_STORE, "readwrite", store => store.put(mutation))
  await refreshPendingCount()
  return mutation
}

export async function listQueuedMutations() {
  return runTransaction(QUEUE_STORE, "readonly", store => store.getAll())
}

export async function removeQueuedMutation(clientMutationId) {
  await runTransaction(QUEUE_STORE, "readwrite", store => store.delete(clientMutationId))
  await refreshPendingCount()
}

export async function refreshPendingCount() {
  offlineState.pending = await runTransaction(QUEUE_STORE, "readonly", store => store.count()).catch(() => 0)
  return offlineState.pending
}


// endregion INDEXEDDB OFFLINE DRAFT STORE
