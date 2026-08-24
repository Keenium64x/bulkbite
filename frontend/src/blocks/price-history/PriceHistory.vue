<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import {
  SystemBadge, SystemCheckbox, SystemDatePicker, SystemFileUploader, SystemFormControl,
  SystemLinkedRecordField, SystemMultiFileUploader, SystemOperationalButton, SystemSelect,
  SystemTabs, SystemTabsContent, SystemTabsList, SystemTabsTrigger,
} from "@/desyium"
import {
  applyPriceWorkbook, createCostInvoice, getCostInvoiceExtractionStatus, getPriceImportFields,
  getPurchasePriceHistory, inspectPriceFile, postCostInvoice, previewPriceWorkbook,
  priceWorkbookUrl, startCostInvoiceExtraction,
} from "@/resources/api"

// =============================================================================
// region FINANCE AND PRICE CATALOGUE WORKSPACE
// =============================================================================

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null }, mode: { type: String, default: "finance" } })
const emit = defineEmits(["open-workflow", "changed"])
const router = useRouter()
const result = ref({ rows: [], summary: { theory_count: 0, actual_count: 0, item_count: 0, supplier_count: 0 } })
const fieldContract = ref({ fields: [], default_fields: [] })
const selectedFields = ref([])
const importInspection = ref(null)
const importMapping = reactive({})
const importBatch = ref(null)
const busy = ref(false)
const error = ref("")
const success = ref("")
const filters = reactive({ item_code: "", supplier: "", from_date: "", to_date: "" })
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const costRuleOptions = computed(() => props.snapshot?.options?.operating_cost_rules || [])
const targetFieldOptions = computed(() => [{ label: "Do not import", value: "" }, ...(importInspection.value?.target_fields || [])])
const costCategoryOptions = ["Labour", "Packaging", "Delivery", "Utilities", "Rent", "Kitchen Consumables", "Transaction Fees", "Other Production Overhead"].map(value => ({ label: value, value }))
const invoiceFiles = ref([])
const invoiceBusy = ref(false)
const invoiceSaved = ref(null)
const invoiceExtraction = ref(null)
const invoiceExtractionStage = ref("")
const showInvoiceOcr = ref(false)
const invoice = reactive({ payee: "", invoice_number: "", invoice_date: new Date().toLocaleDateString("en-CA"), currency: "ZAR", tax_amount: 0, review_notes: "" })
const invoiceLines = reactive([newCostLine()])
const invoiceTotal = computed(() => invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0) + Number(invoice.tax_amount || 0))

function newCostLine() { return { description: "", cost_rule: "", cost_category: "Other Production Overhead", quantity: 1, unit_rate: 0, amount: 0, vat_amount: 0, accounting_category: "", notes: "" } }
function openRecords(doctype, create = false) { router.push({ name: create ? "AuxiliaryRecordCreate" : "BulkBiteSetupList", params: { doctype } }) }
function toggleField(field) { selectedFields.value = selectedFields.value.includes(field) ? selectedFields.value.filter(value => value !== field) : [...selectedFields.value, field] }
function downloadWorkbook() { window.location.assign(priceWorkbookUrl(selectedFields.value)) }
function uploadedFileUrl(file) { return file?.file_url || file?.message?.file_url || file?.data?.file_url || "" }

