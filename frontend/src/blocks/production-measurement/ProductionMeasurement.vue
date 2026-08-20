<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemFormControl, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { createRunFromPlan, submitProductionRun, updateProductionActuals } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const selectedRowName = ref("")
const productionDate = ref(new Date().toISOString().slice(0, 10))
const actualOutput = ref(0)
const notes = ref("")
const measurements = reactive([])
const run = ref(null)
const busy = ref(false)
const error = ref("")
const selectedRow = computed(() => props.plan?.rows?.find(row => row.name === selectedRowName.value))
const planOptions = computed(() => (props.plan?.rows || []).map(row => ({ label: `Week ${row.week_number}: ${row.finished_item_name} (${row.planned_output_qty})`, value: row.name })))

watch(selectedRow, row => {
  measurements.splice(0)
  if (!row) return
  actualOutput.value = row.planned_output_qty
  row.ingredients.forEach(item => measurements.push({ ...item, measurement_method: "Used", actual_qty: item.expected_qty, remaining_qty: item.available_qty }))
})

async function saveRun() {
  busy.value = true; error.value = ""
  try {
    if (!run.value) run.value = await createRunFromPlan(props.plan.name, selectedRowName.value, productionDate.value, props.plan.location, "Finished Meals")
    run.value = await updateProductionActuals(run.value.name, actualOutput.value, measurements.map(item => ({ item_code: item.item_code, measurement_method: item.measurement_method, actual_qty: item.actual_qty, remaining_qty: item.remaining_qty })), notes.value)
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
async function postRun() {
  busy.value = true; error.value = ""
  try { run.value = await submitProductionRun(run.value.name); emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
</script>

<template>
  <section data-block="production-measurement" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Production</p><h1>Production measurement</h1><p>Choose the planned meal. For each ingredient, enter what was used or what was left. The system calculates the difference.</p></div><div class="step-rail"><span class="is-current">1 Plan</span><span>2 Measure</span><span>3 Post</span></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="field-grid">
        <label class="field-shell field-shell--wide"><span>Planned meal</span><SystemSelect v-model="selectedRowName" :options="planOptions" placeholder="Choose one plan row" size="lg" /></label>
        <SystemFormControl v-model="productionDate" type="date" label="Production date" size="lg" />
        <SystemFormControl v-model="actualOutput" type="number" label="Meals made" min="0" step="1" size="lg" />
      </div>
    </section>
    <section v-if="selectedRow" class="data-section">
      <div class="section-heading"><div><p class="eyebrow">Recipe expectation</p><h2>{{ selectedRow.finished_item_name }}</h2></div><SystemBadge>Week {{ selectedRow.week_number }}</SystemBadge></div>
      <div class="measurement-list">
        <article v-for="item in measurements" :key="item.item_code" class="measurement-row">
          <div><strong>{{ item.item_name }}</strong><small>Expected {{ Number(item.expected_qty).toFixed(3) }} {{ item.uom }} · Available {{ Number(item.available_qty).toFixed(3) }}</small></div>
          <label class="field-shell"><span>Enter</span><SystemSelect v-model="item.measurement_method" :options="[{ label: 'Quantity used', value: 'Used' }, { label: 'Quantity left', value: 'Remaining' }]" size="lg" /></label>
          <SystemFormControl v-if="item.measurement_method === 'Used'" v-model="item.actual_qty" type="number" label="Used" min="0" step="0.001" size="lg" />
          <SystemFormControl v-else v-model="item.remaining_qty" type="number" label="Left" min="0" step="0.001" size="lg" />
          <span class="unit-label">{{ item.uom }}</span>
        </article>
      </div>
      <SystemTextarea v-model="notes" placeholder="Production notes or reason for a large difference" :rows="3" />
    </section>
    <footer class="posting-bar">
      <div><SystemBadge>{{ run ? (run.docstatus ? "POSTED" : "DRAFT SAVED") : "NOT SAVED" }}</SystemBadge><p>The draft keeps measurements. Posting changes ingredient and finished-meal stock.</p></div>
      <SystemOperationalButton v-if="!run || !run.docstatus" variant="outline" size="lg" :loading="busy" :disabled="!selectedRow" @click="saveRun">Save measurements</SystemOperationalButton>
      <SystemOperationalButton v-if="run && !run.docstatus" theme="blue" variant="solid" size="lg" :loading="busy" @click="postRun">Post production</SystemOperationalButton>
    </footer>
  </section>
</template>
