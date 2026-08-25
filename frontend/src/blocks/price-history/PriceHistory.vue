<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import {
  SystemBadge, SystemCheckbox, SystemDatePicker, SystemFileUploader, SystemFormControl,
  SystemLinkedRecordField, SystemMultiFileUploader, SystemOperationalButton, SystemSelect,
  SystemTabs, SystemTabsContent, SystemTabsList, SystemTabsTrigger,
} from "@/desyium"
import {
  applyPriceWorkbook, createCostInvoice, getCostInvoiceExtractionStatus, getFinanceWorkspace,
  getPriceImportFields, getPurchasePriceHistory, inspectPriceFile, postCostInvoice,
  previewPriceWorkbook, priceWorkbookUrl, saveExpectedCostRule, saveMiscellaneousCost,
  savePriceAdjustment, startCostInvoiceExtraction,
} from "@/resources/api"

// =============================================================================
// region FINANCE AND PRICE CATALOGUE WORKSPACE
// =============================================================================

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null }, mode: { type: String, default: "finance" } })
const emit = defineEmits(["open-workflow", "changed"])
const router = useRouter()
const today = () => new Date().toLocaleDateString("en-CA")

// region 1. SHARED STATE

const busy = ref(false)
const error = ref("")
const success = ref("")
const finance = ref(null)

