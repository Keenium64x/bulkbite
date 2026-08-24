<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import {
  SystemBadge, SystemDatePicker, SystemFileUploader, SystemLinkedRecordField, SystemOperationalButton,
  SystemTabs, SystemTabsContent, SystemTabsList, SystemTabsTrigger,
} from "@/desyium"
import { applyPriceWorkbook, getPurchasePriceHistory, previewPriceWorkbook, priceWorkbookUrl } from "@/resources/api"
import { useRouter } from "vue-router"

// =============================================================================
// region PRICES AND COSTS WORKSPACE
// =============================================================================

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null } })
const router = useRouter()
const result = ref({ rows: [], summary: { theory_count: 0, actual_count: 0, item_count: 0, supplier_count: 0 } })
const importBatch = ref(null)
const busy = ref(false)
const error = ref("")
const success = ref("")
const filters = reactive({ item_code: "", supplier: "", from_date: "", to_date: "" })
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))

async function loadHistory() {
  error.value = ""
  if (filters.from_date && filters.to_date && filters.from_date > filters.to_date) return (error.value = "From date must be on or before to date.")
  busy.value = true
  try { result.value = await getPurchasePriceHistory(filters) }
  catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

async function onWorkbookUpload(file) {
  const fileUrl = file?.file_url || file?.message?.file_url || file?.data?.file_url
  if (!fileUrl) return (error.value = "The workbook uploaded, but its private file address was missing.")
  busy.value = true; error.value = ""; success.value = ""
  try { importBatch.value = await previewPriceWorkbook(fileUrl) }
  catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

async function applyImport() {
  busy.value = true; error.value = ""; success.value = ""
  try {
    importBatch.value = await applyPriceWorkbook(importBatch.value.name)
    success.value = "The reviewed catalogue changes were applied. Stock was not changed."
    await loadHistory()
  } catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

function clearFilters() { Object.assign(filters, { item_code: "", supplier: "", from_date: "", to_date: "" }); loadHistory() }
function openRecords(doctype) { router.push({ name: "BulkBiteSetupList", params: { doctype } }) }
function downloadWorkbook() { window.location.assign(priceWorkbookUrl()) }
function money(value) { return value === null || value === undefined ? "Not available" : `R ${Number(value || 0).toFixed(2)}` }
function quantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }
function variance(row) {
  if (row.record_type !== "Actual" || row.variance === null || row.variance === undefined) return "No matching theory"
  const sign = Number(row.variance) > 0 ? "+" : ""
  return `${sign}${money(row.variance)} (${sign}${Number(row.variance_percent || 0).toFixed(1)}%)`
}
function rowLabel(row) { return row.item_name || row.label || row.record_name || `Workbook row ${row.row_number}` }
function statusTheme(status) { return status === "error" ? "red" : status === "unchanged" ? undefined : "green" }

onMounted(loadHistory)

// endregion PRICES AND COSTS WORKSPACE
</script>

<template>
  <section data-block="price-history" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Purchasing setup</p><h1>Prices and costs</h1><p>Keep supplier prices, discounts, delivery and VAT rules, operating costs, and actual receipt evidence in one financial workspace.</p></div><SystemBadge>Does not change stock</SystemBadge></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="success" class="state-message" role="status">{{ success }}</div>

    <SystemTabs default-value="catalogue" class="cost-tabs">
      <SystemTabsList class="cost-tabs__list" aria-label="Prices and costs sections">
        <SystemTabsTrigger value="catalogue">Price catalogue</SystemTabsTrigger>
        <SystemTabsTrigger value="rules">Discounts and costs</SystemTabsTrigger>
        <SystemTabsTrigger value="history">Price history</SystemTabsTrigger>
      </SystemTabsList>

      <SystemTabsContent value="catalogue" class="cost-tabs__content">
        <section class="form-section">
          <div class="section-heading"><div><p class="eyebrow">Excel exchange</p><h2>Update prices with the same BulkBite names</h2><p>Download the current catalogue, give it to ChatGPT, then upload the completed workbook for review. Stable IDs stop existing offers from duplicating.</p></div></div>
          <div class="exchange-grid">
            <article class="exchange-card"><span>1</span><div><strong>Download current data</strong><p>Includes exact item names, item codes, suppliers, pack definitions, current offers, adjustments, and cost rules.</p><SystemOperationalButton variant="outline" @click="downloadWorkbook">Download Excel workbook</SystemOperationalButton></div></article>
            <article class="exchange-card"><span>2</span><div><strong>Upload and review</strong><p>The system separates inserts, updates, unchanged rows, and errors before anything is applied.</p><SystemFileUploader :upload-args="{ private: true }" :file-types="['.xlsx', '.xlsm']" @success="onWorkbookUpload"><template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading || busy" @click="upload.openFileSelector">{{ importBatch ? "Replace workbook" : "Upload completed workbook" }}</SystemOperationalButton></template></SystemFileUploader></div></article>
          </div>
        </section>
        <section v-if="importBatch" class="data-section">
          <div class="section-heading"><div><p class="eyebrow">Import {{ importBatch.name }}</p><h2>Review catalogue changes</h2><p>Applying this batch updates pricing theory and cost configuration only.</p></div><SystemBadge :theme="importBatch.status === 'Applied' ? 'green' : undefined">{{ importBatch.status }}</SystemBadge></div>
          <div class="metric-board metric-board--paper"><div><strong>{{ importBatch.counts.insert }}</strong><span>new records</span></div><div><strong>{{ importBatch.counts.update }}</strong><span>updates</span></div><div><strong>{{ importBatch.counts.unchanged }}</strong><span>unchanged</span></div><div><strong>{{ importBatch.counts.error }}</strong><span>errors</span></div></div>
          <div class="review-list"><article v-for="row in importBatch.rows" :key="`${row.kind}-${row.row_number}`"><div><strong>{{ rowLabel(row) }}</strong><small>{{ row.kind }}<template v-if="row.supplier"> · {{ row.supplier }}</template></small></div><SystemBadge :theme="statusTheme(row.status)">{{ row.status }}</SystemBadge><p v-if="row.errors?.length">{{ row.errors.join(" ") }}</p><p v-else-if="row.changes?.length">{{ row.changes.length }} field{{ row.changes.length === 1 ? "" : "s" }} will change.</p><p v-else>No change.</p></article></div>
          <div class="button-row"><SystemOperationalButton v-if="importBatch.status !== 'Applied'" variant="solid" :loading="busy" :disabled="importBatch.counts.error > 0" @click="applyImport">Apply reviewed changes</SystemOperationalButton><span v-if="importBatch.counts.error" class="field-error">Correct workbook errors and upload it again before applying.</span></div>
        </section>
      </SystemTabsContent>

      <SystemTabsContent value="rules" class="cost-tabs__content">
        <section class="data-section">
          <div class="section-heading"><div><p class="eyebrow">Reusable financial rules</p><h2>Model what food really costs to buy and make</h2><p>Keep expected rules separate from actual evidence, so Reports can compare theory with reality.</p></div></div>
          <div class="rule-grid">
            <article><h3>Supplier offers</h3><p>Base pack price, pack size, VAT basis, source, and verification date.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Supplier Offer')">Manage supplier offers</SystemOperationalButton></article>
            <article><h3>Discounts and buying adjustments</h3><p>Percentage or fixed discounts, rebates, free delivery, delivery fees, service costs, and VAT adjustments.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Price Adjustment')">Manage adjustments</SystemOperationalButton></article>
            <article><h3>Expected operating costs</h3><p>Labour, packaging, utilities, rent, delivery, and overhead rates by hour, meal, customer, kg, revenue, or fixed amount.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Operating Cost Rule')">Manage expected costs</SystemOperationalButton></article>
            <article><h3>Actual operating costs</h3><p>Enter employee hours and other evidence-backed costs. Reports will never treat an expected rate as an actual payment.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Cost Entry')">Add actual costs</SystemOperationalButton></article>
          </div>
        </section>
      </SystemTabsContent>

      <SystemTabsContent value="history" class="cost-tabs__content">
        <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Filters</p><h2>Choose what to compare</h2><p>Use one item and supplier to follow theory and receipt evidence over time.</p></div></div><div class="field-grid"><SystemLinkedRecordField v-model="filters.item_code" label="Item" :options="itemOptions" placeholder="All items" /><SystemLinkedRecordField v-model="filters.supplier" label="Supplier" :options="supplierOptions" placeholder="All suppliers" /><SystemDatePicker v-model="filters.from_date" label="From date" format="YYYY-MM-DD" /><SystemDatePicker v-model="filters.to_date" label="To date" format="YYYY-MM-DD" /></div><div class="button-row"><SystemOperationalButton variant="outline" :loading="busy" @click="loadHistory">Update history</SystemOperationalButton><SystemOperationalButton variant="ghost" :disabled="busy" @click="clearFilters">Clear filters</SystemOperationalButton></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Price ledger</p><h2>Theory versus actual</h2><p>Price per stock unit is the comparable basis used by recipes and variance.</p></div></div><div class="metric-board metric-board--paper"><div><strong>{{ result.summary.theory_count }}</strong><span>theory points</span></div><div><strong>{{ result.summary.actual_count }}</strong><span>actual points</span></div><div><strong>{{ result.summary.item_count }}</strong><span>items</span></div><div><strong>{{ result.summary.supplier_count }}</strong><span>suppliers</span></div></div><div v-if="result.rows.length" class="price-table-wrap"><table class="price-table"><thead><tr><th>Date</th><th>Basis</th><th>Item</th><th>Supplier</th><th>Pack</th><th>Pack price</th><th>Price per stock unit</th><th>Theory at purchase</th><th>Difference</th><th>Evidence</th></tr></thead><tbody><tr v-for="row in result.rows" :key="`${row.record_type}-${row.record_name}`"><td>{{ row.date || "Not dated" }}</td><td><SystemBadge :theme="row.record_type === 'Actual' ? 'green' : undefined">{{ row.record_type }}</SystemBadge></td><td><strong>{{ row.item_name }}</strong><small>{{ row.item_code }}</small></td><td>{{ row.supplier }}</td><td>{{ quantity(row.packs) }} × ({{ quantity(row.units_per_pack) }} × {{ quantity(row.unit_size) }} {{ row.purchase_uom }})</td><td>{{ money(row.pack_price) }}</td><td><strong>{{ money(row.stock_unit_price) }} / {{ row.stock_uom }}</strong></td><td>{{ money(row.theory_stock_unit_price) }}</td><td>{{ variance(row) }}</td><td>{{ row.reference }}<small>{{ row.reference_detail || (row.effective_to ? `Until ${row.effective_to}` : "Current until replaced") }}</small></td></tr></tbody></table></div><p v-else class="empty-state">No supplier offers or reviewed receipt prices match these filters.</p></section>
      </SystemTabsContent>
    </SystemTabs>
  </section>
</template>

<style scoped>
.cost-tabs{display:grid;gap:var(--spacing-m)}.cost-tabs__list{display:flex;gap:var(--spacing-3xs);width:fit-content;max-width:100%;overflow-x:auto;padding:var(--spacing-3xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.cost-tabs__content{display:grid;gap:var(--spacing-m);outline:none}.exchange-grid,.rule-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-m)}.exchange-card,.rule-grid article{min-width:0;padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.exchange-card{display:flex;align-items:flex-start;gap:var(--spacing-s)}.exchange-card>span{display:grid;flex:0 0 2rem;place-items:center;width:2rem;height:2rem;border-radius:999px;background:var(--theme-secondary);font-weight:var(--font-weight-700)}.exchange-card>div,.rule-grid article{display:grid;gap:var(--spacing-xs)}.exchange-card p,.rule-grid p{margin:0;color:var(--theme-text-muted)}.rule-grid article{align-content:start}.rule-grid h3{margin:0}.review-list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.review-list article{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--spacing-3xs) var(--spacing-s);padding:var(--spacing-s) var(--spacing-m);border-bottom:var(--border-width-1) solid var(--theme-border)}.review-list article:last-child{border-bottom:0}.review-list small{display:block;color:var(--theme-text-muted)}.review-list p{grid-column:1/-1;margin:0;color:var(--theme-text-muted)}.price-table-wrap{max-width:100%;overflow-x:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card)}.price-table{width:100%;min-width:82rem;border-collapse:collapse;background:var(--theme-surface-raised)}.price-table th,.price-table td{padding:var(--spacing-xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);text-align:left;vertical-align:top}.price-table th{background:var(--theme-secondary);color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-700);white-space:nowrap}.price-table td{font-size:var(--font-size--1)}.price-table tbody tr:last-child td{border-bottom:0}.price-table small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.empty-state{margin:0;padding:var(--spacing-l);border:var(--border-width-1) dashed var(--theme-border);border-radius:var(--component-radius-card);color:var(--theme-text-muted);text-align:center}@media(max-width:760px){.exchange-grid,.rule-grid{grid-template-columns:1fr}.cost-tabs__list{width:100%}}
</style>
