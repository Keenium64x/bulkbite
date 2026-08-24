<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemDatePicker, SystemFormControl, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { createRunFromPlan, submitProductionRun, updateProductionActuals } from "@/resources/api"

// =============================================================================
// region PLANNED PRODUCTION STATION
// =============================================================================

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const localToday = () => { const value = new Date(); return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}` }
const productionDate = ref(localToday())
const actualOutput = ref(0)
const notes = ref("")
const measurements = reactive([])
const run = ref(null)
const busy = ref(false)
const error = ref("")
const dirtySinceSave = ref(false)
const station = computed(() => props.plan?.next_production || { state: "complete", row: null, run: null })
const selectedRow = computed(() => station.value.row)

watch(() => props.plan?.next_production, hydrateStation, { immediate: true, deep: true })
watch([actualOutput, notes, () => measurements.map(item => [item.measurement_method, item.actual_qty, item.remaining_qty])], () => {
  if (run.value) dirtySinceSave.value = true
}, { deep: true })

function hydrateStation(value) {
  const row = value?.row
  run.value = value?.run || null
  measurements.splice(0)
  if (!row) return
  productionDate.value = run.value?.production_date || row.planned_date || localToday()
  actualOutput.value = Number(run.value?.actual_output_qty ?? row.planned_output_qty)
  notes.value = run.value?.notes || ""
  const runIngredients = new Map((run.value?.ingredients || []).map(item => [item.item_code, item]))
  row.ingredients.forEach(item => {
    const saved = runIngredients.get(item.item_code)
    measurements.push({ ...item, measurement_method: saved?.measurement_method || "Used", actual_qty: Number(saved?.actual_qty ?? item.expected_qty), remaining_qty: Number(saved?.remaining_qty ?? item.available_qty) })
  })
  dirtySinceSave.value = false
}

async function saveRun() {
  busy.value = true
  error.value = ""
  try {
    if (!selectedRow.value) throw new Error("There is no planned production week ready.")
    if (!productionDate.value) throw new Error("Choose the production date.")
    if (Number(actualOutput.value) <= 0) throw new Error("Food made must be greater than zero.")
    if (measurements.some(item => Number(item.measurement_method === "Remaining" ? item.remaining_qty : item.actual_qty) < 0)) throw new Error("Ingredient measurements cannot be negative.")
    if (!run.value) run.value = await createRunFromPlan(props.plan.name, selectedRow.value.name, productionDate.value, props.plan.location, "Finished Meals")
    run.value = await updateProductionActuals(run.value.name, Number(actualOutput.value), measurements.map(item => ({ item_code: item.item_code, measurement_method: item.measurement_method, actual_qty: Number(item.actual_qty), remaining_qty: Number(item.remaining_qty) })), notes.value)
    dirtySinceSave.value = false
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

async function postRun() {
  busy.value = true
  error.value = ""
  try {
    if (dirtySinceSave.value) throw new Error("Save the changed measurements before posting.")
    run.value = await submitProductionRun(run.value.name)
    emit("changed")
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

function quantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }

// endregion PLANNED PRODUCTION STATION
</script>

<template>
  <section data-block="production-measurement" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Production</p><h1>Record the next planned meal</h1><p>BulkBite selects the earliest unfinished week, loads its meal and expected quantities, then waits for the actual measurements.</p></div><SystemBadge v-if="selectedRow">Week {{ selectedRow.week_number }}</SystemBadge></header>
    <ol class="workflow-steps" aria-label="Production progress">
      <li :class="{ 'is-current': selectedRow && !run, 'is-complete': run || station.state === 'complete' }"><span>1</span><div><strong>Planned meal ready</strong><small>The next unfinished week is selected automatically.</small></div></li>
      <li :class="{ 'is-current': selectedRow && !run, 'is-complete': run }"><span>2</span><div><strong>Enter actuals</strong><small>Record food made and ingredient measurements.</small></div></li>
      <li :class="{ 'is-current': run && !run.docstatus, 'is-complete': run?.docstatus || station.state === 'complete' }"><span>3</span><div><strong>Review and post</strong><small>Confirm the stock movement once.</small></div></li>
    </ol>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="!plan" class="state-message">Create and save a monthly plan before recording production.</div>
    <div v-else-if="station.state === 'complete'" class="state-message"><strong>This plan is complete.</strong><p>All four planned weeks have posted production runs.</p></div>
    <template v-else-if="selectedRow">
      <section class="form-section">
        <div class="section-heading"><div><p class="eyebrow">Step 1</p><h2>{{ selectedRow.finished_item_name }}</h2><p>{{ plan.plan_title }}, week {{ selectedRow.week_number }}. The meal and theory come from Planning.</p></div><SystemBadge>{{ quantity(selectedRow.planned_output_qty) }} kg expected</SystemBadge></div>
        <div class="field-grid"><SystemDatePicker v-model="productionDate" label="Production date" format="YYYY-MM-DD" :disabled="Boolean(run)" :clearable="false" /><SystemFormControl v-model="actualOutput" type="number" label="Food made (kg)" min="0" step="0.1" size="lg" /></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Step 2</p><h2>Enter what happened</h2><p>Use quantity used, or enter what remained after the cook.</p></div></div>
        <div class="measurement-list">
          <article v-for="item in measurements" :key="item.item_code" class="measurement-row">
            <div><strong>{{ item.item_name }}</strong><small>Expected {{ quantity(item.expected_qty) }} {{ item.uom }} · Available {{ quantity(item.available_qty) }} {{ item.uom }}</small></div>
            <label class="field-shell"><span>Enter</span><SystemSelect v-model="item.measurement_method" :options="[{ label: 'Quantity used', value: 'Used' }, { label: 'Quantity left', value: 'Remaining' }]" size="lg" /></label>
            <SystemFormControl v-if="item.measurement_method === 'Used'" v-model="item.actual_qty" type="number" label="Used" min="0" step="0.1" size="lg" />
            <SystemFormControl v-else v-model="item.remaining_qty" type="number" label="Left" min="0" step="0.1" size="lg" />
            <span class="unit-label">{{ item.uom }}</span>
          </article>
        </div>
        <SystemTextarea v-model="notes" placeholder="Production notes or reason for a large difference" :rows="3" />
      </section>
      <footer class="posting-bar">
        <div><SystemBadge>{{ run ? (run.docstatus ? "STOCK UPDATED" : "READY TO POST") : "MEASUREMENTS NOT SAVED" }}</SystemBadge><p>{{ run ? (run.docstatus ? "Ingredient use and finished meals are now reflected in stock." : "Review the saved measurements, then post the production run.") : "Save the measurements first. Stock will not change yet." }}</p></div>
        <SystemOperationalButton v-if="!run || !run.docstatus" variant="outline" size="lg" :loading="busy" @click="saveRun">Save measurements</SystemOperationalButton>
        <SystemOperationalButton v-if="run && !run.docstatus" variant="solid" size="lg" :loading="busy" :disabled="dirtySinceSave" @click="postRun">Post production</SystemOperationalButton>
      </footer>
    </template>
  </section>
</template>
