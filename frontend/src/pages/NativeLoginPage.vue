<script setup>
import { ref } from "vue"
import { SystemFormControl, SystemOperationalButton } from "@/desyium"
import { loginNative } from "@/native/auth"
import { nativeState } from "@/native/lifecycle"


// =============================================================================
// region NATIVE LOGIN GATE
// =============================================================================

const emit = defineEmits(["authenticated"])
const email = ref("")
const password = ref("")
const busy = ref(false)
const error = ref("")

async function submit() {
  if (!email.value || !password.value || busy.value) return
  busy.value = true
  error.value = ""
  try {
    await loginNative(email.value.trim(), password.value)
    emit("authenticated")
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}


// endregion NATIVE LOGIN GATE
</script>

<template>
  <main class="native-login" aria-labelledby="native-login-title">
    <section class="native-login__card">
      <p class="native-login__eyebrow">BulkBite operations</p>
      <h1 id="native-login-title">Sign in</h1>
      <p>Use your BulkBite work account to access stock, receipts, and production.</p>
      <p v-if="!nativeState.connected" class="native-login__notice" role="status">You are offline. Connect to the internet before signing in.</p>
      <p v-if="error" class="native-login__error" role="alert">{{ error }}</p>
      <form @submit.prevent="submit">
        <SystemFormControl v-model="email" type="email" label="Email" autocomplete="username" :disabled="busy" />
        <SystemFormControl v-model="password" type="password" label="Password" autocomplete="current-password" :disabled="busy" />
        <SystemOperationalButton type="submit" variant="solid" :loading="busy" :disabled="busy || !email || !password || !nativeState.connected">Sign in</SystemOperationalButton>
      </form>
    </section>
  </main>
</template>
