import { runtimeConfig } from "@/config/runtime"
import { nativeState } from "@/native/lifecycle"
import { listQueuedMutations, offlineState, queueMutation, removeQueuedMutation } from "@/native/offlineStore"


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
      throw error
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
        await callSyncEndpoint(mutation)
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
    await removeQueuedMutation(mutation.clientMutationId)
    offlineState.conflict = null
    return true
  }
  if (action === "local") {
    await callSyncEndpoint({ ...mutation, overwriteConflict: true })
    await removeQueuedMutation(mutation.clientMutationId)
    offlineState.conflict = null
    return true
  }
  return false
}

function isConflict(error) {
  return String(error?.message || "").includes("CONFLICT:")
}


// endregion OFFLINE MUTATION SYNCHRONIZATION