async function loadPage() {
  busy.value = true; error.value = ""
  try {
    const [contract, history] = await Promise.all([getPriceImportFields(), getPurchasePriceHistory(filters)])
    fieldContract.value = contract
    selectedFields.value = [...contract.default_fields]
    result.value = history
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function onImportUpload(file) {
  const fileUrl = uploadedFileUrl(file)
  if (!fileUrl) return (error.value = "The spreadsheet uploaded, but its private address was missing.")
  busy.value = true; error.value = ""; success.value = ""; importBatch.value = null
  try {
    importInspection.value = await inspectPriceFile(fileUrl)
    Object.keys(importMapping).forEach(key => delete importMapping[key])
    Object.assign(importMapping, importInspection.value.suggested_mapping)
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function previewImport() {
  busy.value = true; error.value = ""
  try { importBatch.value = await previewPriceWorkbook(importInspection.value.file_url, importMapping) }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function applyImport() {
  busy.value = true; error.value = ""
  try { importBatch.value = await applyPriceWorkbook(importBatch.value.name); success.value = "Catalogue prices updated. Stock was not changed."; await loadHistory() }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function loadHistory() {
  if (filters.from_date && filters.to_date && filters.from_date > filters.to_date) return (error.value = "From date must be on or before to date.")
  busy.value = true; error.value = ""
  try { result.value = await getPurchasePriceHistory(filters) }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function extractCostInvoice(files) {
  invoiceBusy.value = true; error.value = ""
  try {
    const job = await startCostInvoiceExtraction(files.map(file => file.file_url))
    const extracted = await waitForCostExtraction(job.job_id)
    invoiceExtraction.value = extracted
    if (extracted.payee) invoice.payee = extracted.payee
    if (extracted.supplier_invoice_number) invoice.invoice_number = extracted.supplier_invoice_number
    if (extracted.invoice_date) invoice.invoice_date = extracted.invoice_date
    if (extracted.tax_amount !== null && extracted.tax_amount !== undefined) invoice.tax_amount = Number(extracted.tax_amount)
    const rows = (extracted.cost_lines || []).map(row => ({ ...newCostLine(), ...row }))
    invoiceLines.splice(0, invoiceLines.length, ...(rows.length ? rows : [newCostLine()]))
  } catch (exception) { error.value = exception.message } finally { invoiceBusy.value = false }
}

async function waitForCostExtraction(jobId) {
  const deadline = Date.now() + 10 * 60 * 1000
  while (Date.now() < deadline) {
    const state = await getCostInvoiceExtractionStatus(jobId)
		invoiceExtractionStage.value = state.stage || state.status
    if (state.status === "finished") return state.result
    if (state.status === "failed") throw new Error(state.error || "Invoice extraction failed.")
    await new Promise(resolve => window.setTimeout(resolve, 1500))
  }
  throw new Error("Invoice extraction took too long. Try again or enter the costs manually.")
}

function changeCostRule(row, value) {
  row.cost_rule = value
  const rule = costRuleOptions.value.find(option => option.value === value)
  if (rule) { row.cost_category = rule.cost_category; row.unit_rate = Number(rule.rate || 0); row.amount = Number(row.quantity || 0) * row.unit_rate }
}
function updateCostAmount(row) { row.amount = Number(row.quantity || 0) * Number(row.unit_rate || 0) }
function addCostLine() { if (!invoiceSaved.value) invoiceLines.push(newCostLine()) }

async function saveCostInvoice() {
  if (!invoiceFiles.value.length || !invoice.payee || !invoice.invoice_date || !invoiceLines.length) return (error.value = "Add invoice evidence, a payee, a date, and at least one cost line.")
  invoiceBusy.value = true; error.value = ""
  try {
    invoiceSaved.value = await createCostInvoice({ ...invoice, evidence_files: invoiceFiles.value.map(file => ({ evidence_file: file.file_url, file_name: file.file_name })), costs: invoiceLines, subtotal_amount: invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0), total_amount: invoiceTotal.value, status: "Reviewed" })
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { invoiceBusy.value = false }
}

async function postInvoice() {
  invoiceBusy.value = true; error.value = ""
  try { invoiceSaved.value = await postCostInvoice(invoiceSaved.value.name); success.value = "The reviewed invoice was added to actual operating costs."; emit("changed") }
  catch (exception) { error.value = exception.message } finally { invoiceBusy.value = false }
}

function money(value) { return value === null || value === undefined ? "Not available" : `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function quantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }
function variance(row) { if (row.record_type !== "Actual" || row.variance === null || row.variance === undefined) return "No matching theory"; const sign = Number(row.variance) > 0 ? "+" : ""; return `${sign}${money(row.variance)} (${sign}${Number(row.variance_percent || 0).toFixed(1)}%)` }
function rowLabel(row) { return row.item_name || row.record_name || `Spreadsheet row ${row.row_number}` }
function statusTheme(status) { return status === "error" ? "red" : status === "unchanged" ? undefined : "green" }
function confidenceTheme(value) { return Number(value || 0) >= 85 ? "green" : Number(value || 0) >= 60 ? "orange" : "red" }

onMounted(loadPage)

// endregion FINANCE AND PRICE CATALOGUE WORKSPACE
</script>

<template>
  <section data-block="price-history" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">{{ mode === "catalogue" ? "Stock setup" : "Finance" }}</p><h1>{{ mode === "catalogue" ? "Price catalogue" : "Costs and finances" }}</h1><p>{{ mode === "catalogue" ? "Maintain the supplier prices used to calculate what stock should cost." : "Set expected costs, capture actual invoices, manage discounts, and see the result in Reports." }}</p></div><SystemBadge>{{ mode === "catalogue" ? "Does not change stock" : "Cost first" }}</SystemBadge></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div><div v-if="success" class="state-message" role="status">{{ success }}</div>

    <template v-if="mode === 'catalogue'">
      <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Download</p><h2>Choose the columns</h2><p>The file contains one header row and the catalogue data. Nothing else.</p></div></div><div class="field-choice-grid"><label v-for="field in fieldContract.fields" :key="field.fieldname"><SystemCheckbox :model-value="selectedFields.includes(field.fieldname)" @update:model-value="toggleField(field.fieldname)" /><span>{{ field.label }}</span></label></div><div class="button-row"><SystemOperationalButton variant="solid" :disabled="!selectedFields.length" @click="downloadWorkbook">Download price catalogue</SystemOperationalButton></div></section>
      <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Upload</p><h2>Match the spreadsheet columns</h2><p>BulkBite suggests matches. Change any match before previewing the import.</p></div></div><SystemFileUploader :upload-args="{ private: true }" :file-types="['.xlsx', '.xlsm', '.csv']" @success="onImportUpload"><template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading || busy" @click="upload.openFileSelector">{{ importInspection ? "Replace spreadsheet" : "Upload spreadsheet" }}</SystemOperationalButton></template></SystemFileUploader><div v-if="importInspection" class="mapping-list"><article v-for="source in importInspection.source_columns" :key="source.column"><div><strong>{{ source.column }}</strong><small>{{ source.samples.join(" · ") || "No sample value" }}</small></div><SystemSelect :model-value="importMapping[source.column]" :options="targetFieldOptions" placeholder="Do not import" @update:model-value="importMapping[source.column] = $event" /></article></div><div v-if="importInspection" class="button-row"><SystemOperationalButton variant="solid" :loading="busy" @click="previewImport">Preview {{ importInspection.row_count }} rows</SystemOperationalButton></div></section>
      <section v-if="importBatch" class="data-section"><div class="section-heading"><div><p class="eyebrow">Review</p><h2>Catalogue changes</h2><p>Nothing is applied until you confirm this preview.</p></div><SystemBadge :theme="importBatch.status === 'Applied' ? 'green' : undefined">{{ importBatch.status }}</SystemBadge></div><div class="metric-board metric-board--paper"><div><strong>{{ importBatch.counts.insert }}</strong><span>new</span></div><div><strong>{{ importBatch.counts.update }}</strong><span>updates</span></div><div><strong>{{ importBatch.counts.unchanged }}</strong><span>unchanged</span></div><div><strong>{{ importBatch.counts.error }}</strong><span>errors</span></div></div><div class="review-list"><article v-for="row in importBatch.rows" :key="row.row_number"><div><strong>{{ rowLabel(row) }}</strong><small>{{ row.supplier || `Row ${row.row_number}` }}</small></div><SystemBadge :theme="statusTheme(row.status)">{{ row.status }}</SystemBadge><p>{{ row.errors?.join(" ") || (row.changes?.length ? `${row.changes.length} fields will change.` : "No change.") }}</p></article></div><div class="button-row"><SystemOperationalButton v-if="importBatch.status !== 'Applied'" variant="solid" :disabled="importBatch.counts.error > 0" :loading="busy" @click="applyImport">Apply reviewed prices</SystemOperationalButton></div></section>
      <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Price history</p><h2>Theory versus receipt evidence</h2><p>Compare the expected stock-unit price with what reviewed receipts prove.</p></div></div><div class="field-grid"><SystemLinkedRecordField v-model="filters.item_code" label="Item" :options="itemOptions" placeholder="All items" /><SystemLinkedRecordField v-model="filters.supplier" label="Supplier" :options="supplierOptions" placeholder="All suppliers" /><SystemDatePicker v-model="filters.from_date" label="From date" format="YYYY-MM-DD" /><SystemDatePicker v-model="filters.to_date" label="To date" format="YYYY-MM-DD" /></div><div class="button-row"><SystemOperationalButton variant="outline" @click="loadHistory">Update history</SystemOperationalButton></div><div v-if="result.rows.length" class="price-table-wrap"><table class="price-table"><thead><tr><th>Date</th><th>Basis</th><th>Item</th><th>Supplier</th><th>Pack</th><th>Pack price</th><th>Price per stock unit</th><th>Theory</th><th>Difference</th></tr></thead><tbody><tr v-for="row in result.rows" :key="`${row.record_type}-${row.record_name}`"><td>{{ row.date }}</td><td>{{ row.record_type }}</td><td>{{ row.item_name }}</td><td>{{ row.supplier }}</td><td>{{ quantity(row.packs) }} × {{ quantity(row.units_per_pack) }} × {{ quantity(row.unit_size) }} {{ row.purchase_uom }}</td><td>{{ money(row.pack_price) }}</td><td>{{ money(row.stock_unit_price) }} / {{ row.stock_uom }}</td><td>{{ money(row.theory_stock_unit_price) }}</td><td>{{ variance(row) }}</td></tr></tbody></table></div></section>
    </template>

    <SystemTabs v-else default-value="costs" class="finance-tabs">
      <SystemTabsList class="finance-tabs__list"><SystemTabsTrigger value="costs">Costs</SystemTabsTrigger><SystemTabsTrigger value="invoice">Add cost invoice</SystemTabsTrigger><SystemTabsTrigger value="history">Cost history</SystemTabsTrigger></SystemTabsList>
      <SystemTabsContent value="costs" class="finance-tabs__content"><section class="finance-hero"><div><p class="eyebrow">Cost control</p><h2>Everything involved in making and delivering meals</h2><p>Expected costs describe the direction. Cost invoices and miscellaneous entries record what was actually paid.</p></div><SystemOperationalButton variant="solid" @click="openRecords('BulkBite Operating Cost Rule', true)">Add expected cost</SystemOperationalButton></section><div class="finance-action-grid"><article><h3>Employees and recurring costs</h3><p>Set employee type, hourly rate, employees required, hours, or weekly and monthly costs.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Operating Cost Rule')">Manage expected costs</SystemOperationalButton></article><article><h3>Discounts and savings</h3><p>Record discounts, rebates, free delivery, delivery fees, VAT adjustments, and other buying effects.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Price Adjustment')">Manage discounts</SystemOperationalButton></article><article><h3>Miscellaneous actual cost</h3><p>Add a one-off expense directly when it does not need a full invoice review.</p><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Cost Entry', true)">Add miscellaneous cost</SystemOperationalButton></article><article><h3>Financial result</h3><p>See food cost, operating costs, savings, revenue, and the result together.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'export')">Open Reports</SystemOperationalButton></article></div></SystemTabsContent>
      <SystemTabsContent value="invoice" class="finance-tabs__content">
        <section class="form-section">
          <div class="section-heading"><div><p class="eyebrow">Actual operating cost</p><h2>Upload and review an invoice</h2><p>Add all pages at once. BulkBite suggests costs and expected-rule matches for review.</p></div><SystemBadge v-if="invoiceSaved">{{ invoiceSaved.status }}</SystemBadge></div>
          <SystemMultiFileUploader v-model="invoiceFiles" :disabled="Boolean(invoiceSaved)" label="Add invoice files" @complete="extractCostInvoice" />
          <p v-if="invoiceBusy" class="field-note" role="status">{{ invoiceExtractionStage ? `Invoice processing: ${invoiceExtractionStage.replaceAll('_', ' ')}` : 'Reading invoice files and suggesting cost lines...' }}</p>
          <div v-if="invoiceExtraction" class="safety-note">
            <div class="extraction-summary"><div><strong>{{ invoiceExtraction.parser_mode || 'Invoice extraction' }}</strong><p>{{ invoiceExtraction.cost_lines?.length || 0 }} cost lines suggested at {{ Math.round(Number(invoiceExtraction.confidence || 0) * 100) }}% document confidence.</p></div><SystemOperationalButton variant="outline" @click="showInvoiceOcr = !showInvoiceOcr">{{ showInvoiceOcr ? 'Hide OCR text' : 'Show OCR text' }}</SystemOperationalButton></div>
            <p v-for="warning in invoiceExtraction.warnings || []" :key="warning">{{ warning }}</p>
            <pre v-if="showInvoiceOcr" class="invoice-ocr">{{ invoiceExtraction.ocr_text || 'No text was extracted.' }}</pre>
          </div>
          <div class="field-grid"><SystemFormControl v-model="invoice.payee" label="Supplier, employee, or payee" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="invoice.invoice_number" label="Invoice or reference number" :disabled="Boolean(invoiceSaved)" /><SystemDatePicker v-model="invoice.invoice_date" label="Invoice date" format="YYYY-MM-DD" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="invoice.tax_amount" label="VAT or tax" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" /></div>
          <div class="cost-line-list"><article v-for="(row, index) in invoiceLines" :key="index"><SystemFormControl v-model="row.description" label="Cost description" :disabled="Boolean(invoiceSaved)" /><SystemSelect :model-value="row.cost_rule" label="Expected cost match" :options="costRuleOptions" placeholder="No expected cost match" :disabled="Boolean(invoiceSaved)" @update:model-value="changeCostRule(row, $event)" /><SystemSelect v-model="row.cost_category" label="Cost category" :options="costCategoryOptions" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="row.quantity" label="Hours or quantity" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" @update:model-value="updateCostAmount(row)" /><SystemFormControl v-model="row.unit_rate" label="Rate" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" @update:model-value="updateCostAmount(row)" /><SystemFormControl v-model="row.amount" label="Line cost" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" /><div v-if="row.source_quote || row.notes || row.confidence" class="cost-line-review"><SystemBadge :theme="confidenceTheme(row.confidence)">{{ Math.round(Number(row.confidence || 0)) }}% confidence</SystemBadge><p v-if="row.source_quote"><strong>OCR source:</strong> {{ row.source_quote }}</p><p v-if="row.notes"><strong>Parser note:</strong> {{ row.notes }}</p></div></article></div>
          <div class="button-row"><SystemOperationalButton variant="outline" :disabled="Boolean(invoiceSaved)" @click="addCostLine">Add cost line</SystemOperationalButton><strong>{{ money(invoiceTotal) }}</strong><SystemOperationalButton v-if="!invoiceSaved" variant="solid" :loading="invoiceBusy" @click="saveCostInvoice">Save reviewed invoice</SystemOperationalButton><SystemOperationalButton v-else-if="!invoiceSaved.costs_posted" variant="solid" :loading="invoiceBusy" @click="postInvoice">Add to actual costs</SystemOperationalButton></div>
        </section>
      </SystemTabsContent>
      <SystemTabsContent value="history" class="finance-tabs__content"><section class="data-section"><div class="section-heading"><div><p class="eyebrow">Cost evidence</p><h2>Recent cost invoices</h2><p>See each invoice's reviewed lines, categories, total cost, and posting effect.</p></div><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Cost Invoice')">Open all cost invoices</SystemOperationalButton></div><div class="history-list"><article v-for="row in snapshot?.recent_cost_invoices || []" :key="row.name"><div><strong>{{ row.payee }}</strong><small>{{ row.invoice_date }} · {{ row.invoice_number || row.name }}</small><small>{{ row.line_count || 0 }} cost lines · {{ row.cost_categories || 'Uncategorised' }}</small></div><div><b>{{ money(row.total_amount) }}</b><SystemBadge :theme="row.costs_posted ? 'green' : undefined">{{ row.costs_posted ? `${row.posted_entry_count || row.line_count || 0} costs posted` : row.status }}</SystemBadge></div></article><p v-if="!snapshot?.recent_cost_invoices?.length" class="empty-state">No cost invoices have been recorded.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="openRecords('BulkBite Cost Entry')">View miscellaneous and posted costs</SystemOperationalButton><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'export')">View financial result</SystemOperationalButton></div></section></SystemTabsContent>
    </SystemTabs>
  </section>
</template>

<style scoped>
.extraction-summary{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-s)}.extraction-summary p{margin:.25rem 0 0}.invoice-ocr{max-height:20rem;margin:var(--spacing-s) 0 0;padding:var(--spacing-s);overflow:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-field);color:var(--theme-text);font-family:var(--font-family-c);font-size:var(--font-size--2);line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.cost-line-review{grid-column:1/-1;display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-3xs) var(--spacing-xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.cost-line-review p{margin:0}.cost-line-review strong{color:var(--theme-text)}
.field-choice-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-2xs) var(--spacing-m)}.field-choice-grid label{display:flex;align-items:center;gap:var(--spacing-xs);min-height:2.75rem}.mapping-list,.review-list,.history-list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.mapping-list article,.review-list article,.history-list article{display:grid;grid-template-columns:minmax(0,1fr) minmax(12rem,20rem);align-items:center;gap:var(--spacing-s);padding:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.mapping-list article:last-child,.review-list article:last-child,.history-list article:last-child{border-bottom:0}.mapping-list small,.review-list small,.history-list small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.review-list article{grid-template-columns:minmax(0,1fr) auto}.review-list p{grid-column:1/-1;margin:0;color:var(--theme-text-muted)}.finance-tabs{display:grid;gap:var(--spacing-m)}.finance-tabs__list{width:fit-content;max-width:100%;overflow-x:auto}.finance-tabs__content{display:grid;gap:var(--spacing-m);outline:none}.finance-hero{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);padding:var(--spacing-l);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.finance-hero h2,.finance-action-grid h3{margin:0}.finance-hero p,.finance-action-grid p{color:var(--theme-text-muted)}.finance-action-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-m)}.finance-action-grid article{display:grid;align-content:start;gap:var(--spacing-xs);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.cost-line-list{display:grid;gap:var(--spacing-s)}.cost-line-list article{display:grid;grid-template-columns:1.5fr 1fr 1fr repeat(3,minmax(8rem,.6fr));gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.history-list article>div:last-child{display:flex;align-items:center;justify-content:flex-end;gap:var(--spacing-xs)}.price-table-wrap{max-width:100%;overflow-x:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card)}.price-table{width:100%;min-width:72rem;border-collapse:collapse;background:var(--theme-surface-raised)}.price-table th,.price-table td{padding:var(--spacing-xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);text-align:left;vertical-align:top}.price-table th{background:var(--theme-secondary);color:var(--theme-text-muted);white-space:nowrap}.empty-state{margin:0;padding:var(--spacing-l);color:var(--theme-text-muted);text-align:center}@media(max-width:980px){.field-choice-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cost-line-list article{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.field-choice-grid,.finance-action-grid,.cost-line-list article{grid-template-columns:1fr}.mapping-list article,.history-list article{grid-template-columns:1fr}.finance-hero{align-items:flex-start;flex-direction:column}}
</style>
