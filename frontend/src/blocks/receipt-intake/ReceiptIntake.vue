<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemFileUploader, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton } from "@/desyium"
import { createReceiptIntake, receiveStockFromReceipt } from "@/resources/api"
import { useRouter } from "vue-router"

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const saved = ref(null)
const form = reactive({ receipt_file: "", supplier: "", supplier_invoice_number: "", invoice_date: new Date().toISOString().slice(0, 10), default_location: "Ingredients", currency: "ZAR", tax_amount: 0, review_notes: "" })
const lines = reactive([{ item_code: "", qty: 0, rate: 0, location: "Ingredients" }])
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const locationOptions = computed(() => (props.snapshot?.options?.locations || []).map(value => ({ label: value, value })))
const total = computed(() => lines.reduce((sum, line) => sum + Number(line.qty || 0) * Number(line.rate || 0), 0) + Number(form.tax_amount || 0))
function openLinked(mode, doctype) { router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } }) }

function addLine() { lines.push({ item_code: "", qty: 0, rate: 0, location: form.default_location }) }
function onUpload(file) { form.receipt_file = file.file_url }
async function saveDraft() {
  busy.value = true; error.value = ""
  try {
    saved.value = await createReceiptIntake({ ...form, business_name: "BulkBite", subtotal_amount: total.value - Number(form.tax_amount || 0), total_amount: total.value, status: "Reviewed", items: lines.map(line => ({ ...line, uom: props.inventory?.items?.find(item => item.item_code === line.item_code)?.stock_uom, amount: Number(line.qty) * Number(line.rate) })) })
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
      <li :class="{ 'is-current': form.receipt_file && !saved, 'is-complete': saved }"><span>2</span><div><strong>Check details</strong><small>Confirm the supplier, items, quantities, and rates.</small></div></li>
      <li :class="{ 'is-current': saved && !saved.docstatus, 'is-complete': saved?.docstatus }"><span>3</span><div><strong>Add to stock</strong><small>Post the reviewed quantities once.</small></div></li>
    </ol>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 1</p><h2>Upload the receipt</h2><p>Use the receipt as evidence for this stock entry.</p></div><SystemBadge v-if="form.receipt_file">Uploaded</SystemBadge></div>
      <SystemFileUploader :upload-args="{ private: true }" @success="onUpload">
        <template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading" @click="upload.openFileSelector">{{ form.receipt_file ? "Replace receipt" : "Upload receipt" }}</SystemOperationalButton></template>
      </SystemFileUploader>
      <p class="field-note">{{ form.receipt_file || "The source file stays private and attached to the receipt record." }}</p>
    </section>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 2</p><h2>Check what was bought</h2><p>Enter each ingredient exactly as it arrived.</p></div></div>
      <div class="field-grid">
        <SystemLinkedRecordField v-model="form.supplier" label="Supplier" :options="supplierOptions" placeholder="Choose supplier" create-label="Add supplier" manage-label="Manage suppliers" @create="openLinked('create', 'BulkBite Supplier')" @manage="openLinked('list', 'BulkBite Supplier')" />
        <SystemFormControl v-model="form.supplier_invoice_number" label="Invoice number" size="lg" />
        <SystemFormControl v-model="form.invoice_date" type="date" label="Invoice date" size="lg" />
        <SystemLinkedRecordField v-model="form.default_location" label="Stock location" :options="locationOptions" create-label="Add location" manage-label="Manage locations" @create="openLinked('create', 'BulkBite Location')" @manage="openLinked('list', 'BulkBite Location')" />
      </div>
      <div class="line-list">
        <article v-for="(line, index) in lines" :key="index" class="entry-row">
          <span class="row-number">{{ String(index + 1).padStart(2, "0") }}</span>
          <SystemLinkedRecordField v-model="line.item_code" label="Item" :options="itemOptions" placeholder="Choose ingredient" create-label="Add item" manage-label="Manage items" @create="openLinked('create', 'BulkBite Item')" @manage="openLinked('list', 'BulkBite Item')" />
          <SystemFormControl v-model="line.qty" type="number" label="Quantity" min="0" step="0.001" size="lg" />
          <SystemFormControl v-model="line.rate" type="number" label="Rate (R)" min="0" step="0.01" size="lg" />
          <strong class="line-total">R {{ (Number(line.qty || 0) * Number(line.rate || 0)).toFixed(2) }}</strong>
        </article>
      </div>
      <SystemOperationalButton variant="outline" @click="addLine">Add receipt line</SystemOperationalButton>
      <div class="receipt-total"><span>Reviewed total</span><strong>R {{ total.toFixed(2) }}</strong></div>
    </section>
    <footer class="posting-bar">
      <div><SystemBadge>{{ saved ? (saved.docstatus ? "STOCK ADDED" : "READY TO ADD") : "REVIEW NOT SAVED" }}</SystemBadge><p>{{ saved ? (saved.docstatus ? "The reviewed quantities are now in stock." : "Review the saved receipt once more, then add it to stock.") : "Save the review first. Stock will not change yet." }}</p></div>
      <SystemOperationalButton v-if="!saved" theme="blue" variant="solid" size="lg" :loading="busy" @click="saveDraft">Save reviewed receipt</SystemOperationalButton>
      <SystemOperationalButton v-else-if="!saved.docstatus" theme="blue" variant="solid" size="lg" :loading="busy" @click="receiveStock">Add reviewed stock</SystemOperationalButton>
    </footer>
  </section>
</template>
