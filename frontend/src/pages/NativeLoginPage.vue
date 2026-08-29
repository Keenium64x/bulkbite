<script setup>
import { onMounted, ref, watch } from "vue"
import { SystemFormControl, SystemLogo, SystemOperationalButton } from "@/desyium"
import bulkbiteIcon from "@/assets/bulkbite-icon.svg"
import { loginNative } from "@/native/auth"
import { nativeState } from "@/native/lifecycle"


// =============================================================================
// region NATIVE LOGIN GATE
// =============================================================================

const emit = defineEmits(["authenticated"])
const LOGIN_DRAFT_KEY = "bulkbite-native-login-email"
const email = ref("")
const password = ref("")
const busy = ref(false)
const error = ref("")

onMounted(() => {
  email.value = window.localStorage.getItem(LOGIN_DRAFT_KEY) || ""
})

watch(email, value => {
  const normalized = String(value || "").trim()
  if (normalized) window.localStorage.setItem(LOGIN_DRAFT_KEY, normalized)
  else window.localStorage.removeItem(LOGIN_DRAFT_KEY)
})

async function submit() {
  if (!email.value || !password.value || busy.value) return
  busy.value = true
  error.value = ""
  try {
    await loginNative(email.value.trim(), password.value)
    window.localStorage.removeItem(LOGIN_DRAFT_KEY)
    password.value = ""
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
  <main class="native-login" data-native-pull-ignore aria-labelledby="native-login-title">
    <section class="native-login__card">
      <SystemLogo class="native-login__logo" name="BulkBite" :src="bulkbiteIcon" href="#/bulkbite" compact />
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

<style scoped>
.native-login__logo{width:4rem;min-height:0;margin-bottom:var(--spacing-s)}
.native-login__logo :deep(.system-logo__mark){width:100%;height:auto}
</style>