function clearMessages() { error.value = ""; success.value = "" }
function openRecords(doctype, create = false) { router.push({ name: create ? "AuxiliaryRecordCreate" : "BulkBiteSetupList", params: { doctype } }) }
function money(value) { return value === null || value === undefined ? "Not available" : `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function quantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }
function statusTheme(status) { return status === "error" ? "red" : status === "unchanged" ? undefined : "green" }
function confidenceTheme(value) { return Number(value || 0) >= 85 ? "green" : Number(value || 0) >= 60 ? "orange" : "red" }

// endregion 1. SHARED STATE

// region 1. CATALOGUE EXCHANGE

const result = ref({ rows: [], summary: { theory_count: 0, actual_count: 0, item_count: 0, supplier_count: 0 } })
const fieldContract = ref({ fields: [], default_fields: [] })
const selectedFields = ref([])
const importInspection = ref(null)
const importMapping = reactive({})
const importBatch = ref(null)
const filters = reactive({ item_code: "", supplier: "", from_date: "", to_date: "" })
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const targetFieldOptions = computed(() => [{ label: "Do not import", value: "" }, ...(importInspection.value?.target_fields || [])])

function toggleField(field) { selectedFields.value = selectedFields.value.includes(field) ? selectedFields.value.filter(value => value !== field) : [...selectedFields.value, field] }
function downloadWorkbook() { window.location.assign(priceWorkbookUrl(selectedFields.value)) }
function uploadedFileUrl(file) { return file?.file_url || file?.message?.file_url || file?.data?.file_url || "" }
function variance(row) { if (row.record_type !== "Actual" || row.variance === null || row.variance === undefined) return "No matching theory"; const sign = Number(row.variance) > 0 ? "+" : ""; return `${sign}${money(row.variance)} (${sign}${Number(row.variance_percent || 0).toFixed(1)}%)` }
function rowLabel(row) { return row.item_name || row.record_name || `Spreadsheet row ${row.row_number}` }

async function loadCatalogue() {
  busy.value = true; clearMessages()
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
  busy.value = true; clearMessages(); importBatch.value = null
  try {
    importInspection.value = await inspectPriceFile(fileUrl)
    Object.keys(importMapping).forEach(key => delete importMapping[key])
    Object.assign(importMapping, importInspection.value.suggested_mapping)
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function previewImport() {
  busy.value = true; clearMessages()
  try { importBatch.value = await previewPriceWorkbook(importInspection.value.file_url, importMapping) }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function applyImport() {
  busy.value = true; clearMessages()
  try { importBatch.value = await applyPriceWorkbook(importBatch.value.name); success.value = "Catalogue prices updated. Stock was not changed."; await loadPriceHistory() }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function loadPriceHistory() {
  if (filters.from_date && filters.to_date && filters.from_date > filters.to_date) return (error.value = "From date must be on or before to date.")
  busy.value = true; clearMessages()
  try { result.value = await getPurchasePriceHistory(filters) }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

// endregion 1. CATALOGUE EXCHANGE

// region 1. FINANCE OVERVIEW

async function loadFinance() {
  busy.value = true; clearMessages()
  try { finance.value = await getFinanceWorkspace() }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function refreshFinance(message) {
  await loadFinance()
  if (!error.value && message) success.value = message
  emit("changed")
}

// endregion 1. FINANCE OVERVIEW

// region 1. EXPECTED COST RULES

const costCategories = ["Labour", "Packaging", "Delivery", "Utilities", "Rent", "Kitchen Consumables", "Transaction Fees", "Other Production Overhead"]
const costCategoryOptions = costCategories.map(value => ({ label: value, value }))
const expectedCostCategoryOptions = costCategories.filter(value => value !== "Labour").map(value => ({ label: value, value }))
const costBasisOptions = ["Fixed", "Hourly", "Per Meal", "Per Customer", "Per Kg", "Percentage of Revenue"].map(value => ({ label: value, value }))
const recurrenceOptions = ["Once", "Weekly", "Monthly", "Per Period"].map(value => ({ label: value, value }))
const vatOptions = ["Inclusive", "Exclusive", "No VAT"].map(value => ({ label: value, value }))
const expectedSaving = ref(false)
const expectedCost = reactive(newExpectedCost())
const expectedPreview = computed(() => Number(expectedCost.default_quantity || 0) * Number(expectedCost.rate || 0))

function newExpectedCost() {
  return { name: "", cost_name: "", cost_category: "Utilities", basis: "Fixed", rate: 0, employee_count: 1, hours_per_employee: 0, default_quantity: 1, recurrence: "Monthly", effective_from: today(), effective_to: "", vat_treatment: "Inclusive", accounting_category: "", payee: "", enabled: 1, notes: "" }
}
function resetExpectedCost() { Object.assign(expectedCost, newExpectedCost()) }
function editExpectedCost(row) { Object.assign(expectedCost, newExpectedCost(), row); window.setTimeout(() => document.querySelector("[data-finance-form='expected']")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0) }

async function submitExpectedCost() {
  expectedSaving.value = true; clearMessages()
  try { await saveExpectedCostRule({ ...expectedCost }); resetExpectedCost(); await refreshFinance("Expected cost saved.") }
  catch (exception) { error.value = exception.message } finally { expectedSaving.value = false }
}

// endregion 1. EXPECTED COST RULES

// region 1. MISCELLANEOUS ACTUAL COST

const miscSaving = ref(false)
const miscFiles = ref([])
const miscellaneousCost = reactive(newMiscellaneousCost())
const miscTotal = computed(() => Number(miscellaneousCost.amount || 0) || Number(miscellaneousCost.quantity || 0) * Number(miscellaneousCost.unit_rate || 0))
const costRuleOptions = computed(() => (finance.value?.expected_costs || []).filter(row => row.enabled).map(row => ({ label: row.cost_name, value: row.name, cost_category: row.cost_category, rate: row.rate })))

function newMiscellaneousCost() { return { cost_date: today(), cost_rule: "", cost_category: "Other Production Overhead", payee: "", quantity: 1, unit_rate: 0, amount: 0, vat_amount: 0, accounting_category: "", notes: "" } }
function changeMiscCostRule(value) { miscellaneousCost.cost_rule = value; const rule = costRuleOptions.value.find(option => option.value === value); if (rule) { miscellaneousCost.cost_category = rule.cost_category; miscellaneousCost.unit_rate = Number(rule.rate || 0); miscellaneousCost.amount = 0 } }
function resetMiscellaneousCost() { Object.assign(miscellaneousCost, newMiscellaneousCost()); miscFiles.value = [] }

async function submitMiscellaneousCost() {
  miscSaving.value = true; clearMessages()
  try {
    await saveMiscellaneousCost({ ...miscellaneousCost, amount: miscTotal.value, evidence_files: miscFiles.value.map(file => ({ evidence_file: file.file_url, file_name: file.file_name })) })
    resetMiscellaneousCost(); await refreshFinance("Actual cost added.")
  } catch (exception) { error.value = exception.message } finally { miscSaving.value = false }
}

// endregion 1. MISCELLANEOUS ACTUAL COST

// region 1. PRICE ADJUSTMENTS

const adjustmentSaving = ref(false)
const adjustment = reactive(newAdjustment())
const adjustmentTypeOptions = ["Percentage Discount", "Fixed Discount", "Rebate", "Delivery Fee", "Free Delivery", "Service Fee", "VAT Adjustment", "Other Saving", "Other Cost"].map(value => ({ label: value, value }))
const scopeOptions = ["Global", "Supplier", "Item Category", "Item", "Supplier Offer", "Basket"].map(value => ({ label: value, value }))
const calculationOptions = ["Pack Price", "Basket Subtotal", "Fixed"].map(value => ({ label: value, value }))
const adjustmentVatOptions = ["As Configured", "Inclusive", "Exclusive", "No VAT"].map(value => ({ label: value, value }))
const adjustmentTarget = computed(() => ({
  Supplier: { field: "supplier", label: "Supplier", options: finance.value?.options?.suppliers || [], doctype: "BulkBite Supplier" },
  "Item Category": { field: "item_category", label: "Item category", options: finance.value?.options?.item_categories || [], doctype: "BulkBite Item Category" },
  Item: { field: "item_code", label: "Item", options: finance.value?.options?.items || [], doctype: "BulkBite Item" },
  "Supplier Offer": { field: "supplier_offer", label: "Supplier offer", options: finance.value?.options?.supplier_offers || [], doctype: "BulkBite Supplier Offer" },
}[adjustment.scope_type] || null))

function newAdjustment() { return { name: "", adjustment_name: "", scope_type: "Global", supplier_offer: "", supplier: "", item_code: "", item_category: "", adjustment_type: "Percentage Discount", calculation_basis: "Pack Price", value: 0, threshold_amount: 0, effective_from: today(), effective_to: "", priority: 100, stackable: 1, vat_treatment: "As Configured", enabled: 1, notes: "" } }
function resetAdjustment() { Object.assign(adjustment, newAdjustment()) }
function editAdjustment(row) { Object.assign(adjustment, newAdjustment(), row); window.setTimeout(() => document.querySelector("[data-finance-form='adjustment']")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0) }
async function submitAdjustment() {
  adjustmentSaving.value = true; clearMessages()
  try { await savePriceAdjustment({ ...adjustment }); resetAdjustment(); await refreshFinance("Discount or buying cost saved.") }
  catch (exception) { error.value = exception.message } finally { adjustmentSaving.value = false }
}

// endregion 1. PRICE ADJUSTMENTS

// region 1. COST INVOICE REVIEW

const invoiceFiles = ref([])
const invoiceBusy = ref(false)
const invoiceSaved = ref(null)
const invoiceExtraction = ref(null)
const invoiceExtractionStage = ref("")
const showInvoiceOcr = ref(false)
const invoice = reactive({ payee: "", invoice_number: "", invoice_date: today(), currency: "ZAR", tax_amount: 0, review_notes: "" })
const invoiceLines = reactive([newCostLine()])
const invoiceTotal = computed(() => invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0) + Number(invoice.tax_amount || 0))

function newCostLine() { return { description: "", cost_rule: "", cost_category: "Other Production Overhead", quantity: 1, unit_rate: 0, amount: 0, vat_amount: 0, accounting_category: "", notes: "" } }
function updateCostAmount(row) { row.amount = Math.round(Number(row.quantity || 0) * Number(row.unit_rate || 0) * 100) / 100 }
function changeCostRule(row, value) { row.cost_rule = value; const rule = costRuleOptions.value.find(option => option.value === value); if (rule) { row.cost_category = rule.cost_category; row.unit_rate = Number(rule.rate || 0); updateCostAmount(row) } }
function addCostLine() { if (!invoiceSaved.value) invoiceLines.push(newCostLine()) }

async function extractCostInvoice(files) {
  invoiceBusy.value = true; clearMessages()
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

async function saveCostInvoice() {
  if (!invoiceFiles.value.length || !invoice.payee || !invoice.invoice_date || !invoiceLines.length) return (error.value = "Add invoice evidence, a payee, a date, and at least one cost line.")
  invoiceBusy.value = true; clearMessages()
  try {
    invoiceSaved.value = await createCostInvoice({ ...invoice, evidence_files: invoiceFiles.value.map(file => ({ evidence_file: file.file_url, file_name: file.file_name })), costs: invoiceLines, subtotal_amount: invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0), total_amount: invoiceTotal.value, status: "Reviewed" })
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { invoiceBusy.value = false }
}

async function postInvoice() {
  invoiceBusy.value = true; clearMessages()
  try { invoiceSaved.value = await postCostInvoice(invoiceSaved.value.name); await refreshFinance("The reviewed invoice was added to actual operating costs.") }
  catch (exception) { error.value = exception.message } finally { invoiceBusy.value = false }
}

// endregion 1. COST INVOICE REVIEW

onMounted(() => props.mode === "catalogue" ? loadCatalogue() : loadFinance())

// endregion FINANCE AND PRICE CATALOGUE WORKSPACE
</script>

<template>
  <section data-block="price-history" class="workflow-block">
    <header class="workflow-header">
      <div><p class="eyebrow">{{ mode === "catalogue" ? "Stock setup" : "Finance" }}</p><h1>{{ mode === "catalogue" ? "Price catalogue" : "Costs and finances" }}</h1><p>{{ mode === "catalogue" ? "Maintain the supplier prices used to calculate what stock should cost." : "Plan employee and operating costs, record what was paid, and track discounts in one place." }}</p></div>
      <SystemBadge>{{ mode === "catalogue" ? "Does not change stock" : "Cost control" }}</SystemBadge>
    </header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="success" class="state-message" role="status">{{ success }}</div>

    <template v-if="mode === 'catalogue'">
      <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Download</p><h2>Choose the columns</h2><p>The file contains one header row and the catalogue data. Nothing else.</p></div></div><div class="field-choice-grid"><label v-for="field in fieldContract.fields" :key="field.fieldname"><SystemCheckbox :model-value="selectedFields.includes(field.fieldname)" @update:model-value="toggleField(field.fieldname)" /><span>{{ field.label }}</span></label></div><div class="button-row"><SystemOperationalButton variant="solid" :disabled="!selectedFields.length" @click="downloadWorkbook">Download price catalogue</SystemOperationalButton></div></section>
      <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Upload</p><h2>Match the spreadsheet columns</h2><p>BulkBite suggests matches. Change any match before previewing the import.</p></div></div><SystemFileUploader :upload-args="{ private: true }" :file-types="['.xlsx', '.xlsm', '.csv']" @success="onImportUpload"><template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading || busy" @click="upload.openFileSelector">{{ importInspection ? "Replace spreadsheet" : "Upload spreadsheet" }}</SystemOperationalButton></template></SystemFileUploader><div v-if="importInspection" class="mapping-list"><article v-for="source in importInspection.source_columns" :key="source.column"><div><strong>{{ source.column }}</strong><small>{{ source.samples.join(" · ") || "No sample value" }}</small></div><SystemSelect :model-value="importMapping[source.column]" :options="targetFieldOptions" placeholder="Do not import" @update:model-value="importMapping[source.column] = $event" /></article></div><div v-if="importInspection" class="button-row"><SystemOperationalButton variant="solid" :loading="busy" @click="previewImport">Preview {{ importInspection.row_count }} rows</SystemOperationalButton></div></section>
      <section v-if="importBatch" class="data-section"><div class="section-heading"><div><p class="eyebrow">Review</p><h2>Catalogue changes</h2><p>Nothing is applied until you confirm this preview.</p></div><SystemBadge :theme="importBatch.status === 'Applied' ? 'green' : undefined">{{ importBatch.status }}</SystemBadge></div><div class="metric-board metric-board--paper"><div><strong>{{ importBatch.counts.insert }}</strong><span>new</span></div><div><strong>{{ importBatch.counts.update }}</strong><span>updates</span></div><div><strong>{{ importBatch.counts.unchanged }}</strong><span>unchanged</span></div><div><strong>{{ importBatch.counts.error }}</strong><span>errors</span></div></div><div class="review-list"><article v-for="row in importBatch.rows" :key="row.row_number"><div><strong>{{ rowLabel(row) }}</strong><small>{{ row.supplier || `Row ${row.row_number}` }}</small></div><SystemBadge :theme="statusTheme(row.status)">{{ row.status }}</SystemBadge><p>{{ row.errors?.join(" ") || (row.changes?.length ? `${row.changes.length} fields will change.` : "No change.") }}</p></article></div><div class="button-row"><SystemOperationalButton v-if="importBatch.status !== 'Applied'" variant="solid" :disabled="importBatch.counts.error > 0" :loading="busy" @click="applyImport">Apply reviewed prices</SystemOperationalButton></div></section>
      <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Price history</p><h2>Theory versus receipt evidence</h2><p>Compare the expected stock-unit price with what reviewed receipts prove.</p></div></div><div class="field-grid"><SystemLinkedRecordField v-model="filters.item_code" label="Item" :options="itemOptions" placeholder="All items" /><SystemLinkedRecordField v-model="filters.supplier" label="Supplier" :options="supplierOptions" placeholder="All suppliers" /><SystemDatePicker v-model="filters.from_date" label="From date" format="YYYY-MM-DD" /><SystemDatePicker v-model="filters.to_date" label="To date" format="YYYY-MM-DD" /></div><div class="button-row"><SystemOperationalButton variant="outline" @click="loadPriceHistory">Update history</SystemOperationalButton></div><div v-if="result.rows.length" class="price-table-wrap"><table class="price-table"><thead><tr><th>Date</th><th>Basis</th><th>Item</th><th>Supplier</th><th>Pack</th><th>Pack price</th><th>Price per stock unit</th><th>Theory</th><th>Difference</th></tr></thead><tbody><tr v-for="row in result.rows" :key="`${row.record_type}-${row.record_name}`"><td>{{ row.date }}</td><td>{{ row.record_type }}</td><td>{{ row.item_name }}</td><td>{{ row.supplier }}</td><td>{{ quantity(row.packs) }} × {{ quantity(row.units_per_pack) }} × {{ quantity(row.unit_size) }} {{ row.purchase_uom }}</td><td>{{ money(row.pack_price) }}</td><td>{{ money(row.stock_unit_price) }} / {{ row.stock_uom }}</td><td>{{ money(row.theory_stock_unit_price) }}</td><td>{{ variance(row) }}</td></tr></tbody></table></div></section>
    </template>

    <SystemTabs v-else default-value="overview" class="finance-tabs">
      <SystemTabsList class="finance-tabs__list"><SystemTabsTrigger value="overview">Overview</SystemTabsTrigger><SystemTabsTrigger value="expected">Expected costs</SystemTabsTrigger><SystemTabsTrigger value="actual">Actual costs</SystemTabsTrigger><SystemTabsTrigger value="discounts">Discounts</SystemTabsTrigger><SystemTabsTrigger value="history">History</SystemTabsTrigger></SystemTabsList>

      <SystemTabsContent value="overview" class="finance-tabs__content">
        <section class="finance-overview"><div class="section-heading"><div><p class="eyebrow">This month</p><h2>Operating cost position</h2><p v-if="finance">{{ finance.period.from_date }} to {{ finance.period.to_date }}</p></div><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'export')">Open Reports</SystemOperationalButton></div><div class="finance-metrics"><article><span>Expected operating costs</span><strong>{{ money(finance?.summary?.expected_total) }}</strong><small>Employee and recurring rules</small></article><article><span>Actual operating costs</span><strong>{{ money(finance?.summary?.actual_total) }}</strong><small>Posted invoices and direct costs</small></article><article><span>Cost variance</span><strong>{{ money(finance?.summary?.variance) }}</strong><small>Actual less expected</small></article><article><span>Expected savings</span><strong>{{ money(finance?.summary?.expected_savings) }}</strong><small>{{ finance?.summary?.active_adjustments || 0 }} active rules</small></article></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Where money is going</p><h2>Cost categories</h2><p>Expected and actual operating costs for the current month.</p></div></div><div class="category-list"><article v-for="row in finance?.breakdown || []" :key="row.category"><strong>{{ row.category }}</strong><span>{{ money(row.expected) }} expected</span><span>{{ money(row.actual) }} actual</span><SystemBadge :theme="Number(row.variance) <= 0 ? 'green' : 'orange'">{{ money(row.variance) }} variance</SystemBadge></article><p v-if="!finance?.breakdown?.length" class="empty-state">Add an expected cost or an actual cost to start the comparison.</p></div></section>
      </SystemTabsContent>

      <SystemTabsContent value="expected" class="finance-tabs__content">
        <section class="finance-workforce"><div class="section-heading"><div><p class="eyebrow">Employee capacity and cost</p><h2>Expected workforce</h2><p>Employee types and profiles are managed under Production. Finance shows the capacity and labour effect.</p></div><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'employees')">Manage employees</SystemOperationalButton></div><div class="category-list"><article v-for="row in finance?.workforce?.rows || []" :key="row.name"><strong>{{ row.employee_type_name }}</strong><span>{{ row.required_workers }} needed / {{ row.active_workers }} active</span><span>{{ money(row.expected_monthly_cost) }} expected</span><SystemBadge :theme="row.status === 'Under capacity' ? 'orange' : row.status === 'At capacity' ? 'green' : undefined">{{ row.status }}</SystemBadge></article><p v-if="!finance?.workforce?.rows?.length" class="empty-state">Add employee types under Production to calculate workforce capacity and expected labour.</p></div></section>
        <section class="form-section" data-finance-form="expected"><div class="section-heading"><div><p class="eyebrow">Other expected costs</p><h2>{{ expectedCost.name ? 'Edit expected cost' : 'Add an expected cost' }}</h2><p>Add power, rent, utilities, packaging, delivery, and other configurable operating costs here.</p></div><SystemBadge v-if="expectedCost.name">Editing</SystemBadge></div>
          <div class="field-grid field-grid--wide"><SystemFormControl v-model="expectedCost.cost_name" label="Cost type" placeholder="Kitchen electricity" /><SystemSelect v-model="expectedCost.cost_category" label="Cost category" :options="expectedCostCategoryOptions" /><SystemSelect v-model="expectedCost.basis" label="How it is calculated" :options="costBasisOptions" /><SystemFormControl v-model="expectedCost.rate" label="Rate (R)" type="number" step="0.1" /></div>
          <div class="field-grid"><SystemFormControl v-model="expectedCost.default_quantity" label="Expected quantity" type="number" step="0.1" /><div class="calculated-field"><span>Cost at expected quantity</span><strong>{{ money(expectedPreview) }}</strong><small>{{ quantity(expectedCost.default_quantity) }} × {{ money(expectedCost.rate) }}</small></div></div>
          <div class="field-grid"><SystemSelect v-model="expectedCost.recurrence" label="Repeats" :options="recurrenceOptions" /><SystemDatePicker v-model="expectedCost.effective_from" label="Effective from" format="YYYY-MM-DD" /><SystemDatePicker v-model="expectedCost.effective_to" label="Effective to" format="YYYY-MM-DD" /><SystemFormControl v-model="expectedCost.payee" label="Usual employee or payee" /><SystemSelect v-model="expectedCost.vat_treatment" label="VAT treatment" :options="vatOptions" /><SystemFormControl v-model="expectedCost.notes" label="Notes" /></div>
          <label class="check-field"><SystemCheckbox v-model="expectedCost.enabled" /><span>Include this cost in planning</span></label><div class="button-row"><SystemOperationalButton v-if="expectedCost.name" variant="outline" @click="resetExpectedCost">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="expectedSaving" @click="submitExpectedCost">{{ expectedCost.name ? 'Save changes' : 'Add expected cost' }}</SystemOperationalButton></div>
        </section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Current cost model</p><h2>Recurring and miscellaneous costs</h2><p>The period value uses the current month's dates and production drivers.</p></div></div><div class="record-list"><article v-for="row in finance?.expected_costs || []" :key="row.name"><div><strong>{{ row.cost_name }}</strong><small>{{ row.cost_category }} · {{ row.basis }} · {{ row.recurrence }}</small><small>{{ quantity(row.default_quantity) }} expected · {{ money(row.rate) }} rate</small></div><div><b>{{ money(row.period_amount) }}</b><SystemBadge :theme="row.enabled ? 'green' : undefined">{{ row.enabled ? 'Active' : 'Disabled' }}</SystemBadge><SystemOperationalButton variant="outline" @click="editExpectedCost(row)">Edit</SystemOperationalButton></div></article><p v-if="!finance?.expected_costs?.length" class="empty-state">No recurring or miscellaneous costs have been set.</p></div></section>
      </SystemTabsContent>

      <SystemTabsContent value="actual" class="finance-tabs__content">
        <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Quick actual cost</p><h2>Add a miscellaneous expense</h2><p>Use this for a single expense. Use the invoice review below when a document contains several costs.</p></div><strong>{{ money(miscTotal) }}</strong></div><div class="field-grid"><SystemDatePicker v-model="miscellaneousCost.cost_date" label="Cost date" format="YYYY-MM-DD" /><SystemSelect :model-value="miscellaneousCost.cost_rule" label="Expected cost match" :options="costRuleOptions" placeholder="No expected match" @update:model-value="changeMiscCostRule" /><SystemSelect v-model="miscellaneousCost.cost_category" label="Cost category" :options="costCategoryOptions" /><SystemFormControl v-model="miscellaneousCost.payee" label="Employee, supplier, or payee" /></div><div class="field-grid"><SystemFormControl v-model="miscellaneousCost.quantity" label="Hours or quantity" type="number" step="0.1" /><SystemFormControl v-model="miscellaneousCost.unit_rate" label="Rate (R)" type="number" step="0.1" /><SystemFormControl v-model="miscellaneousCost.amount" label="Actual cost (R)" type="number" step="0.1" description="Leave at 0 to calculate quantity × rate." /><SystemFormControl v-model="miscellaneousCost.vat_amount" label="VAT amount (R)" type="number" step="0.1" /><SystemFormControl v-model="miscellaneousCost.notes" label="Notes" /></div><SystemMultiFileUploader v-model="miscFiles" label="Add expense evidence" /><div class="button-row"><SystemOperationalButton variant="solid" :loading="miscSaving" @click="submitMiscellaneousCost">Add actual cost</SystemOperationalButton></div></section>
        <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Actual operating-cost invoice</p><h2>Upload and review an invoice</h2><p>Add all pages at once. BulkBite suggests costs and expected-rule matches, then waits for your review.</p></div><SystemBadge v-if="invoiceSaved">{{ invoiceSaved.status }}</SystemBadge></div><SystemMultiFileUploader v-model="invoiceFiles" :disabled="Boolean(invoiceSaved)" label="Add invoice files" @complete="extractCostInvoice" /><p v-if="invoiceBusy" class="field-note" role="status">{{ invoiceExtractionStage ? `Invoice processing: ${invoiceExtractionStage.replaceAll('_', ' ')}` : 'Reading invoice files and suggesting cost lines...' }}</p><div v-if="invoiceExtraction" class="safety-note"><div class="extraction-summary"><div><strong>{{ invoiceExtraction.parser_mode || 'Invoice extraction' }}</strong><p>{{ invoiceExtraction.cost_lines?.length || 0 }} cost lines suggested at {{ Math.round(Number(invoiceExtraction.confidence || 0) * 100) }}% document confidence.</p></div><SystemOperationalButton variant="outline" @click="showInvoiceOcr = !showInvoiceOcr">{{ showInvoiceOcr ? 'Hide OCR text' : 'Show OCR text' }}</SystemOperationalButton></div><p v-for="warning in invoiceExtraction.warnings || []" :key="warning">{{ warning }}</p><pre v-if="showInvoiceOcr" class="invoice-ocr">{{ invoiceExtraction.ocr_text || 'No text was extracted.' }}</pre></div><div class="field-grid"><SystemFormControl v-model="invoice.payee" label="Supplier, employee, or payee" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="invoice.invoice_number" label="Invoice or reference number" :disabled="Boolean(invoiceSaved)" /><SystemDatePicker v-model="invoice.invoice_date" label="Invoice date" format="YYYY-MM-DD" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="invoice.tax_amount" label="VAT or tax" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" /></div><div class="cost-line-list"><article v-for="(row, index) in invoiceLines" :key="index"><SystemFormControl v-model="row.description" label="Cost description" :disabled="Boolean(invoiceSaved)" /><SystemSelect :model-value="row.cost_rule" label="Expected cost match" :options="costRuleOptions" placeholder="No expected cost match" :disabled="Boolean(invoiceSaved)" @update:model-value="changeCostRule(row, $event)" /><SystemSelect v-model="row.cost_category" label="Cost category" :options="costCategoryOptions" :disabled="Boolean(invoiceSaved)" /><SystemFormControl v-model="row.quantity" label="Hours or quantity" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" @update:model-value="updateCostAmount(row)" /><SystemFormControl v-model="row.unit_rate" label="Rate" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" @update:model-value="updateCostAmount(row)" /><SystemFormControl v-model="row.amount" label="Line cost" type="number" step="0.1" :disabled="Boolean(invoiceSaved)" /><div v-if="row.source_quote || row.notes || row.confidence" class="cost-line-review"><SystemBadge :theme="confidenceTheme(row.confidence)">{{ Math.round(Number(row.confidence || 0)) }}% confidence</SystemBadge><p v-if="row.source_quote"><strong>OCR source:</strong> {{ row.source_quote }}</p><p v-if="row.notes"><strong>Parser note:</strong> {{ row.notes }}</p></div></article></div><div class="button-row"><SystemOperationalButton variant="outline" :disabled="Boolean(invoiceSaved)" @click="addCostLine">Add cost line</SystemOperationalButton><strong>{{ money(invoiceTotal) }}</strong><SystemOperationalButton v-if="!invoiceSaved" variant="solid" :loading="invoiceBusy" @click="saveCostInvoice">Save reviewed invoice</SystemOperationalButton><SystemOperationalButton v-else-if="!invoiceSaved.costs_posted" variant="solid" :loading="invoiceBusy" @click="postInvoice">Add to actual costs</SystemOperationalButton></div></section>
      </SystemTabsContent>

      <SystemTabsContent value="discounts" class="finance-tabs__content">
        <section class="form-section" data-finance-form="adjustment"><div class="section-heading"><div><p class="eyebrow">Discounts and buying costs</p><h2>{{ adjustment.name ? 'Edit discount or cost' : 'Add a discount or cost' }}</h2><p>Model discounts, rebates, free delivery, fees, VAT changes, and other savings or costs.</p></div><SystemBadge v-if="adjustment.name">Editing</SystemBadge></div><div class="field-grid"><SystemFormControl v-model="adjustment.adjustment_name" label="Discount or cost name" /><SystemSelect v-model="adjustment.adjustment_type" label="Type" :options="adjustmentTypeOptions" /><SystemSelect v-model="adjustment.scope_type" label="Applies to" :options="scopeOptions" /><SystemLinkedRecordField v-if="adjustmentTarget" v-model="adjustment[adjustmentTarget.field]" :label="adjustmentTarget.label" :options="adjustmentTarget.options" @create="openRecords(adjustmentTarget.doctype, true)" @manage="openRecords(adjustmentTarget.doctype)" /></div><div class="field-grid"><SystemSelect v-model="adjustment.calculation_basis" label="Calculation basis" :options="calculationOptions" /><SystemFormControl v-model="adjustment.value" label="Rate or amount" type="number" step="0.1" /><SystemFormControl v-model="adjustment.threshold_amount" label="Minimum basket amount" type="number" step="0.1" /><SystemFormControl v-model="adjustment.priority" label="Priority" type="number" step="1" /><SystemDatePicker v-model="adjustment.effective_from" label="Effective from" format="YYYY-MM-DD" /><SystemDatePicker v-model="adjustment.effective_to" label="Effective to" format="YYYY-MM-DD" /><SystemSelect v-model="adjustment.vat_treatment" label="VAT treatment" :options="adjustmentVatOptions" /><SystemFormControl v-model="adjustment.notes" label="Notes or source" /></div><div class="check-row"><label class="check-field"><SystemCheckbox v-model="adjustment.stackable" /><span>Can combine with other discounts</span></label><label class="check-field"><SystemCheckbox v-model="adjustment.enabled" /><span>Use this rule in planning</span></label></div><div class="button-row"><SystemOperationalButton v-if="adjustment.name" variant="outline" @click="resetAdjustment">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="adjustmentSaving" @click="submitAdjustment">{{ adjustment.name ? 'Save changes' : 'Add discount or cost' }}</SystemOperationalButton></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Current rules</p><h2>Discounts, savings, and added costs</h2><p>These rules feed theoretical buying costs and the saving analysis in Reports.</p></div></div><div class="record-list"><article v-for="row in finance?.adjustments || []" :key="row.name"><div><strong>{{ row.adjustment_name }}</strong><small>{{ row.adjustment_type }} · {{ row.scope_type }} · {{ row.calculation_basis }}</small><small>{{ row.effective_from }}{{ row.effective_to ? ` to ${row.effective_to}` : '' }}</small></div><div><b>{{ money(row.value) }}</b><SystemBadge :theme="row.enabled ? 'green' : undefined">{{ row.enabled ? 'Active' : 'Disabled' }}</SystemBadge><SystemOperationalButton variant="outline" @click="editAdjustment(row)">Edit</SystemOperationalButton></div></article><p v-if="!finance?.adjustments?.length" class="empty-state">No discount or buying-cost rules have been set.</p></div></section>
      </SystemTabsContent>

      <SystemTabsContent value="history" class="finance-tabs__content">
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Cost evidence</p><h2>Recent cost invoices</h2><p>Each row shows the reviewed document and whether it created actual cost entries.</p></div></div><div class="history-list"><article v-for="row in snapshot?.recent_cost_invoices || []" :key="row.name"><div><strong>{{ row.payee }}</strong><small>{{ row.invoice_date }} · {{ row.invoice_number || row.name }}</small><small>{{ row.line_count || 0 }} cost lines · {{ row.cost_categories || 'Uncategorised' }}</small></div><div><b>{{ money(row.total_amount) }}</b><SystemBadge :theme="row.costs_posted ? 'green' : undefined">{{ row.costs_posted ? `${row.posted_entry_count || row.line_count || 0} actual costs created` : row.status }}</SystemBadge></div></article><p v-if="!snapshot?.recent_cost_invoices?.length" class="empty-state">No cost invoices have been recorded.</p></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Actual-cost ledger</p><h2>What was added</h2><p>Posted invoice lines and direct miscellaneous costs appear together.</p></div><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'export')">See result in Reports</SystemOperationalButton></div><div class="history-list"><article v-for="row in finance?.actual_costs || []" :key="row.name"><div><strong>{{ row.payee || row.cost_category }}</strong><small>{{ row.cost_date }} · {{ row.cost_category }} · {{ row.name }}</small><small>{{ row.cost_rule ? `Matched to ${row.cost_rule}` : 'No expected-cost match' }}{{ row.evidence_file ? ' · Evidence attached' : '' }}</small></div><div><b>{{ money(row.amount) }}</b><SystemBadge>{{ quantity(row.quantity) }} × {{ money(row.unit_rate) }}</SystemBadge></div></article><p v-if="!finance?.actual_costs?.length" class="empty-state">No actual operating costs have been added.</p></div></section>
      </SystemTabsContent>
    </SystemTabs>
  </section>
</template>

<style scoped>
.finance-workforce{display:grid;gap:var(--spacing-s);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface)}
.field-choice-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-2xs) var(--spacing-m)}.field-choice-grid label,.check-field{display:flex;align-items:center;gap:var(--spacing-xs);min-height:2.75rem}.mapping-list,.review-list,.history-list,.record-list,.category-list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.mapping-list article,.review-list article,.history-list article,.record-list article,.category-list article{display:grid;grid-template-columns:minmax(0,1fr) minmax(12rem,auto);align-items:center;gap:var(--spacing-s);padding:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.mapping-list article:last-child,.review-list article:last-child,.history-list article:last-child,.record-list article:last-child,.category-list article:last-child{border-bottom:0}.mapping-list small,.review-list small,.history-list small,.record-list small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.review-list article{grid-template-columns:minmax(0,1fr) auto}.review-list p{grid-column:1/-1;margin:0;color:var(--theme-text-muted)}.finance-tabs{display:grid;gap:var(--spacing-m)}.finance-tabs__list{justify-content:flex-start!important;width:fit-content;max-width:100%;overflow-x:auto}.finance-tabs__list :deep([role="tab"]){min-height:2.75rem}.finance-tabs__content{display:grid;gap:var(--spacing-m);outline:none}.finance-overview{display:grid;gap:var(--spacing-m);padding:var(--spacing-l);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface-raised)}.finance-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.finance-metrics article{display:grid;align-content:start;gap:var(--spacing-2xs);min-width:0;padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-secondary)}.finance-metrics span,.finance-metrics small{color:var(--theme-text-muted)}.finance-metrics strong{font-size:var(--font-size-2);line-height:1.15;overflow-wrap:anywhere}.category-list article{grid-template-columns:minmax(10rem,1fr) repeat(2,minmax(9rem,.7fr)) auto}.record-list article>div:last-child,.history-list article>div:last-child{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:var(--spacing-xs)}.calculated-field{display:grid;align-content:center;gap:var(--spacing-3xs);min-height:4.75rem;padding:var(--spacing-xs) var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-secondary)}.calculated-field span,.calculated-field small{color:var(--theme-text-muted)}.calculated-field strong{font-size:var(--font-size-1)}.check-row{display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-s) var(--spacing-l)}.cost-line-list{display:grid;gap:var(--spacing-s)}.cost-line-list article{display:grid;grid-template-columns:1.5fr 1fr 1fr repeat(3,minmax(8rem,.6fr));gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.cost-line-review{grid-column:1/-1;display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-3xs) var(--spacing-xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.cost-line-review p{margin:0}.cost-line-review strong{color:var(--theme-text)}.extraction-summary{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-s)}.extraction-summary p{margin:.25rem 0 0}.invoice-ocr{max-height:20rem;margin:var(--spacing-s) 0 0;padding:var(--spacing-s);overflow:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-field);color:var(--theme-text);font-family:var(--font-family-c);font-size:var(--font-size--2);line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.price-table-wrap{max-width:100%;overflow-x:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card)}.price-table{width:100%;min-width:72rem;border-collapse:collapse;background:var(--theme-surface-raised)}.price-table th,.price-table td{padding:var(--spacing-xs) var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);text-align:left;vertical-align:top}.price-table th{background:var(--theme-secondary);color:var(--theme-text-muted);white-space:nowrap}.empty-state{margin:0;padding:var(--spacing-l);color:var(--theme-text-muted);text-align:center}.field-grid--wide{grid-template-columns:repeat(4,minmax(0,1fr))}
@media(max-width:1100px){.finance-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.cost-line-list article,.field-grid--wide{grid-template-columns:repeat(2,minmax(0,1fr))}.category-list article{grid-template-columns:minmax(9rem,1fr) repeat(2,minmax(8rem,.7fr))}.category-list article>*:last-child{grid-column:1/-1;width:fit-content}}
@media(max-width:700px){.field-choice-grid,.finance-metrics,.cost-line-list article,.field-grid--wide{grid-template-columns:1fr}.mapping-list article,.history-list article,.record-list article,.category-list article{grid-template-columns:1fr}.record-list article>div:last-child,.history-list article>div:last-child{justify-content:flex-start}.finance-overview{padding:var(--spacing-m)}.extraction-summary{align-items:stretch;flex-direction:column}.category-list article>*:last-child{grid-column:auto}}
</style>
