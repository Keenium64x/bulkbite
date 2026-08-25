<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemDatePicker, SystemFormControl, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { createRunFromPlan, discardProductionRun, saveProductionEmployees, submitProductionRun, updateProductionActuals } from "@/resources/api"

// =============================================================================
// region PLANNED PRODUCTION STATION
// =============================================================================

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed", "open-worker-sheets", "open-employees"])
const localToday = () => { const value = new Date(); return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}` }
const productionDate = ref(localToday())
const actualOutput = ref(0)
const notes = ref("")
const measurements = reactive([])
const employeeRows = reactive([])
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
watch(employeeRows, () => { if (run.value) dirtySinceSave.value = true }, { deep: true })

function hydrateStation(value) {
  const row = value?.row
  run.value = value?.run || null
  measurements.splice(0)
  if (!row) return
  productionDate.value = run.value?.production_date || row.planned_date || localToday()
  actualOutput.value = roundQuantity(run.value?.actual_output_qty ?? row.planned_output_qty)
  notes.value = run.value?.notes || ""
  const runIngredients = new Map((run.value?.ingredients || []).map(item => [item.item_code, item]))
  row.ingredients.forEach(item => {
    const saved = runIngredients.get(item.item_code)
    measurements.push({ ...item, measurement_method: saved?.measurement_method || "Used", actual_qty: roundQuantity(saved?.actual_qty ?? item.expected_qty), remaining_qty: roundQuantity(saved?.remaining_qty ?? item.available_qty) })
  })
  employeeRows.splice(0, employeeRows.length, ...(run.value?.employees || []).map(row => ({ ...row })))
  dirtySinceSave.value = false
}

async function saveRun() {
  busy.value = true
  error.value = ""
  try {
    if (!selectedRow.value) throw new Error("There is no planned meal ready.")
    if (!productionDate.value) throw new Error("Choose the production date.")
    if (Number(actualOutput.value) <= 0) throw new Error("Food made must be greater than zero.")
    if (measurements.some(item => Number(item.measurement_method === "Remaining" ? item.remaining_qty : item.actual_qty) < 0)) throw new Error("Ingredient measurements cannot be negative.")
    if (!run.value) run.value = await createRunFromPlan(props.plan.name, selectedRow.value.name, productionDate.value, props.plan.location, "Finished Meals")
    run.value = await updateProductionActuals(run.value.name, roundQuantity(actualOutput.value), measurements.map(item => ({ item_code: item.item_code, measurement_method: item.measurement_method, actual_qty: roundQuantity(item.actual_qty), remaining_qty: roundQuantity(item.remaining_qty) })), notes.value)
    run.value = await saveProductionEmployees(run.value.name, employeeRows)
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

async function discardRun() {
  if (!run.value || !window.confirm("Discard this production draft and reload the latest customer direction?")) return
  busy.value = true
  error.value = ""
  try {
    await discardProductionRun(run.value.name)
    run.value = null
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

function roundQuantity(value) { return Math.round(Number(value || 0) * 1000) / 1000 }
function quantity(value) { return roundQuantity(value).toLocaleString("en-ZA", { maximumFractionDigits: 3 }) }
const employeeOptions = computed(() => props.snapshot?.options?.employees || [])
const attendanceOptions = ["Assigned", "Completed", "Absent", "Cancelled"].map(value => ({ label: value, value }))
function addEmployee() { employeeRows.push({ employee: "", hours_worked: 0, completion_status: "Completed", notes: "" }); dirtySinceSave.value = true }
function removeEmployee(index) { employeeRows.splice(index, 1); dirtySinceSave.value = true }

// endregion PLANNED PRODUCTION STATION
</script>

<template>
  <section data-block="production-measurement" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Production</p><h1>Record the next meal</h1><p>The current direction chooses the next meal. Saving keeps a draft; posting moves stock once.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="emit('open-employees')">Employees</SystemOperationalButton><SystemOperationalButton variant="outline" @click="emit('open-worker-sheets')">Worker sheets</SystemOperationalButton><SystemBadge v-if="selectedRow">Cycle {{ station.cycle_number || 1 }} · Meal {{ selectedRow.week_number }}</SystemBadge></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="!plan" class="state-message">Set the current meal direction before recording production.</div>
    <template v-else-if="selectedRow">
      <section class="form-section">
        <div class="section-heading"><div><p class="eyebrow">Current meal</p><h2>{{ selectedRow.finished_item_name }}</h2><p>{{ plan.plan_title }}, meal {{ selectedRow.week_number }}. The saved draft keeps this theory even if customer counts change later.</p></div><SystemBadge>{{ quantity(selectedRow.planned_output_qty) }} kg expected</SystemBadge></div>
        <div class="production-topline"><div class="field-grid"><SystemDatePicker v-model="productionDate" label="Production date" format="YYYY-MM-DD" :disabled="Boolean(run)" :clearable="false" /><SystemFormControl v-model="actualOutput" type="number" label="Food made (kg)" min="0" step="0.1" size="lg" /></div><div class="button-row"><SystemOperationalButton v-if="!run || !run.docstatus" variant="outline" size="lg" :loading="busy" @click="saveRun">Save draft</SystemOperationalButton><SystemOperationalButton v-if="run && !run.docstatus" variant="ghost" size="lg" :disabled="busy" @click="discardRun">Discard draft</SystemOperationalButton><SystemOperationalButton v-if="run && !run.docstatus" variant="solid" size="lg" :loading="busy" :disabled="dirtySinceSave" @click="postRun">Post production</SystemOperationalButton></div></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Measurements</p><h2>Enter what happened</h2><p>Use quantity used, or enter what remained after the cook.</p></div></div>
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
      <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Employees</p><h2>Who worked on this production run</h2><p>Saving freezes attendance and pay facts. Posting creates actual labour costs only for hourly and per-run payment.</p></div><SystemOperationalButton variant="outline" :disabled="Boolean(run?.docstatus)" @click="addEmployee">Add employee</SystemOperationalButton></div><div class="employee-assignment-list"><article v-for="(row, index) in employeeRows" :key="index"><SystemSelect v-model="row.employee" label="Employee" :options="employeeOptions" :disabled="Boolean(run?.docstatus)" /><SystemSelect v-model="row.completion_status" label="Work status" :options="attendanceOptions" :disabled="Boolean(run?.docstatus)" /><SystemFormControl v-model="row.hours_worked" label="Hours worked" type="number" step="0.1" min="0" :disabled="Boolean(run?.docstatus)" /><SystemFormControl v-model="row.notes" label="Notes" :disabled="Boolean(run?.docstatus)" /><SystemOperationalButton v-if="!run?.docstatus" variant="ghost" @click="removeEmployee(index)">Remove</SystemOperationalButton><small v-if="row.payment_basis">{{ row.payment_basis }} · R {{ Number(row.payment_rate || 0).toFixed(2) }} · R {{ Number(row.payable_amount || 0).toFixed(2) }} payable</small></article><p v-if="!employeeRows.length" class="state-message">No employees assigned yet.</p></div></section>
      <footer class="posting-bar">
        <div><SystemBadge>{{ run ? (run.docstatus ? "STOCK UPDATED" : "READY TO POST") : "MEASUREMENTS NOT SAVED" }}</SystemBadge><p>{{ run ? (run.docstatus ? "Ingredient use and finished meals are now reflected in stock." : "Review the saved measurements, then post the production run.") : "Save the measurements first. Stock will not change yet." }}</p></div>
      </footer>
    </template>
    <section class="data-section" aria-labelledby="production-history-heading"><div class="section-heading"><div><p class="eyebrow">History</p><h2 id="production-history-heading">Past production</h2><p>Posted runs are permanent. Drafts can be opened from the current production area.</p></div></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Meal</th><th>Food made</th><th>Status</th></tr></thead><tbody><tr v-for="item in snapshot?.recent_runs || []" :key="item.name"><td>{{ item.production_date }}</td><td><strong>{{ item.finished_item }}</strong><small>{{ item.name }}</small></td><td>{{ quantity(item.actual_output_qty) }} kg</td><td><SystemBadge>{{ item.docstatus ? "POSTED" : "DRAFT" }}</SystemBadge></td></tr><tr v-if="!snapshot?.recent_runs?.length"><td colspan="4">No production runs yet.</td></tr></tbody></table></div></section>
  </section>
</template>

<style scoped>
.production-topline{display:flex;align-items:end;justify-content:space-between;gap:var(--spacing-s);flex-wrap:wrap}.production-topline>.field-grid{flex:1 1 34rem}.production-topline>.button-row{justify-content:flex-end}.employee-assignment-list{display:grid;gap:var(--spacing-xs)}.employee-assignment-list article{display:grid;grid-template-columns:1fr .75fr .55fr 1fr auto;align-items:end;gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-secondary)}.employee-assignment-list article>small{grid-column:1/-1;color:var(--theme-text-muted)}@media(max-width:64rem){.employee-assignment-list article{grid-template-columns:repeat(2,minmax(0,1fr))}.employee-assignment-list article>*:last-of-type{justify-self:start}}@media(max-width:52rem){.production-topline,.production-topline>.field-grid{display:grid;grid-template-columns:1fr;width:100%}.production-topline>.button-row{justify-content:stretch}.production-topline>.button-row>*{flex:1 1 auto}}@media(max-width:44rem){.employee-assignment-list article{grid-template-columns:1fr}}
</style>
