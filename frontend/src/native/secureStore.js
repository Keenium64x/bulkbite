import { runtimeConfig } from "@/config/runtime"
import { KeychainAccess, SecureStorage } from "@aparajita/capacitor-secure-storage"


// =============================================================================
// region NATIVE SECURE STORAGE STATION
// =============================================================================

let configuredStore = null

async function ensureConfiguredStore() {
  if (!runtimeConfig.isNative) throw new Error("Secure credentials are only available in the native app")
  if (!configuredStore) {
    configuredStore = Promise.all([
      SecureStorage.setKeyPrefix("bulkbite_auth_"),
      SecureStorage.setSynchronize(false),
      SecureStorage.setDefaultKeychainAccess(KeychainAccess.whenUnlockedThisDeviceOnly),
    ])
  }
  await configuredStore
}

export async function readSecureValue(key) {
  await ensureConfiguredStore()
  return SecureStorage.get(key)
}

export async function writeSecureValue(key, value) {
  await ensureConfiguredStore()
  await SecureStorage.set(key, value)
}

export async function removeSecureValue(key) {
  await ensureConfiguredStore()
  await SecureStorage.remove(key)
}


// endregion NATIVE SECURE STORAGE STATION
