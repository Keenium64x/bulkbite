<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemDatePicker, SystemFormControl, SystemLink, SystemLinkedRecordField, SystemMultiFileUploader, SystemOperationalButton, SystemSelect } from "@/desyium"
import { createReceiptIntake, getReceiptExtractionStatus, receiveStockFromReceipt, startReceiptExtraction } from "@/resources/api"
import { useRouter } from "vue-router"

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const errors = reactive({})
const saved = ref(null)
const extraction = ref(null)
const extractionStatus = ref("")
const extractionStage = ref("")
const showOcr = ref(false)
const showReceipt = ref(false)
const receiptFiles = ref([])
const today = new Date()
const localToday = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`
const form = reactive({ receipt_file: "", supplier: "", supplier_invoice_number: "", invoice_date: localToday, default_location: "Ingredients", currency: "ZAR", tax_amount: 0, review_notes: "" })
const lines = reactive([newLine("Ingredients")])
const adjustments = reactive([])
watch(receiptFiles, (files) => { form.receipt_file = files[0]?.file_url || "" }, { deep: true })
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const locationOptions = computed(() => (props.snapshot?.options?.locations || []).map(value => ({ label: value, value })))
const purchaseUomOptions = [{ label: "grams", value: "g" }, { label: "kilograms", value: "Kg" }, { label: "millilitres", value: "ml" }, { label: "litres", value: "Litre" }, { label: "each", value: "Each" }]
const total = computed(() => lines.reduce((sum, line) => sum + Number(line.amount || 0), 0) + Number(form.tax_amount || 0) + adjustments.reduce((sum, row) => sum + (row.effect === "Saving" ? -1 : 1) * Number(row.amount || 0), 0))
const adjustmentTypes = [{ label: "Offer discount", value: "Offer Discount" }, { label: "Fixed discount", value: "Fixed Discount" }, { label: "Rebate", value: "Rebate" }, { label: "Free delivery", value: "Free Delivery" }, { label: "Delivery fee", value: "Delivery Fee" }, { label: "Service fee", value: "Service Fee" }, { label: "Other saving", value: "Other Saving" }, { label: "Other cost", value: "Other Cost" }]
function receiptFileType(fileUrl) {
  const pathname = String(fileUrl || "").split(/[?#]/, 1)[0].toLowerCase()
  const extension = pathname.includes(".") ? pathname.slice(pathname.lastIndexOf(".") + 1) : ""
  if (["avif", "bmp", "gif", "jpeg", "jpg", "png", "webp"].includes(extension)) return "image"
  if (extension === "pdf") return "pdf"
  return "file"
}
function openLinked(mode, doctype) { router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } }) }

function newLine(location) { return { item_code: "", purchase_qty: 1, units_per_pack: 1, unit_size: 1, purchase_uom: "Kg", qty: 1, uom: "Kg", amount: 0, rate: 0, price_per_pack: 0, price_per_unit: 0, location } }
function itemFor(line) { return props.inventory?.items?.find(item => item.item_code === line.item_code) }
function purchaseStockUom(purchaseUom) { return ({ g: "Kg", Kg: "Kg", ml: "Litre", Litre: "Litre", Each: "Each" })[purchaseUom] || "" }
function recomputeLine(line) {
  const aliases = { g: ["Kg", 0.001], Kg: ["Kg", 1], ml: ["Litre", 0.001], Litre: ["Litre", 1], Each: ["Each", 1] }
  const [uom, multiplier] = aliases[line.purchase_uom] || ["", 0]
  const packs = Number(line.purchase_qty || 0)
  const units = Number(line.units_per_pack || 0)
  const pricePerUnit = Number(line.price_per_unit || 0)
  line.qty = packs * units * Number(line.unit_size || 0) * multiplier
  line.uom = itemFor(line)?.stock_uom || uom
  line.amount = packs * units * pricePerUnit
  line.price_per_pack = units * pricePerUnit
  line.rate = line.qty ? Number(line.amount || 0) / line.qty : 0
  return line
}
function updateLine(line, field, value) { line[field] = value; recomputeLine(line) }
function formatQuantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }
function formatMoney(value) { return Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function visibleWarning(line) {
  const warning = String(line.warning || "").trim()
  return warning === "Confirm the item match, pack size, and line amount against the receipt." ? "" : warning
}
function addLine() { if (!saved.value) lines.push(newLine(form.default_location)) }
function addAdjustment() { if (!saved.value) adjustments.push({ adjustment_type: "Offer Discount", description: "", effect: "Saving", amount: 0, notes: "" }) }
function updateAdjustment(row, field, value) { row[field] = value; row.effect = ["Offer Discount", "Percentage Discount", "Fixed Discount", "Rebate", "Free Delivery", "Other Saving"].includes(row.adjustment_type) ? "Saving" : "Cost" }
function uploadedFileUrl(file) { return file?.file_url || file?.message?.file_url || file?.data?.file_url || "" }
async function onUpload(files) {
	const uploaded = (files || []).map(file => ({ file_url: uploadedFileUrl(file), file_name: file.file_name || "Receipt evidence" })).filter(file => file.file_url)
	if (!uploaded.length) { error.value = "The files uploaded, but their private addresses were missing. Try the upload again."; return }
	receiptFiles.value = uploaded
	form.receipt_file = uploaded[0].file_url
  showReceipt.value = false
  extraction.value = null
  extractionStatus.value = "queued"
  busy.value = true; error.value = ""
  try {
		const job = await startReceiptExtraction(uploaded.map(file => file.file_url))
    extraction.value = await waitForExtraction(job.job_id)
    applyExtraction(extraction.value)
    extractionStatus.value = "finished"
  } catch (exception) { extractionStatus.value = "failed"; error.value = exception.message } finally { busy.value = false }
}
async function waitForExtraction(jobId) {
  const deadline = Date.now() + 10 * 60 * 1000
  while (Date.now() < deadline) {
		const state = await getReceiptExtractionStatus(jobId)
		extractionStatus.value = state.status
		extractionStage.value = state.stage || state.status
    if (state.status === "finished") return state.result
    if (state.status === "failed") throw new Error(state.error || "Receipt extraction failed.")
    await new Promise(resolve => window.setTimeout(resolve, 1500))
  }
  throw new Error("Receipt extraction took too long. Try again or enter the receipt manually.")
}
const extractionProgressText = computed(() => ({ queued: "Receipt files are waiting for the background worker...", extracting_text: "Reading text from the private receipt files...", structuring: "Structuring supplier and purchase-line suggestions...", matching: "Matching suggested lines to BulkBite stock items...", finished: "Receipt suggestions are ready for review." }[extractionStage.value] || "Receipt files are processing..."))
function applyExtraction(result) {
  if (result.supplier) form.supplier = result.supplier
  if (result.supplier_invoice_number) form.supplier_invoice_number = result.supplier_invoice_number
  if (result.invoice_date) form.invoice_date = result.invoice_date
  if (result.currency) form.currency = result.currency
  if (result.tax_amount !== null && result.tax_amount !== undefined) form.tax_amount = Number(result.tax_amount)
  const extractedLines = (result.lines || []).map(line => ({
    item_code: line.item_code || "",
    supplier_description: line.proposed_item_name || line.source_quote || "",
    purchase_qty: Number(line.purchase_qty || 1),
    units_per_pack: Number(line.units_per_pack || 1),
    unit_size: Number(line.unit_size || line.qty || 1),
    purchase_uom: line.purchase_uom || line.uom || "Kg",
    qty: Number(line.qty || 0),
    rate: Number(line.rate || 0),
    price_per_pack: Number(line.price_per_pack || 0),
    price_per_unit: Number(line.price_per_unit || 0),
    amount: Number(line.amount || 0),
    location: form.default_location,
    source_quote: line.source_quote,
		warning: line.warning,
		notes: line.notes,
		confidence: Number(line.confidence || 0),
  }))
  lines.splice(0, lines.length, ...(extractedLines.length ? extractedLines.map(recomputeLine) : [newLine(form.default_location)]))
}
function validate() {
  Object.keys(errors).forEach((key) => delete errors[key])
  if (!form.receipt_file) errors.receipt_file = "Upload the private receipt."
  if (!form.supplier) errors.supplier = "Choose a supplier."
  if (!form.invoice_date) errors.invoice_date = "Choose the invoice date."
  if (!form.default_location) errors.default_location = "Choose a stock location."
  lines.forEach((line, index) => {
    if (!line.item_code) errors[`item_${index}`] = "Choose an item."
    recomputeLine(line)
    if (Number(line.purchase_qty) <= 0) errors[`purchase_qty_${index}`] = "Packs bought must be greater than zero."
    if (Number(line.units_per_pack) <= 0) errors[`units_per_pack_${index}`] = "Units per pack must be greater than zero."
    if (Number(line.unit_size) <= 0) errors[`unit_size_${index}`] = "Size per unit must be greater than zero."
    if (!line.purchase_uom) errors[`purchase_uom_${index}`] = "Choose the size unit."
    if (line.item_code && purchaseStockUom(line.purchase_uom) !== itemFor(line)?.stock_uom) errors[`purchase_uom_${index}`] = `This purchase size becomes ${purchaseStockUom(line.purchase_uom) || "an unknown unit"}, but this item is stocked in ${itemFor(line)?.stock_uom || "its configured unit"}.`
    if (Number(line.amount) < 0) errors[`amount_${index}`] = "Line total cannot be negative."
  })
  return !Object.keys(errors).length
}
async function saveDraft() {
  if (!validate()) { error.value = "Check the marked receipt fields."; return }
  busy.value = true; error.value = ""
  try {
    saved.value = await createReceiptIntake({ ...form, evidence_files: receiptFiles.value.slice(1).map(file => ({ evidence_file: file.file_url, file_name: file.file_name })), business_name: "BulkBite", subtotal_amount: lines.reduce((sum, line) => sum + Number(line.amount || 0), 0), total_amount: total.value, status: "Reviewed", items: lines.map(line => recomputeLine({ ...line })), adjustments })
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
async function receiveStock() {
  busy.value = true; error.value = ""
  try { saved.value = await receiveStockFromReceipt(saved.value.name); emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
</script>

<template>
  <section data-block="receipt-intake" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Receipts</p><h1>Add bought stock</h1><p>Keep the receipt, check what arrived, then add the reviewed quantities to stock.</p></div></header>
    <ol class="workflow-steps" aria-label="Receipt progress">
      <li :class="{ 'is-current': !form.receipt_file, 'is-complete': form.receipt_file }"><span>1</span><div><strong>Upload receipt</strong><small>Attach the private source document.</small></div></li>
      <li :class="{ 'is-current': form.receipt_file && !saved, 'is-complete': saved }"><span>2</span><div><strong>Check details</strong><small>Confirm the supplier, pack sizes, quantities, and prices.</small></div></li>
      <li :class="{ 'is-current': saved && !saved.docstatus, 'is-complete': saved?.docstatus }"><span>3</span><div><strong>Add to stock</strong><small>Post the reviewed quantities once.</small></div></li>
    </ol>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 1</p><h2>Upload the receipt</h2><p>Use the receipt as evidence for this stock entry.</p></div><SystemBadge v-if="form.receipt_file">Uploaded</SystemBadge></div>
			<SystemMultiFileUploader v-model="receiptFiles" :disabled="Boolean(saved)" :label="receiptFiles.length ? 'Replace or add receipt files' : 'Add receipt files'" @complete="onUpload" />
			<p class="field-note" aria-live="polite">{{ busy && form.receipt_file ? extractionProgressText : (receiptFiles.length ? `${receiptFiles.length} private receipt file${receiptFiles.length === 1 ? '' : 's'} ready.` : "Add all receipt images or PDF files in one selection. They stay private and attached to the receipt record.") }}</p>
			<div v-if="extraction" class="safety-note">
				<div class="extraction-summary"><div><strong>{{ extraction.parser_mode }}</strong><p>{{ extraction.lines.length }} purchase lines suggested at {{ Math.round(Number(extraction.confidence || 0) * 100) }}% document confidence. Check every match, quantity, and rate before saving.</p></div><SystemOperationalButton variant="outline" @click="showOcr = !showOcr">{{ showOcr ? "Hide OCR text" : "Show OCR text" }}</SystemOperationalButton></div>
				<p><strong>OCR:</strong> {{ extraction.ocr_provider || "Text extraction" }}</p>
				<p v-for="warning in extraction.warnings" :key="warning">{{ warning }}</p>
				<div v-if="showOcr" class="ocr-result"><strong>OCR extraction result</strong><pre>{{ extraction.ocr_text || "No text was extracted from this file." }}</pre></div>
			</div>
    </section>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 2</p><h2>Check what was bought</h2><p>Enter each ingredient exactly as it arrived.</p></div></div>
      <div v-if="form.receipt_file" class="receipt-evidence">
        <div class="receipt-evidence__heading">
          <div><strong>Receipt evidence</strong><p>Compare the original receipt with the suggested purchase lines.</p></div>
          <SystemOperationalButton variant="outline" :aria-expanded="showReceipt" aria-controls="receipt-evidence-preview" @click="showReceipt = !showReceipt">{{ showReceipt ? "Hide receipt" : "Show receipt" }}</SystemOperationalButton>
        </div>
        <div v-if="showReceipt" id="receipt-evidence-preview" class="receipt-evidence__preview">
					<article v-for="(file, index) in receiptFiles" :key="file.file_url" class="receipt-evidence__file">
						<strong>{{ file.file_name || `Receipt file ${index + 1}` }}</strong>
						<img v-if="receiptFileType(file.file_url) === 'image'" :src="file.file_url" :alt="`Uploaded receipt evidence ${index + 1}`" />
						<iframe v-else-if="receiptFileType(file.file_url) === 'pdf'" :src="file.file_url" :title="`Uploaded receipt evidence ${index + 1}`"></iframe>
						<div v-else class="receipt-evidence__fallback"><p>This file type cannot be previewed here.</p><SystemLink :href="file.file_url" external>Open receipt file</SystemLink></div>
					</article>
        </div>
      </div>
      <div class="field-grid">
        <SystemLinkedRecordField v-model="form.supplier" label="Supplier" :options="supplierOptions" :disabled="Boolean(saved)" :error="errors.supplier" placeholder="Choose supplier" create-label="Add supplier" manage-label="Manage suppliers" @create="openLinked('create', 'BulkBite Supplier')" @manage="openLinked('list', 'BulkBite Supplier')" />
        <SystemFormControl v-model="form.supplier_invoice_number" label="Invoice number" size="lg" :disabled="Boolean(saved)" />
        <SystemDatePicker v-model="form.invoice_date" label="Invoice date" format="YYYY-MM-DD" :disabled="Boolean(saved)" :clearable="false" />
        <SystemLinkedRecordField v-model="form.default_location" label="Stock location" :options="locationOptions" :disabled="Boolean(saved)" :error="errors.default_location" create-label="Add location" manage-label="Manage locations" @create="openLinked('create', 'BulkBite Location')" @manage="openLinked('list', 'BulkBite Location')" />
      </div>
      <div class="line-list">
        <article v-for="(line, index) in lines" :key="index" class="entry-row">
          <span class="row-number">{{ String(index + 1).padStart(2, "0") }}</span>
          <div class="purchase-fields">
            <SystemLinkedRecordField :model-value="line.item_code" label="Item" :options="itemOptions" :disabled="Boolean(saved)" :error="errors[`item_${index}`]" placeholder="Choose ingredient" create-label="Add item" manage-label="Manage items" @update:model-value="updateLine(line, 'item_code', $event)" @create="openLinked('create', 'BulkBite Item')" @manage="openLinked('list', 'BulkBite Item')" />
            <SystemFormControl :model-value="line.purchase_qty" type="number" label="Packs bought" min="1" step="1" size="lg" :disabled="Boolean(saved)" :error="errors[`purchase_qty_${index}`]" @update:model-value="updateLine(line, 'purchase_qty', $event)" />
            <SystemFormControl :model-value="line.units_per_pack" type="number" label="Units per pack" min="1" step="1" size="lg" :disabled="Boolean(saved)" :error="errors[`units_per_pack_${index}`]" @update:model-value="updateLine(line, 'units_per_pack', $event)" />
            <SystemFormControl :model-value="line.unit_size" type="number" label="Size per unit" min="0.1" step="0.1" size="lg" :disabled="Boolean(saved)" :error="errors[`unit_size_${index}`]" @update:model-value="updateLine(line, 'unit_size', $event)" />
            <label class="field-shell">
              <span>Size unit</span>
              <SystemSelect :model-value="line.purchase_uom" :options="purchaseUomOptions" size="lg" :disabled="Boolean(saved)" @update:model-value="updateLine(line, 'purchase_uom', $event)" />
              <small v-if="errors[`purchase_uom_${index}`]" class="field-error">{{ errors[`purchase_uom_${index}`] }}</small>
            </label>
            <SystemFormControl :model-value="line.price_per_unit" type="number" label="Unit price (R)" min="0" step="0.01" size="lg" :disabled="Boolean(saved)" :error="errors[`amount_${index}`]" @update:model-value="updateLine(line, 'price_per_unit', $event)" />
          </div>
          <dl class="purchase-summary" aria-label="Calculated purchase values">
            <div><dt>Purchase format</dt><dd>{{ formatQuantity(line.purchase_qty) }} pack(s) × {{ formatQuantity(line.units_per_pack) }} unit(s) × {{ formatQuantity(line.unit_size) }} {{ line.purchase_uom }}</dd></div>
            <div><dt>Stock received</dt><dd>{{ formatQuantity(line.qty) }} {{ line.uom }}</dd></div>
            <div><dt>Price per pack</dt><dd>R {{ formatMoney(line.price_per_pack) }}</dd></div>
            <div><dt>Line total</dt><dd>R {{ formatMoney(line.amount) }}</dd></div>
            <div><dt>Price per {{ line.uom || "stock unit" }}</dt><dd>R {{ formatMoney(line.rate) }}</dd></div>
          </dl>
					<div v-if="line.source_quote || visibleWarning(line) || line.notes || line.confidence" class="line-review"><SystemBadge :theme="line.confidence >= 85 ? 'green' : line.confidence >= 60 ? 'orange' : 'red'">{{ Math.round(line.confidence || 0) }}% confidence</SystemBadge><p v-if="line.source_quote"><strong>OCR source:</strong> {{ line.source_quote }}</p><p v-if="line.notes"><strong>Parser note:</strong> {{ line.notes }}</p><p v-if="visibleWarning(line)"><strong>Check:</strong> {{ visibleWarning(line) }}</p></div>
        </article>
      </div>
      <SystemOperationalButton v-if="!saved" class="receipt-add-line" variant="outline" @click="addLine">Add receipt line</SystemOperationalButton>
      <div class="section-heading receipt-adjustment-heading"><div><p class="eyebrow">Actual savings and buying costs</p><h3>What changed the receipt total?</h3><p>Record discounts, rebates, free delivery, delivery charges, and other buying adjustments exactly as the receipt proves them.</p></div></div>
      <div v-if="adjustments.length" class="adjustment-list">
        <article v-for="(row, index) in adjustments" :key="index">
          <label class="field-shell"><span>Type</span><SystemSelect :model-value="row.adjustment_type" :options="adjustmentTypes" size="lg" :disabled="Boolean(saved)" @update:model-value="updateAdjustment(row, 'adjustment_type', $event)" /></label>
          <SystemFormControl v-model="row.description" label="Receipt description" size="lg" :disabled="Boolean(saved)" />
          <SystemFormControl v-model="row.amount" type="number" label="Amount (R)" min="0" step="0.01" size="lg" :disabled="Boolean(saved)" />
          <SystemBadge :theme="row.effect === 'Saving' ? 'green' : undefined">{{ row.effect }}</SystemBadge>
          <SystemOperationalButton v-if="!saved" variant="ghost" @click="adjustments.splice(index, 1)">Remove</SystemOperationalButton>
        </article>
      </div>
      <SystemOperationalButton v-if="!saved" class="receipt-add-line" variant="outline" @click="addAdjustment">Add discount or cost</SystemOperationalButton>
      <div class="receipt-total"><span>Reviewed total</span><strong>R {{ total.toFixed(2) }}</strong></div>
    </section>
    <footer class="posting-bar">
      <div><SystemBadge>{{ saved ? (saved.docstatus ? "STOCK ADDED" : "READY TO ADD") : "REVIEW NOT SAVED" }}</SystemBadge><p>{{ saved ? (saved.docstatus ? "The reviewed quantities are now in stock." : "Review the saved receipt once more, then add it to stock.") : "Save the review first. Stock will not change yet." }}</p></div>
      <SystemOperationalButton v-if="!saved" variant="solid" size="lg" :loading="busy" @click="saveDraft">Save reviewed receipt</SystemOperationalButton>
      <SystemOperationalButton v-else-if="!saved.docstatus" variant="solid" size="lg" :loading="busy" @click="receiveStock">Add reviewed stock</SystemOperationalButton>
    </footer>
		<section class="data-section receipt-history">
			<div class="section-heading"><div><p class="eyebrow">Receipt history</p><h2>What previous receipts changed</h2><p>Each record shows the reviewed spend and whether it was added to stock.</p></div><SystemOperationalButton variant="outline" @click="openLinked('list', 'BulkBite Receipt Intake')">Open all receipts</SystemOperationalButton></div>
			<div class="receipt-history__list">
				<article v-for="row in snapshot?.recent_receipts || []" :key="row.name">
					<div><strong>{{ row.supplier }}</strong><small>{{ row.invoice_date }} · {{ row.supplier_invoice_number || row.name }}</small></div>
					<dl><div><dt>Items</dt><dd>{{ row.item_count || 0 }}</dd></div><div><dt>Stock added</dt><dd>{{ row.stock_events_posted ? (row.stock_quantity_summary || 'Posted') : 'Not posted' }}</dd></div><div><dt>Spend</dt><dd>R {{ formatMoney(row.total_amount) }}</dd></div></dl>
					<SystemBadge :theme="row.stock_events_posted ? 'green' : undefined">{{ row.stock_events_posted ? 'Stock added' : 'Review saved' }}</SystemBadge>
				</article>
				<p v-if="!snapshot?.recent_receipts?.length" class="empty-state">No receipts have been recorded.</p>
			</div>
		</section>
  </section>
</template>

<style scoped>
.receipt-adjustment-heading{margin-top:var(--spacing-m)}.receipt-adjustment-heading h3{margin:0}.adjustment-list{display:grid;gap:var(--spacing-xs)}.adjustment-list article{display:grid;grid-template-columns:minmax(11rem,1fr) minmax(12rem,2fr) minmax(8rem,1fr) auto auto;align-items:end;gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.adjustment-list .system-badge{align-self:center}@media(max-width:64rem){.adjustment-list article{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:44rem){.adjustment-list article{grid-template-columns:1fr}}
.extraction-summary{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-s)}.extraction-summary p{margin:.25rem 0 0}.receipt-evidence{display:grid;gap:var(--spacing-s);min-width:0;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.receipt-evidence__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-s)}.receipt-evidence__heading p,.receipt-evidence__fallback p{margin:.25rem 0 0;color:var(--theme-text-muted)}.receipt-evidence__preview{display:grid;gap:var(--spacing-s);min-width:0;max-width:100%;padding:var(--spacing-s);overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-field)}.receipt-evidence__file{display:grid;gap:var(--spacing-xs);min-width:0}.receipt-evidence__preview img{display:block;width:auto;max-width:100%;height:auto;max-height:60rem;object-fit:contain}.receipt-evidence__preview iframe{display:block;width:100%;height:min(70vh,52rem);min-height:32rem;border:0}.receipt-evidence__fallback{justify-self:stretch;padding:var(--spacing-m);text-align:center}.ocr-result{display:grid;gap:var(--spacing-3xs);margin-top:var(--spacing-s)}.ocr-result pre{max-height:22rem;margin:0;padding:var(--spacing-s);overflow:auto;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-field);color:var(--theme-text);font-family:var(--font-family-c);font-size:var(--font-size--2);line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}.entry-row{grid-template-columns:auto minmax(0,1fr);align-items:start}.purchase-fields{display:grid;grid-template-columns:minmax(12rem,1.5fr) repeat(5,minmax(7rem,1fr));gap:var(--spacing-xs);min-width:0}.purchase-fields>.field-shell{padding-top:.375rem}.purchase-summary{grid-column:2/-1;display:grid;grid-template-columns:repeat(5,minmax(8rem,1fr));gap:var(--spacing-3xs);margin:0;padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface)}.purchase-summary div{min-width:0}.purchase-summary dt{color:var(--theme-text-muted);font-size:var(--font-size--2)}.purchase-summary dd{margin:.15rem 0 0;color:var(--theme-text);font-size:var(--font-size--1);font-weight:var(--font-weight-600);overflow-wrap:anywhere}.field-error{color:var(--theme-error);font-size:var(--font-size--2);font-weight:var(--font-weight-500)}.line-review{grid-column:2/-1;display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-3xs) var(--spacing-xs);padding-top:var(--spacing-3xs);color:var(--theme-text-muted);font-size:var(--font-size--2)}.line-review p{margin:0}.line-review strong{color:var(--theme-text)}.receipt-history__list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.receipt-history__list>article{display:grid;grid-template-columns:minmax(12rem,1fr) minmax(20rem,2fr) auto;align-items:center;gap:var(--spacing-s);padding:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.receipt-history__list>article:last-of-type{border-bottom:0}.receipt-history__list small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.receipt-history__list dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-xs);margin:0}.receipt-history__list dt{color:var(--theme-text-muted);font-size:var(--font-size--2)}.receipt-history__list dd{margin:.125rem 0 0;font-weight:var(--font-weight-600)}.empty-state{margin:0;padding:var(--spacing-l);color:var(--theme-text-muted);text-align:center}@media(max-width:86rem){.purchase-fields{grid-template-columns:repeat(3,minmax(8rem,1fr))}.purchase-fields>:first-child{grid-column:span 3}.purchase-summary{grid-template-columns:repeat(3,minmax(8rem,1fr))}.receipt-history__list>article{grid-template-columns:1fr auto}.receipt-history__list dl{grid-column:1/-1}}@media(max-width:44rem){.extraction-summary,.receipt-evidence__heading{align-items:stretch;flex-direction:column}.extraction-summary button,.receipt-evidence__heading button{width:100%}.receipt-evidence__preview iframe{height:65vh;min-height:24rem}.entry-row{grid-template-columns:1fr}.purchase-fields,.purchase-summary{grid-column:auto;grid-template-columns:1fr}.purchase-fields>:first-child{grid-column:auto}.purchase-summary{padding:var(--spacing-s)}.line-review{grid-column:auto}.receipt-history__list>article,.receipt-history__list dl{grid-template-columns:1fr}.receipt-history__list>article>.system-badge{justify-self:start}}
</style>
