<script setup>
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  SystemAccountantExport,
  SystemAuxiliaryRecords,
  SystemBulkbiteAppShell,
  SystemBuyingPlan,
  SystemDocumentReview,
  SystemEmployeeManagement,
  SystemMonthlyPlanning,
  SystemProductionMeasurement,
  SystemPriceHistory,
  SystemReceiptIntake,
  SystemStockOverview,
  SystemStockReconciliation,
} from "@/desyium"
import { assignScanCode, getInventorySnapshot, getProductionPlanSnapshot, getWorkspaceSnapshot, logOut, resolveScanCode } from "@/resources/api"

const sections = [
  { id: "overview", label: "Dashboard" },
  { id: "planning", label: "Planning" },
  { id: "buying", label: "Buying" },
  { id: "receipts", label: "Receipts" },
  { id: "production", label: "Production" },
  { id: "finance", label: "Finance" },
  { id: "export", label: "Reports" },
  { id: "stock", label: "Stock" },
]
const auxiliarySections = ["employees", "documents"]
const activeSectionStorageKey = "bulkbite-active-section"
const allowedSectionIds = new Set([...sections.map(section => section.id), ...auxiliarySections])
const route = useRoute()
const router = useRouter()
const auxiliaryMode = computed(() => {
  if (route.meta.auxiliaryRecord) return route.name === "AuxiliaryRecordCreate" ? "create" : "edit"
  if (route.meta.auxiliaryList) return "list"
  if (route.meta.auxiliaryCatalogue) return "catalogue"
  return ""
})
const activeSection = ref(resolveInitialSection())
const snapshot = ref(null)
const inventory = ref(null)
const plan = ref(null)
const scanResult = ref(null)
const loading = ref(false)
const sessionBusy = ref(false)
const error = ref("")
const currentUser = computed(() => snapshot.value?.user || window.boot?.user || "")

function navigate(id) {
  if (typeof id === "object") return navigateAuxiliary(id)
  if (route.path.startsWith("/bulkbite/setup")) router.push("/bulkbite")
  activeSection.value = id
  window.localStorage.setItem(activeSectionStorageKey, id)
  const url = new URL(window.location.href)
  id === "overview" ? url.searchParams.delete("work") : url.searchParams.set("work", id)
  window.history.replaceState({}, "", url)
  requestAnimationFrame(() => document.querySelector(".app-shell__work")?.focus())
}

function resolveInitialSection() {
  const urlSection = new URLSearchParams(window.location.search).get("work")
  if (allowedSectionIds.has(urlSection)) return urlSection
  const storedSection = window.localStorage.getItem(activeSectionStorageKey)
  return allowedSectionIds.has(storedSection) ? storedSection : "overview"
}

function navigateAuxiliary(target) {
  if (target.mode === "catalogue") return router.push({ name: "BulkBiteSetup" })
  if (target.mode === "list") return router.push({ name: "BulkBiteSetupList", params: { doctype: target.doctype } })
  if (target.mode === "create") return router.push({ name: "AuxiliaryRecordCreate", params: { doctype: target.doctype } })
  return router.push({ name: "AuxiliaryRecordEdit", params: { doctype: target.doctype, name: target.name } })
}

async function loadAll() {
  loading.value = true; error.value = ""
  try {
    const [workspaceData, inventoryData, planData] = await Promise.all([getWorkspaceSnapshot(), getInventorySnapshot("Ingredients"), getProductionPlanSnapshot(null, "Ingredients")])
    snapshot.value = workspaceData; inventory.value = inventoryData; plan.value = planData
  } catch (exception) { error.value = exception.message } finally { loading.value = false }
}

async function scan(code) { error.value = ""; try { scanResult.value = await resolveScanCode(code) } catch (exception) { error.value = exception.message } }
async function mapScan(itemCode, code) { error.value = ""; try { scanResult.value = await assignScanCode(itemCode, code); await loadAll() } catch (exception) { error.value = exception.message } }
async function handleLogout() {
  sessionBusy.value = true
  error.value = ""
  try {
    await logOut()
    window.location.assign("/login?redirect-to=%2Fbulkbite")
  } catch (exception) {
    error.value = exception.message
    sessionBusy.value = false
  }
}
onMounted(loadAll)
</script>

<template>
  <SystemBulkbiteAppShell :sections="sections" :active-section="activeSection" :user="currentUser" :busy="loading" :session-busy="sessionBusy" @navigate="navigate" @refresh="loadAll" @logout="handleLogout">
    <SystemAuxiliaryRecords v-if="auxiliaryMode" :mode="auxiliaryMode" :doctype="String(route.params.doctype || '')" :record-name="String(route.params.name || '')" @navigate="navigateAuxiliary" />
    <SystemStockOverview v-else-if="activeSection === 'overview'" mode="dashboard" :snapshot="snapshot" :inventory="inventory" :plan="plan" :loading="loading" :error="error" @open-workflow="navigate" />
    <SystemReceiptIntake v-else-if="activeSection === 'receipts'" :snapshot="snapshot" :inventory="inventory" :plan="plan" @changed="loadAll" />
    <SystemProductionMeasurement v-else-if="activeSection === 'production'" :snapshot="snapshot" :plan="plan" @changed="loadAll" @open-worker-sheets="navigate('documents')" @open-employees="navigate('employees')" />
    <SystemEmployeeManagement v-else-if="activeSection === 'employees'" @close="navigate('production')" @changed="loadAll" />
    <SystemMonthlyPlanning v-else-if="activeSection === 'planning'" :snapshot="snapshot" :plan="plan" @changed="loadAll" />
    <SystemBuyingPlan v-else-if="activeSection === 'buying'" :snapshot="snapshot" :plan="plan" @open-workflow="navigate" />
    <SystemDocumentReview v-else-if="activeSection === 'documents'" :snapshot="snapshot" :inventory="inventory" @changed="loadAll" />
    <SystemPriceHistory v-else-if="activeSection === 'finance'" mode="finance" :snapshot="snapshot" :inventory="inventory" @open-workflow="navigate" @changed="loadAll" />
    <SystemAccountantExport v-else-if="activeSection === 'export'" />
    <template v-else-if="activeSection === 'stock'">
      <SystemStockOverview mode="stock" :snapshot="snapshot" :inventory="inventory" :plan="plan" :scan-result="scanResult" :loading="loading" :error="error" @scan="scan" @map-scan="mapScan" @open-workflow="navigate" />
      <SystemPriceHistory mode="catalogue" :snapshot="snapshot" :inventory="inventory" @changed="loadAll" />
      <SystemStockReconciliation :inventory="inventory" @changed="loadAll" />
    </template>
  </SystemBulkbiteAppShell>
</template>
