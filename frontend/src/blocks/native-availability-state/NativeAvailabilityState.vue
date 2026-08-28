<script setup>
import { computed } from "vue"
import { RefreshCw, ServerOff, WifiOff } from "lucide-vue-next"
import { SystemCard, SystemLogo, SystemOperationalButton } from "@/desyium"
import bulkbiteWordmarkDark from "@/assets/bulkbite-logo-wordmark-dark.svg"


// =============================================================================
// region AVAILABILITY PRESENTATION STATION
// =============================================================================

const props = defineProps({
  status: { type: String, required: true },
  productionHost: { type: String, required: true },
  checking: { type: Boolean, default: false },
})

defineEmits(["retry"])

const content = computed(() => {
  if (props.status === "offline") return {
    icon: WifiOff,
    eyebrow: "Connection unavailable",
    title: "This device is offline",
    description: "Reconnect to the internet, then try again. Your BulkBite data has not been changed.",
  }
  if (props.status === "checking") return {
    icon: RefreshCw,
    eyebrow: "Production connection",
    title: "Checking BulkBite",
    description: "The app is checking the production server before loading your work.",
  }
  return {
    icon: ServerOff,
    eyebrow: "Server unavailable",
    title: "BulkBite is temporarily unavailable",
    description: "The BulkBite production server could not be reached. Your data has not been changed.",
  }
})


// endregion AVAILABILITY PRESENTATION STATION
</script>

<template>
  <main data-block="native-availability-state" class="native-availability" aria-labelledby="native-availability-title">
    <SystemCard class="native-availability__card" role="status" aria-live="polite">
      <SystemLogo class="native-availability__logo" name="BulkBite" :src="bulkbiteWordmarkDark" href="#/bulkbite" compact />
      <div class="native-availability__state-icon" aria-hidden="true">
        <component :is="content.icon" :class="{ 'is-checking': status === 'checking' }" />
      </div>
      <p class="native-availability__eyebrow">{{ content.eyebrow }}</p>
      <h1 id="native-availability-title">{{ content.title }}</h1>
      <p class="native-availability__description">{{ content.description }}</p>
      <SystemOperationalButton
        class="native-availability__retry"
        theme="blue"
        :loading="checking"
        :disabled="checking"
        @click="$emit('retry')"
      >
        <RefreshCw v-if="!checking" aria-hidden="true" />
        {{ checking ? "Checking server" : "Try again" }}
      </SystemOperationalButton>
      <p class="native-availability__host">Production server: <strong>{{ productionHost }}</strong></p>
    </SystemCard>
  </main>
</template>

<style scoped>
.native-availability{display:grid;width:100%;max-width:100%;min-height:100dvh;overflow:hidden;padding:max(var(--spacing-l),env(safe-area-inset-top)) max(var(--spacing-l),env(safe-area-inset-right)) max(var(--spacing-l),env(safe-area-inset-bottom)) max(var(--spacing-l),env(safe-area-inset-left));place-items:center;background:var(--theme-canvas);color:var(--theme-text)}
.native-availability__card{display:grid;width:min(100%,28rem);max-width:100%;min-width:0;padding:clamp(1.5rem,6vw,2.25rem);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised);box-shadow:0 18px 48px color-mix(in oklch,var(--theme-text) 10%,transparent)}
.native-availability__logo{width:min(11rem,58vw);min-height:0;margin-bottom:var(--spacing-xl)}
.native-availability__logo :deep(.system-logo__mark){width:100%;height:auto;max-height:3rem}
.native-availability__state-icon{display:grid;width:3rem;height:3rem;margin-bottom:var(--spacing-s);border-radius:50%;place-items:center;background:var(--theme-accent-soft);color:var(--theme-primary)}
.native-availability__state-icon svg{width:1.35rem;height:1.35rem}
.native-availability__state-icon .is-checking{animation:native-availability-spin .9s linear infinite}
.native-availability__eyebrow{margin:0 0 var(--spacing-2xs);color:var(--theme-primary);font-size:var(--font-size--1);font-weight:var(--font-weight-700);letter-spacing:.06em;text-transform:uppercase}
.native-availability h1{max-width:100%;margin:0;font-size:clamp(var(--font-size-2),7vw,var(--font-size-3));line-height:1.12;overflow-wrap:anywhere}
.native-availability__description{max-width:38ch;margin:var(--spacing-xs) 0 0;color:var(--theme-text-muted);line-height:1.55;overflow-wrap:anywhere}
.native-availability__retry{width:100%;min-height:2.875rem!important;margin-top:var(--spacing-l);border-color:var(--theme-primary)!important;border-radius:var(--component-radius-button)!important;background:var(--theme-primary)!important;color:var(--theme-primary-foreground)!important}
.native-availability__retry :deep(>span.truncate){display:flex!important;align-items:center!important;justify-content:center!important;gap:var(--spacing-2xs)!important;min-width:0!important;line-height:1!important}
.native-availability__retry :deep(svg),.native-availability__retry :deep([data-slot="loading"]){display:block!important;flex:0 0 1rem!important;width:1rem!important;height:1rem!important;min-width:1rem!important;min-height:1rem!important;max-width:1rem!important;max-height:1rem!important;margin:0!important}
.native-availability__host{margin:var(--spacing-s) 0 0;color:var(--theme-text-muted);font-size:var(--font-size--2);line-height:1.4;overflow-wrap:anywhere}
.native-availability__host strong{color:var(--theme-text);font-weight:var(--font-weight-600)}
@keyframes native-availability-spin{to{transform:rotate(360deg)}}
@media(max-width:24rem){.native-availability{padding:max(var(--spacing-s),env(safe-area-inset-top)) max(var(--spacing-s),env(safe-area-inset-right)) max(var(--spacing-s),env(safe-area-inset-bottom)) max(var(--spacing-s),env(safe-area-inset-left))}.native-availability__card{padding:1.35rem}.native-availability__logo{margin-bottom:var(--spacing-l)}}
@media(prefers-reduced-motion:reduce){.native-availability__state-icon .is-checking{animation:none}}
</style>
