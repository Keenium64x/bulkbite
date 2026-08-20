<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemFileUploader, SystemFormControl, SystemOperationalButton, SystemSelect } from "@/desyium"
import { createReceiptIntake, receiveStockFromReceipt } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const busy = ref(false)
const error = ref("")
const saved = ref(null)
const form = reactive({ receipt_file: "", supplier: "", supplier_invoice_number: "", invoice_date: new Date().toISOString().slice(0, 10), default_location: "Ingredients", currency: "ZAR", tax_amount: 0, review_notes: "" })
const lines = reactive([{ item_code: "", qty: 0, rate: 0, location: "Ingredients" }])
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const locationOptions = computed(() => (props.snapshot?.options?.locations || []).map(value => ({ label: value, value })))
const total = computed(() => lines.reduce((sum, line) => sum + Number(line.qty || 0) * Number(line.rate || 0), 0) + Number(form.tax_amount || 0))

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
    <header class="workflow-header"><div><p class="eyebrow">PURCHASE EVIDENCE</p><h1>RECEIVE<br />WHAT ARRIVED.</h1><p>Upload the receipt, check every line, save the review, then add the quantities to stock.</p></div><div class="step-rail"><span class="is-current">1 Upload</span><span>2 Review</span><span>3 Receive</span></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">SOURCE</p><h2>PRIVATE RECEIPT</h2></div><SystemBadge v-if="form.receipt_file">UPLOADED</SystemBadge></div>
      <SystemFileUploader :upload-args="{ private: true }" @success="onUpload">
        <template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading" @click="upload.openFileSelector">{{ form.receipt_file ? "Replace receipt" : "Upload receipt" }}</SystemOperationalButton></template>
      </SystemFileUploader>
      <p class="field-note">{{ form.receipt_file || "The source file stays private and attached to the receipt record." }}</p>
    </section>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">REVIEW</p><h2>SUPPLIER AND TOTALS</h2></div></div>
      <div class="field-grid">
        <label class="field-shell"><span>Supplier</span><SystemSelect v-model="form.supplier" :options="supplierOptions" placeholder="Choose supplier" size="lg" /></label>
        <SystemFormControl v-model="form.supplier_invoice_number" label="Invoice number" size="lg" />
        <SystemFormControl v-model="form.invoice_date" type="date" label="Invoice date" size="lg" />
        <label class="field-shell"><span>Stock location</span><SystemSelect v-model="form.default_location" :options="locationOptions" size="lg" /></label>
      </div>
      <div class="line-list">
        <article v-for="(line, index) in lines" :key="index" class="entry-row">
          <span class="row-number">{{ String(index + 1).padStart(2, "0") }}</span>
          <label class="field-shell"><span>Item</span><SystemSelect v-model="line.item_code" :options="itemOptions" placeholder="Choose ingredient" size="lg" /></label>
          <SystemFormControl v-model="line.qty" type="number" label="Quantity" min="0" step="0.001" size="lg" />
          <SystemFormControl v-model="line.rate" type="number" label="Rate (R)" min="0" step="0.01" size="lg" />
          <strong class="line-total">R {{ (Number(line.qty || 0) * Number(line.rate || 0)).toFixed(2) }}</strong>
        </article>
      </div>
      <SystemOperationalButton variant="outline" @click="addLine">Add receipt line</SystemOperationalButton>
      <div class="receipt-total"><span>REVIEWED TOTAL</span><strong>R {{ total.toFixed(2) }}</strong></div>
    </section>
    <footer class="posting-bar">
      <div><SystemBadge>{{ saved ? "DRAFT SAVED" : "NOT SAVED" }}</SystemBadge><p>Saving retains evidence. Receiving is the action that changes stock.</p></div>
      <SystemOperationalButton v-if="!saved" theme="blue" variant="solid" size="lg" :loading="busy" @click="saveDraft">Save reviewed receipt</SystemOperationalButton>
      <SystemOperationalButton v-else theme="blue" variant="solid" size="lg" :loading="busy" @click="receiveStock">Receive stock now</SystemOperationalButton>
    </footer>
  </section>
</template>
