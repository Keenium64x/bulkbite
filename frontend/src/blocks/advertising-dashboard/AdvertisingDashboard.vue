<script setup>
import { computed, onMounted, ref } from "vue"
import { SystemOperationalButton } from "@/desyium"
import { getAdvertisingWorkspace } from "@/resources/api"
import AdvertisingOverview from "./AdvertisingOverview.vue"
import AdvertisingRequests from "./AdvertisingRequests.vue"
import AdvertisingCampaigns from "./AdvertisingCampaigns.vue"
import AdvertisingAssets from "./AdvertisingAssets.vue"
import AdvertisingReview from "./AdvertisingReview.vue"
import AdvertisingResults from "./AdvertisingResults.vue"

const sections = [
  { id: "overview", label: "Overview", component: AdvertisingOverview },
  { id: "requests", label: "Requests", component: AdvertisingRequests },
  { id: "campaigns", label: "Campaigns", component: AdvertisingCampaigns },
  { id: "assets", label: "Assets", component: AdvertisingAssets },
  { id: "review", label: "Review", component: AdvertisingReview },
  { id: "results", label: "Placements & results", component: AdvertisingResults },
]
const workspace = ref({ requests: [], campaigns: [], assets: [], placements: [], review_queue: [], metrics: {}, options: {}, can_manage: false })
const activeSection = ref("overview")
const busy = ref(false)
const error = ref("")
const notice = ref("")
const activeComponent = computed(() => sections.find(section => section.id === activeSection.value)?.component || AdvertisingOverview)

function navigate(section) {
  activeSection.value = section
  notice.value = ""
  requestAnimationFrame(() => document.querySelector(".advertising-panel")?.focus())
}

