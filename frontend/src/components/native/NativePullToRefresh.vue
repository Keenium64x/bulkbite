<script setup>
import { computed } from "vue"
import { AlertCircle, Check, RefreshCw } from "lucide-vue-next"
import { runtimeConfig } from "@/config/runtime"
import {
  pullToRefreshArmed as armed,
  pullToRefreshProgress as progress,
  pullToRefreshState as state,
} from "@/native/pullToRefresh"


// =============================================================================
// region NATIVE REFRESH INDICATOR
// =============================================================================

const label = computed(() => {
  if (state.refreshing) return "Refreshing BulkBite"
  if (state.outcome === "success") return "BulkBite is up to date"
  if (state.outcome === "error") return "Refresh failed"
  return armed.value ? "Release to refresh" : "Pull to refresh"
})

const icon = computed(() => {
  if (state.outcome === "success") return Check
  if (state.outcome === "error") return AlertCircle
  return RefreshCw
})


// endregion NATIVE REFRESH INDICATOR
</script>

<template>
  <div
    v-if="runtimeConfig.isNative"
    class="native-pull-refresh"
    :class="{
      'is-visible': state.pulling || state.refreshing || state.outcome,
      'is-armed': armed,
      'is-refreshing': state.refreshing,
      'is-success': state.outcome === 'success',
      'is-error': state.outcome === 'error',
    }"
    :style="{ '--pull-distance': `${state.distance}px`, '--pull-progress': progress }"
    role="status"
    aria-live="polite"
  >
    <span class="native-pull-refresh__icon"><component :is="icon" aria-hidden="true" /></span>
    <strong>{{ label }}</strong>
  </div>
</template>

<style scoped>
.native-pull-refresh{position:fixed;z-index:60;top:env(safe-area-inset-top,0);left:50%;display:flex;min-height:2.75rem;align-items:center;gap:var(--spacing-2xs);padding:var(--spacing-3xs) var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:999px;background:color-mix(in oklch,var(--theme-surface-raised) 94%,transparent);box-shadow:0 .5rem 1.5rem color-mix(in oklch,var(--theme-text) 12%,transparent);color:var(--theme-text-muted);font-size:var(--font-size--2);opacity:0;pointer-events:none;transform:translate(-50%,calc(min(var(--pull-distance),5.5rem) - 4rem)) scale(calc(.84 + var(--pull-progress) * .16));transition:opacity 120ms ease,transform 120ms ease,border-color 120ms ease,color 120ms ease;backdrop-filter:blur(14px)}
.native-pull-refresh.is-visible{opacity:1}.native-pull-refresh.is-armed,.native-pull-refresh.is-success{border-color:var(--theme-success);color:var(--theme-success)}.native-pull-refresh.is-error{border-color:var(--theme-error);color:var(--theme-error)}
.native-pull-refresh__icon{display:grid;width:1.75rem;height:1.75rem;place-items:center;border-radius:50%;background:var(--theme-surface)}.native-pull-refresh svg{width:1rem;height:1rem;transform:rotate(calc(var(--pull-progress) * 220deg));transition:transform 80ms linear}.native-pull-refresh.is-success svg,.native-pull-refresh.is-error svg{transform:none}.native-pull-refresh.is-refreshing svg{animation:native-refresh-spin .75s linear infinite}.native-pull-refresh strong{white-space:nowrap}@keyframes native-refresh-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.native-pull-refresh,.native-pull-refresh svg{transition:none}.native-pull-refresh.is-refreshing svg{animation-duration:1.2s}}
</style>
