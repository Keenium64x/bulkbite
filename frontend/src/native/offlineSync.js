import { runtimeConfig } from "../config/runtime.js"
import { nativeState } from "./state.js"
import { listQueuedMutations, offlineState, queueMutation, removeQueuedMutation, saveSyncOutcome } from "./offlineStore.js"


// =============================================================================
// region OFFLINE MUTATION SYNCHRONIZATION
// =============================================================================


let activeFlush = null

export function createClientMutationId() {
  return globalThis.crypto?.randomUUID?.() || `bb-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export async function syncDraftMutation(callSyncEndpoint, operation, payload, baseModified = null) {
  if (!runtimeConfig.isNative) return { queued: false, result: null }
  const mutation = { clientMutationId: createClientMutationId(), operation, payload, baseModified, createdAt: Date.now(), attempts: 0 }
  if (!nativeState.connected) {
    await queueMutation(mutation)
    return { queued: true, mutation }
  }
  try {
    const response = await callSyncEndpoint(mutation)
    offlineState.lastSyncedAt = Date.now()
    return { queued: false, result: response.result }
  } catch (error) {
    if (isConflict(error)) {
      mutation.conflict = error.message
      await queueMutation(mutation)
      offlineState.conflict = mutation
      return { queued: true, mutation, conflict: true }
    }
    await queueMutation(mutation)
    offlineState.error = "This draft is saved on this device and will sync when BulkBite reconnects."
    return { queued: true, mutation }
  }
}

export async function flushOfflineMutations(callSyncEndpoint) {
  if (!runtimeConfig.isNative || !nativeState.connected) return false
  if (activeFlush) return activeFlush
  activeFlush = runFlush(callSyncEndpoint).finally(() => { activeFlush = null })
  return activeFlush
}

async function runFlush(callSyncEndpoint) {
  offlineState.syncing = true
  offlineState.error = ""
  offlineState.conflict = null
  try {
    const queued = (await listQueuedMutations()).sort((a, b) => a.createdAt - b.createdAt)
    for (const mutation of queued) {
      try {
        const response = await callSyncEndpoint(mutation)
        await saveSyncOutcome(mutation.clientMutationId, { action: "completed", result: response?.result || null })
        offlineState.completedResults[mutation.clientMutationId] = response?.result || null
        await removeQueuedMutation(mutation.clientMutationId)
        offlineState.lastSyncedAt = Date.now()
      } catch (error) {
        if (isConflict(error)) {
          offlineState.conflict = { ...mutation, conflict: error.message }
          return false
        }
        offlineState.error = "BulkBite could not finish synchronizing local drafts. It will try again later."
        return false
      }
    }
    return true
  } finally {
    offlineState.syncing = false
  }
}

export async function resolveOfflineConflict(callSyncEndpoint, action) {
  const mutation = offlineState.conflict
  if (!mutation) return false
  if (action === "server") {
    await saveSyncOutcome(mutation.clientMutationId, { action: "server", result: null })
    await removeQueuedMutation(mutation.clientMutationId)
    offlineState.lastResolution = { clientMutationId: mutation.clientMutationId, action: "server", result: null }
    offlineState.conflict = null
    offlineState.lastSyncedAt = Date.now()
    return true
  }
  if (action === "local") {
    const response = await callSyncEndpoint({ ...mutation, overwriteConflict: true })
    await saveSyncOutcome(mutation.clientMutationId, { action: "local", result: response?.result || null })
    await removeQueuedMutation(mutation.clientMutationId)
    offlineState.lastResolution = { clientMutationId: mutation.clientMutationId, action: "local", result: response?.result || null }
    offlineState.conflict = null
    offlineState.lastSyncedAt = Date.now()
    return true
  }
  return false
}

export function offlineConflictDetails() {
  const conflict = offlineState.conflict
  if (!conflict) return null
  const marker = String(conflict.conflict || "").indexOf("CONFLICT:")
  if (marker < 0) return { operation: conflict.operation, local: conflict.payload, server: null, changedFields: [] }
  try {
    const detail = JSON.parse(String(conflict.conflict).slice(marker + 9).trim())
    const local = conflict.payload || {}
    const server = detail.server || {}
    const changedFields = [...new Set([...Object.keys(local), ...Object.keys(server)])]
      .filter(field => JSON.stringify(local[field]) !== JSON.stringify(server[field]))
      .map(field => ({ field, local: local[field], server: server[field] }))
    return { ...detail, operation: conflict.operation, local, changedFields }
  } catch {
    return { operation: conflict.operation, local: conflict.payload, server: null, changedFields: [] }
  }
}

function isConflict(error) {
  return String(error?.message || "").includes("CONFLICT:")
}


// endregion OFFLINE MUTATION SYNCHRONIZATION
