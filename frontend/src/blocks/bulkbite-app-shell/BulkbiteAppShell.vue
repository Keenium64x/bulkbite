<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { LogIn, LogOut, Settings, UserRound } from "lucide-vue-next"
import {
  SystemDialog,
  SystemDialogContent,
  SystemDialogDescription,
  SystemDialogFooter,
  SystemDialogHeader,
  SystemDialogTitle,
  SystemLink,
  SystemLogo,
  SystemOperationalButton,
} from "@/desyium"
import bulkbiteWordmark from "@/assets/bulkbite-logo-wordmark.svg"
import NativePullToRefresh from "@/components/native/NativePullToRefresh.vue"
import { offlineState } from "@/native/offlineStore"
import { offlineConflictDetails, resolveOfflineConflict } from "@/native/offlineSync"
import { useNativePullToRefresh } from "@/native/pullToRefresh"
import { syncOfflineMutation } from "@/resources/api"

// =============================================================================
// region SHELL CONTRACT
// =============================================================================

const props = defineProps({
  sections: { type: Array, required: true },
  activeSection: { type: String, required: true },
  user: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  sessionBusy: { type: Boolean, default: false },
  refreshAction: { type: Function, default: null },
})

const emit = defineEmits(["navigate", "refresh", "logout"])

// endregion SHELL CONTRACT

// =============================================================================
// region OFFLINE RECONCILIATION
// =============================================================================

const conflictBusy = ref(false)
const conflictError = ref("")
const conflictDetails = computed(() => offlineConflictDetails())

function formatConflictValue(value) {
  if (value === undefined || value === null || value === "") return "Not set"
  if (typeof value === "object") return JSON.stringify(value, null, 2)
  return String(value)
}

async function chooseConflictVersion(action) {
  if (conflictBusy.value) return
  conflictBusy.value = true
  conflictError.value = ""
  try {
    await resolveOfflineConflict(syncOfflineMutation, action)
  } catch (error) {
    conflictError.value = error?.message || "BulkBite could not reconcile this draft."
  } finally {
    conflictBusy.value = false
  }
}

async function refreshCurrentWorkflow() {
  if (props.busy) return true
  if (props.refreshAction) return props.refreshAction()
  emit("refresh")
  return true
}

useNativePullToRefresh(refreshCurrentWorkflow)

// endregion OFFLINE RECONCILIATION
</script>