async function loadWorkspace(message = "") {
  busy.value = true
  error.value = ""
  try {
    workspace.value = await getAdvertisingWorkspace()
    notice.value = message
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

function handleSaved(message) {
  loadWorkspace(message)
}

onMounted(loadWorkspace)
</script>

<template>
  <section data-block="advertising-dashboard" class="advertising-workspace">
    <header class="advertising-page-header">
      <div>
        <p class="advertising-eyebrow">BulkBite operations</p>
        <h1>Advertising</h1>
        <p>Capture the need once, move it through production and review, then keep the final files and results together.</p>
      </div>
      <SystemOperationalButton variant="solid" size="lg" @click="navigate('requests')">New request</SystemOperationalButton>
    </header>

    <nav class="advertising-section-nav" aria-label="Advertising workspace">
      <SystemOperationalButton v-for="section in sections" :key="section.id" :variant="activeSection === section.id ? 'solid' : 'ghost'" @click="navigate(section.id)">{{ section.label }}</SystemOperationalButton>
    </nav>

    <div v-if="error" class="advertising-message advertising-message--error" role="alert">{{ error }}</div>
    <div v-if="notice" class="advertising-message" role="status">{{ notice }}</div>

    <main class="advertising-panel" tabindex="-1">
      <component :is="activeComponent" :workspace="workspace" :busy="busy" @navigate="navigate" @refresh="loadWorkspace" @saved="handleSaved" />
    </main>
  </section>
</template>

<style>
.advertising-workspace { width: min(100%, var(--grid-max-width)); margin: 0 auto; padding: var(--spacing-l) var(--spacing-m) var(--spacing-xl-2xl); display: grid; gap: var(--spacing-m); color: var(--theme-text); }
.advertising-page-header { display: flex; align-items: end; justify-content: space-between; gap: var(--spacing-m); }
.advertising-page-header h1, .advertising-section h2, .advertising-card h3 { margin: 0; }
.advertising-page-header p, .advertising-section p, .advertising-card p { margin: var(--spacing-2xs) 0 0; color: var(--theme-text-muted); }
.advertising-eyebrow { margin: 0 0 var(--spacing-3xs) !important; color: var(--theme-text-muted); font-size: var(--font-size--2); font-weight: var(--font-weight-600); letter-spacing: var(--font-letter-spacing-2); text-transform: uppercase; }
.advertising-section-nav { display: flex; gap: var(--spacing-2xs); overflow-x: auto; padding: var(--spacing-2xs); border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); }
.advertising-section-nav > * { flex: 0 0 auto; }
.advertising-panel { min-width: 0; outline: none; }
.advertising-section { display: grid; gap: var(--spacing-m); }
.advertising-section-header { display: flex; align-items: start; justify-content: space-between; gap: var(--spacing-m); }
.advertising-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); overflow: hidden; }
.advertising-metric { padding: var(--spacing-m); display: grid; gap: var(--spacing-3xs); border-right: 1px solid var(--theme-border); }
.advertising-metric:last-child { border-right: 0; }
.advertising-metric strong { font-size: var(--font-size-3); }
.advertising-metric span, .advertising-muted { color: var(--theme-text-muted); font-size: var(--font-size--1); }
.advertising-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-m); }
.advertising-card { min-width: 0; padding: var(--spacing-m); display: grid; align-content: start; gap: var(--spacing-s); border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); }
.advertising-card--raised { background: var(--theme-surface-raised); }
.advertising-list { display: grid; gap: var(--spacing-xs); }
.advertising-list-row { min-width: 0; padding: var(--spacing-s); display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-s); border: 1px solid var(--theme-border); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.advertising-list-row__body { min-width: 0; display: grid; gap: var(--spacing-3xs); }
.advertising-list-row__body small { color: var(--theme-text-muted); }
.advertising-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--spacing-xs); }
.advertising-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-s); }
.advertising-field { min-width: 0; display: grid; gap: var(--spacing-3xs); }
.advertising-field > span { font-size: var(--font-size--1); font-weight: var(--font-weight-600); }
.advertising-field--wide { grid-column: 1 / -1; }
.advertising-split { display: grid; grid-template-columns: minmax(17rem, .72fr) minmax(0, 1.65fr); gap: var(--spacing-m); }
.advertising-filters { display: grid; grid-template-columns: minmax(14rem, 2fr) repeat(2, minmax(10rem, 1fr)); gap: var(--spacing-s); align-items: end; }
.advertising-message { padding: var(--spacing-s) var(--spacing-m); border: 1px solid var(--theme-border); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.advertising-message--error { border-color: var(--theme-danger, var(--theme-primary)); }
.advertising-empty { padding: var(--spacing-l); color: var(--theme-text-muted); text-align: center; }
.advertising-destination { padding: var(--spacing-s); display: grid; gap: var(--spacing-2xs); border-left: .2rem solid var(--theme-primary); background: var(--theme-surface-raised); overflow-wrap: anywhere; }
.advertising-data { margin: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--spacing-xs); }
.advertising-data div { padding: var(--spacing-s); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.advertising-data dt { color: var(--theme-text-muted); font-size: var(--font-size--2); }
.advertising-data dd { margin: var(--spacing-3xs) 0 0; }
.advertising-table { width: 100%; border-collapse: collapse; }
.advertising-table th, .advertising-table td { padding: var(--spacing-xs); border-bottom: 1px solid var(--theme-border); text-align: left; vertical-align: top; }
.advertising-table th { color: var(--theme-text-muted); font-size: var(--font-size--2); }
@media (max-width: 64rem) { .advertising-metrics, .advertising-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .advertising-split { grid-template-columns: 1fr; } }
@media (max-width: 42rem) { .advertising-workspace { padding-inline: var(--spacing-s); } .advertising-page-header, .advertising-section-header { align-items: stretch; flex-direction: column; } .advertising-metrics, .advertising-grid, .advertising-form-grid, .advertising-filters, .advertising-data { grid-template-columns: 1fr; } .advertising-metric { border-right: 0; border-bottom: 1px solid var(--theme-border); } .advertising-field--wide { grid-column: auto; } .advertising-table { display: block; overflow-x: auto; } }
</style>
