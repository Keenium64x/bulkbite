<script setup>
import { reactive, ref } from "vue"
import { SystemBadge, SystemFormControl, SystemOperationalButton, SystemSelect } from "@/desyium"
import { accountantExportUrl, getAccountantExport } from "@/resources/api"

const today = new Date()
const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10)
const form = reactive({ from_date: firstDay, to_date: today.toISOString().slice(0, 10), dataset: "receipts" })
const preview = ref(null)
const busy = ref(false)
const error = ref("")
const datasets = [{ label: "Receipts", value: "receipts" }, { label: "Stock events", value: "stock_events" }, { label: "Closing stock", value: "closing_stock" }]
async function loadPreview() { busy.value = true; error.value = ""; try { preview.value = await getAccountantExport(form.from_date, form.to_date) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
function download() { window.location.assign(accountantExportUrl(form.from_date, form.to_date, form.dataset)) }
</script>

<template>
  <section data-block="accountant-export" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Export</p><h1>Prepare records for the accountant</h1><p>Choose the period, preview what is included, then download a CSV. Nothing here changes stock.</p></div><SystemBadge>Read only</SystemBadge></header>
    <ol class="workflow-steps" aria-label="Export progress">
      <li :class="{ 'is-current': !preview, 'is-complete': preview }"><span>1</span><div><strong>Choose records</strong><small>Select the period and dataset.</small></div></li>
      <li :class="{ 'is-complete': preview }"><span>2</span><div><strong>Check preview</strong><small>Confirm the record counts and note.</small></div></li>
      <li :class="{ 'is-current': preview }"><span>3</span><div><strong>Download CSV</strong><small>Send the selected records to the accountant.</small></div></li>
    </ol>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Step 1</p><h2>Choose what to export</h2><p>The preview covers the whole period. The CSV contains the selected dataset.</p></div></div>
      <div class="field-grid"><SystemFormControl v-model="form.from_date" type="date" label="From date" size="lg" /><SystemFormControl v-model="form.to_date" type="date" label="To date" size="lg" /><label class="field-shell"><span>Dataset</span><SystemSelect v-model="form.dataset" :options="datasets" size="lg" /></label></div>
      <div class="button-row"><SystemOperationalButton variant="outline" size="lg" :loading="busy" @click="loadPreview">Preview period</SystemOperationalButton><SystemOperationalButton theme="blue" variant="solid" size="lg" :disabled="!preview" @click="download">Download CSV</SystemOperationalButton></div>
    </section>
    <section v-if="preview" class="data-section"><div class="section-heading"><div><p class="eyebrow">{{ preview.period.from_date }} to {{ preview.period.to_date }}</p><h2>Export contents</h2></div></div><div class="metric-board metric-board--paper"><div><strong>{{ preview.receipts.length }}</strong><span>receipts</span></div><div><strong>{{ preview.stock_events.length }}</strong><span>stock events</span></div><div><strong>{{ preview.closing_stock.length }}</strong><span>closing balances</span></div></div><p class="safety-note">{{ preview.note }}</p></section>
  </section>
</template>