<template>
  <section data-block="bulkbite-app-shell" class="app-shell">
    <NativePullToRefresh />

    <header class="app-shell__bar">
      <SystemLogo class="app-shell__logo" name="BulkBite" :src="bulkbiteWordmark" href="/bulkbite" compact variant="inverse" @click.prevent="$emit('navigate', sections[0].id)" />

      <nav class="app-shell__tabs" aria-label="Main navigation">
        <SystemOperationalButton
          v-for="section in sections"
          :key="section.id"
          class="app-shell__tab"
          :class="{ 'is-active': activeSection === section.id }"
          :aria-current="activeSection === section.id ? 'page' : undefined"
          variant="ghost"
          @click="$emit('navigate', section.id)"
        >{{ section.label }}</SystemOperationalButton>
      </nav>

      <div class="app-shell__bar-actions">
        <SystemOperationalButton class="app-shell__bar-action" variant="ghost" :disabled="busy" :aria-busy="busy" :label="busy ? 'Refreshing' : 'Refresh'" @click="$emit('refresh')">
          <span v-if="busy" class="app-shell__refresh-loader" aria-hidden="true" />
          <span>{{ busy ? 'Refreshing' : 'Refresh' }}</span>
        </SystemOperationalButton>

        <SystemLink href="/bulkbite/setup" class="app-shell__bar-action app-shell__settings" title="Settings" aria-label="Settings" @click.prevent="$emit('navigate', { mode: 'catalogue' })">
          <Settings aria-hidden="true" />
        </SystemLink>

        <SystemOperationalButton v-if="user && user !== 'Guest'" class="app-shell__bar-action" variant="ghost" :loading="sessionBusy" loading-text="Signing out" :title="user" :aria-label="`Log out ${user}`" @click="$emit('logout')">
          <UserRound aria-hidden="true" /><LogOut aria-hidden="true" />
        </SystemOperationalButton>
        <SystemLink v-else href="/login?redirect-to=%2Fbulkbite" class="app-shell__bar-action" aria-label="Log in" title="Log in">
          <LogIn aria-hidden="true" />
        </SystemLink>
      </div>
    </header>

    <main class="app-shell__work" tabindex="-1"><slot /></main>

    <SystemDialog :open="Boolean(offlineState.conflict)">
      <SystemDialogContent class="app-shell__conflict-dialog" @escape-key-down.prevent @pointer-down-outside.prevent>
        <SystemDialogHeader>
          <SystemDialogTitle>Choose which draft to keep</SystemDialogTitle>
          <SystemDialogDescription>
            This device and the server both changed the same editable draft. Posted records, receipts, stock events, and immutable ledger entries are never overwritten here.
          </SystemDialogDescription>
        </SystemDialogHeader>

        <div class="app-shell__conflict-body">
          <p v-if="conflictDetails?.name" class="app-shell__conflict-record">
            {{ conflictDetails.doctype }} · {{ conflictDetails.name }}
          </p>
          <div v-if="conflictDetails?.changedFields?.length" class="app-shell__conflict-differences" role="list" aria-label="Conflicting draft fields">
            <article v-for="difference in conflictDetails.changedFields" :key="difference.field" class="app-shell__conflict-row" role="listitem">
              <h3>{{ difference.field.replaceAll('_', ' ') }}</h3>
              <div class="app-shell__conflict-versions">
                <section><p>This device</p><pre>{{ formatConflictValue(difference.local) }}</pre></section>
                <section><p>Server</p><pre>{{ formatConflictValue(difference.server) }}</pre></section>
              </div>
            </article>
          </div>
          <p v-else class="app-shell__conflict-empty">The server reported a version conflict but did not return field-level differences.</p>
          <p v-if="conflictError" class="app-shell__conflict-error" role="alert">{{ conflictError }}</p>
        </div>

        <SystemDialogFooter class="app-shell__conflict-actions">
          <SystemOperationalButton variant="subtle" :disabled="conflictBusy" @click="chooseConflictVersion('server')">Keep server version</SystemOperationalButton>
          <SystemOperationalButton variant="solid" :loading="conflictBusy" loading-text="Reconciling" @click="chooseConflictVersion('local')">Use this device</SystemOperationalButton>
        </SystemDialogFooter>
      </SystemDialogContent>
    </SystemDialog>
  </section>
</template>

<style scoped>
.app-shell{display:grid;grid-template-rows:auto minmax(0,1fr);min-height:100vh;min-height:100dvh;background:var(--theme-canvas)}

.app-shell__bar{position:sticky;top:0;z-index:20;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:var(--spacing-m);padding:var(--spacing-xs) var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-text);color:var(--theme-canvas)}

.app-shell__tabs{display:flex;justify-content:center;gap:var(--spacing-3xs)}
.app-shell__tab{padding:var(--spacing-2xs) var(--spacing-m);border-radius:999px;color:color-mix(in oklch,var(--theme-canvas) 70%,transparent);font-size:var(--font-size-0);font-weight:var(--font-weight-500);white-space:nowrap}
.app-shell__tab:hover{color:var(--theme-canvas);background:color-mix(in oklch,var(--theme-canvas) 10%,transparent)}
.app-shell__tab.is-active{color:var(--theme-text);background:var(--theme-canvas);font-weight:var(--font-weight-600)}

.app-shell__bar-actions{display:flex;align-items:center;gap:var(--spacing-3xs)}
.app-shell__bar-action{display:inline-flex;align-items:center;gap:var(--spacing-3xs);padding:var(--spacing-2xs) var(--spacing-xs);border-radius:var(--component-radius-card);color:color-mix(in oklch,var(--theme-canvas) 70%,transparent);font-size:var(--font-size--1);text-decoration:none}
.app-shell__bar-action:hover{color:var(--theme-canvas);background:color-mix(in oklch,var(--theme-canvas) 10%,transparent)}
.app-shell__bar-action :deep(svg){width:1.05rem;height:1.05rem}

.app-shell__work{min-width:0;padding:var(--spacing-l) 0 var(--spacing-xl-2xl)}
.app-shell__work:focus{outline:none}

@media(max-width:52rem){
  .app-shell__bar{grid-template-columns:auto auto;grid-template-areas:"logo actions" "tabs tabs";gap:var(--spacing-xs);padding:var(--spacing-2xs) var(--spacing-s)}
  .app-shell__bar-actions{grid-area:actions;justify-self:end}
  .app-shell__tabs{grid-area:tabs;justify-content:stretch}
  .app-shell__tab{flex:1;padding:var(--spacing-2xs) var(--spacing-2xs);text-align:center}
  .app-shell__bar-action span:not(.app-shell__refresh-loader){display:none}
  .app-shell__work{padding:var(--spacing-m) 0 var(--spacing-xl)}
}

.app-shell__work{min-width:0;min-height:calc(100vh - 7.75rem);background:var(--theme-canvas)}
.app-shell__refresh-loader{display:block;align-self:center;box-sizing:border-box;flex:0 0 .75rem;width:.75rem;height:.75rem;margin:0;border:1.5px solid currentColor;border-right-color:transparent;border-radius:999px;animation:app-shell-spin .7s linear infinite}
.app-shell__visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;margin:-1px;padding:0;border:0;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:64rem){
  .app-shell__work{position:relative;width:100%;min-width:0;max-width:100%;min-height:100dvh;overflow-x:hidden;padding-bottom:calc(5.25rem + env(safe-area-inset-bottom,0px))}
}
:global(.app-shell__conflict-dialog){display:grid!important;width:min(46rem,calc(100vw - 2rem))!important;max-width:46rem!important;max-height:min(88dvh,52rem)!important;overflow:hidden!important;padding:var(--spacing-m)!important;background:var(--theme-surface-raised)!important;color:var(--theme-text)!important}
.app-shell__conflict-body{display:grid;min-height:0;gap:var(--spacing-s);overflow:hidden}
.app-shell__conflict-record,.app-shell__conflict-empty,.app-shell__conflict-error{margin:0;font-size:var(--font-size--1)}
.app-shell__conflict-record{color:var(--theme-text-muted);font-weight:var(--font-weight-600)}
.app-shell__conflict-differences{display:grid;min-height:0;max-height:52dvh;gap:var(--spacing-xs);overflow-y:auto;overscroll-behavior:contain;padding-right:var(--spacing-2xs);scrollbar-color:var(--theme-border) transparent;scrollbar-width:thin}
.app-shell__conflict-row{display:grid;gap:var(--spacing-2xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}
.app-shell__conflict-row h3,.app-shell__conflict-versions p{margin:0;font-size:var(--font-size--1);text-transform:capitalize}
.app-shell__conflict-versions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-xs)}
.app-shell__conflict-versions section{min-width:0}
.app-shell__conflict-versions p{margin-bottom:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-700)}
.app-shell__conflict-versions pre{max-width:100%;max-height:10rem;overflow:auto;margin:0;padding:var(--spacing-xs);border-radius:var(--component-radius-button);background:var(--theme-canvas);font:inherit;font-size:var(--font-size--2);white-space:pre-wrap;overflow-wrap:anywhere}
.app-shell__conflict-error{color:var(--theme-danger-text,var(--theme-error))}
.app-shell__conflict-actions{display:flex!important;flex-wrap:wrap;justify-content:flex-end;gap:var(--spacing-xs)}
@media(max-width:36rem){:global(.app-shell__conflict-dialog){width:calc(100vw - 1rem)!important;max-height:92dvh!important;padding:var(--spacing-s)!important}.app-shell__conflict-versions{grid-template-columns:1fr}.app-shell__conflict-actions{display:grid!important;grid-template-columns:1fr}.app-shell__conflict-actions :deep(button){width:100%!important}}
</style>
