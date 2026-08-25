<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import {
  SystemBadge, SystemCheckboxShadcn, SystemDatePicker, SystemFormControl, SystemLinkedRecordField,
  SystemMultiFileUploader, SystemOperationalButton, SystemSelect,
} from "@/desyium"
import { getEmployeeWorkspace, saveEmployee, saveEmployeeType } from "@/resources/api"

// =============================================================================
// region EMPLOYEE MANAGEMENT WORKSPACE
// =============================================================================

const emit = defineEmits(["close", "changed"])
const workspace = ref(null)
const loading = ref(false)
const savingEmployee = ref(false)
const savingType = ref(false)
const error = ref("")
const success = ref("")
const savedEmployeeName = ref("")
const savedTypeName = ref("")
const documents = ref([])
const paymentOptions = ["Once-off", "Hourly", "Weekly", "Monthly", "Per Production Run"].map(value => ({ label: value, value }))
const statusOptions = ["Active", "Inactive", "On Leave", "Ended"].map(value => ({ label: value, value }))
const employeeTypeOptions = computed(() => (workspace.value?.employee_types || []).map(row => ({ label: row.employee_type_name, value: row.name })))
const employeeType = reactive(newEmployeeType())
const employee = reactive(newEmployee())
const capacity = computed(() => workspace.value?.capacity || {})

function today() { return new Date().toLocaleDateString("en-CA") }
function money(value) { return `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function quantity(value, digits = 2) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: digits }) }
function newEmployeeType() { return { name: "", employee_type_name: "", description: "", capacity_basis: "Kg per Production Run", capacity_per_worker: 1, expected_hours_per_run: 8, payment_basis: "Monthly", payment_rate: 0, working_assumptions: "", enabled: 1 } }
function newEmployee() { return { name: "", full_name: "", employee_type: "", status: "Active", available_for_production: 1, available_hours_per_run: 0, email_address: "", phone_number: "", start_date: today(), end_date: "", use_payment_override: 0, payment_basis_override: "", payment_rate_override: 0, notes: "" } }
function clearMessages() { error.value = ""; success.value = "" }
function resetEmployeeType() { Object.assign(employeeType, newEmployeeType()); savedTypeName.value = "" }
function resetEmployee() { Object.assign(employee, newEmployee()); documents.value = []; savedEmployeeName.value = "" }
function editEmployeeType(row) { Object.assign(employeeType, newEmployeeType(), row); document.querySelector("#employee-type-form")?.scrollIntoView({ behavior: "smooth", block: "start" }) }
function editEmployee(row) {
  Object.assign(employee, newEmployee(), row)
  documents.value = (row.documents || []).map(item => ({ ...item, file_url: item.document_file, file_name: item.document_type }))
  document.querySelector("#employee-form")?.scrollIntoView({ behavior: "smooth", block: "start" })
}
function scrollToTypes() { document.querySelector("#employee-type-form")?.scrollIntoView({ behavior: "smooth", block: "start" }) }

watch(() => employee.employee_type, employeeTypeName => {
  if (!employeeTypeName || Number(employee.available_hours_per_run) > 0) return
  const selectedType = (workspace.value?.employee_types || []).find(row => row.name === employeeTypeName)
  employee.available_hours_per_run = Number(selectedType?.expected_hours_per_run || 0)
})

async function loadWorkspace({ quiet = false } = {}) {
  if (!quiet) loading.value = true
  try { workspace.value = await getEmployeeWorkspace() }
  catch (exception) { error.value = exception.message }
  finally { if (!quiet) loading.value = false }
}

async function submitEmployeeType() {
  savingType.value = true; clearMessages()
  try {
    const saved = await saveEmployeeType({ ...employeeType })
    resetEmployeeType()
    await loadWorkspace({ quiet: true })
    savedTypeName.value = saved.name
    success.value = `${saved.employee_type_name} was saved and capacity has been recalculated.`
    emit("changed")
    await nextTick()
    document.querySelector(`[data-employee-type="${CSS.escape(saved.name)}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  } catch (exception) { error.value = exception.message }
  finally { savingType.value = false }
}

async function submitEmployee() {
  savingEmployee.value = true; clearMessages()
  try {
    const saved = await saveEmployee({ ...employee, documents: documents.value.map(file => ({ document_type: file.document_type || file.file_name, document_file: file.file_url, expiry_date: file.expiry_date || "", notes: file.notes || "" })) })
    resetEmployee()
    await loadWorkspace({ quiet: true })
    savedEmployeeName.value = saved.name
    success.value = `${saved.full_name} was saved and is now in the employee list.`
    emit("changed")
    await nextTick()
    document.querySelector(`[data-employee="${CSS.escape(saved.name)}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  } catch (exception) { error.value = exception.message }
  finally { savingEmployee.value = false }
}

onMounted(loadWorkspace)

// endregion EMPLOYEE MANAGEMENT WORKSPACE
</script>

<template>
  <section data-block="employee-management" class="workflow-block">
    <header class="workflow-header">
      <div><p class="eyebrow">Production</p><h1>Employees and capacity</h1><p>Check whether the current team can meet demand, maintain people, then adjust the assumptions used for planning.</p></div>
      <SystemOperationalButton variant="outline" @click="emit('close')">Back</SystemOperationalButton>
    </header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="success" class="state-message" role="status">{{ success }}</div>
    <div v-if="loading && !workspace" class="state-message" role="status">Loading employees and production evidence.</div>

    <section class="capacity-panel" aria-labelledby="capacity-heading">
      <div class="section-heading capacity-heading">
        <div><p class="eyebrow">Lean capacity</p><h2 id="capacity-heading">Can the current team make the next planned output?</h2><p>Takt is calculated from the total hours each available employee can work in one production run. The current labour rate comes from the latest four posted runs when evidence exists, otherwise it uses the employee-type theory below.</p></div>
        <SystemBadge :theme="capacity.status === 'Under capacity' ? 'red' : capacity.status === 'Capacity not configured' ? undefined : 'green'">{{ capacity.status || 'Capacity not configured' }}</SystemBadge>
      </div>
      <div class="capacity-summary">
        <article><span>Demand</span><strong>{{ quantity(capacity.required_output_qty) }} kg</strong><small>current weekly output</small></article>
        <article><span>Takt time</span><strong>{{ quantity(capacity.takt_minutes_per_kg) }} min/kg</strong><small>available time per required kg</small></article>
        <article><span>Workers needed</span><strong>{{ capacity.required_workers || 0 }}</strong><small>{{ capacity.planning_basis || 'No rate yet' }}</small></article>
        <article><span>Workers available</span><strong>{{ capacity.active_workers || 0 }}</strong><small>{{ quantity(capacity.available_worker_hours) }} team-hours</small></article>
      </div>
      <div class="capacity-decision" :class="capacity.status === 'Under capacity' ? 'is-under' : capacity.status === 'Capacity not configured' ? '' : 'is-ready'">
        <div>
          <strong v-if="capacity.status === 'Under capacity'">Short by {{ quantity(Math.abs(capacity.hour_difference || 0)) }} team-hours at the current rate.</strong>
          <strong v-else-if="capacity.status === 'Over capacity'">{{ quantity(capacity.hour_difference) }} team-hours of capacity are available above the current requirement.</strong>
          <strong v-else-if="capacity.status === 'Capacity not configured'">Add an employee type with kilograms per worker and planned hours.</strong>
          <strong v-else>Available capacity matches the planned demand.</strong>
          <p v-if="capacity.status === 'Under capacity' && capacity.efficiency_improvement_percent">Keep the same team by improving labour efficiency by about {{ quantity(capacity.efficiency_improvement_percent, 1) }}%, or add capacity.</p>
          <p v-if="capacity.status === 'Capacity not configured'">The system cannot judge staffing until a theoretical rate or actual production evidence exists.</p>
          <p v-else-if="capacity.status !== 'Under capacity' || !capacity.efficiency_improvement_percent">{{ quantity(capacity.required_team_hours) }} team-hours are required from {{ quantity(capacity.available_worker_hours) }} available.</p>
        </div>
        <SystemBadge>{{ capacity.planning_basis || 'THEORY' }}</SystemBadge>
      </div>

      <div class="capacity-columns">
        <section class="capacity-detail">
          <div><p class="eyebrow">Planning rate</p><h3>Theory compared with actual</h3></div>
          <dl>
            <div><dt>Theoretical labour</dt><dd>{{ quantity(capacity.theoretical_labour_minutes_per_kg) }} min/kg</dd></div>
            <div><dt>Actual labour</dt><dd>{{ capacity.actual?.run_count ? `${quantity(capacity.actual.labour_minutes_per_kg)} min/kg` : 'No evidence yet' }}</dd></div>
            <div><dt>Actual throughput</dt><dd>{{ capacity.actual?.run_count ? `${quantity(capacity.actual.kg_per_labour_hour)} kg/labour-hour` : 'No evidence yet' }}</dd></div>
            <div><dt>Average team</dt><dd>{{ capacity.actual?.run_count ? `${quantity(capacity.actual.average_team_size, 1)} people` : 'No evidence yet' }}</dd></div>
            <div><dt>Hours per worker</dt><dd>{{ capacity.actual?.run_count ? `${quantity(capacity.actual.average_hours_per_worker)} hours` : 'No evidence yet' }}</dd></div>
          </dl>
        </section>
        <section class="capacity-detail">
          <div><p class="eyebrow">Recent evidence</p><h3>{{ capacity.actual?.source || 'Posted production runs' }}</h3></div>
          <div class="run-evidence">
            <article v-for="run in capacity.actual?.runs || []" :key="run.production_run">
              <div><strong>{{ run.finished_item }}</strong><small>{{ run.production_date }} · {{ run.production_run }}</small></div>
              <span>{{ quantity(run.output_qty) }} kg</span><span>{{ run.team_members }} people</span><span>{{ quantity(run.team_hours) }} team-hours ({{ quantity(run.average_hours_per_worker) }} avg)</span><b>{{ quantity(run.labour_minutes_per_kg) }} min/kg</b>
            </article>
            <p v-if="!capacity.actual?.runs?.length" class="empty-state">Post a production run with employee hours to establish the actual team rate.</p>
          </div>
        </section>
      </div>
    </section>

    <section id="employee-form" class="form-section">
      <div class="section-heading"><div><p class="eyebrow">People</p><h2>{{ employee.name ? 'Edit employee' : 'Add employee' }}</h2><p>Set the person's normal hours for one production run. A specific production run can override this without changing the employee profile.</p></div></div>
      <div v-if="!employeeTypeOptions.length" class="state-message">Create an employee type at the bottom of this page before adding the first employee. <SystemOperationalButton variant="ghost" @click="scrollToTypes">Go to employee types</SystemOperationalButton></div>
      <div class="field-grid employee-fields">
        <SystemFormControl v-model="employee.full_name" label="Full name" />
        <SystemLinkedRecordField v-model="employee.employee_type" label="Employee type" :options="employeeTypeOptions" create-label="Add type below" manage-label="View types below" @create="scrollToTypes" @manage="scrollToTypes" />
        <label class="employee-select-field"><span>Status</span><SystemSelect v-model="employee.status" :options="statusOptions" /></label>
        <SystemFormControl v-model="employee.phone_number" label="Phone" />
        <SystemFormControl v-model="employee.email_address" label="Email" type="email" />
        <SystemFormControl v-model="employee.available_hours_per_run" label="Hours available per production run" type="number" step="0.1" min="0" />
        <SystemDatePicker v-model="employee.start_date" label="Start date" format="YYYY-MM-DD" />
        <SystemDatePicker v-model="employee.end_date" label="End date" format="YYYY-MM-DD" />
        <SystemFormControl v-model="employee.notes" label="Notes" />
      </div>
      <div class="check-row"><label class="check-field"><SystemCheckboxShadcn v-model="employee.available_for_production" /><span>Available for production</span></label><label class="check-field"><SystemCheckboxShadcn v-model="employee.use_payment_override" /><span>Override employee-type payment</span></label></div>
      <div v-if="employee.use_payment_override" class="field-grid"><label class="employee-select-field"><span>Payment basis override</span><SystemSelect v-model="employee.payment_basis_override" :options="paymentOptions" /></label><SystemFormControl v-model="employee.payment_rate_override" label="Payment rate override" type="number" step="0.1" min="0" /></div>
      <div class="document-area"><strong>Private documents</strong><SystemMultiFileUploader v-model="documents" accept="image/*,.pdf" label="Add employee documents" /></div>
      <div class="button-row"><SystemOperationalButton v-if="employee.name" variant="outline" :disabled="savingEmployee" @click="resetEmployee">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="savingEmployee" :disabled="!employeeTypeOptions.length" @click="submitEmployee">{{ employee.name ? 'Save employee' : 'Add employee' }}</SystemOperationalButton></div>
    </section>

    <section class="data-section" aria-labelledby="employee-list-heading">
      <div class="section-heading"><div><p class="eyebrow">Current team</p><h2 id="employee-list-heading">Employees</h2><p>Each profile includes the hours recorded against posted production.</p></div><SystemBadge>{{ workspace?.employees?.length || 0 }} PEOPLE</SystemBadge></div>
      <div class="employee-list">
        <article v-for="row in workspace?.employees || []" :key="row.name" :data-employee="row.name" :class="{ 'is-saved': savedEmployeeName === row.name }">
          <div class="employee-profile">
            <div><strong>{{ row.full_name }}</strong><small>{{ row.employee_type }} · {{ row.phone_number || row.email_address || 'No contact details' }}</small></div>
            <div class="employee-profile__facts"><span>{{ quantity(row.available_hours_per_run) }} hours available per run</span><span>{{ quantity(row.total_completed_hours) }} recorded hours</span><span>{{ row.documents?.length || 0 }} private documents</span><SystemBadge :theme="row.status === 'Active' ? 'green' : undefined">{{ row.status }}</SystemBadge><SystemOperationalButton variant="outline" @click="editEmployee(row)">Edit</SystemOperationalButton></div>
          </div>
          <div class="employee-history">
            <div v-for="history in row.production_history || []" :key="`${row.name}-${history.production_run}`"><span>{{ history.production_date }}</span><strong>{{ history.finished_item }}</strong><span>{{ quantity(history.hours_worked) }} hours</span><span>{{ history.completion_status }}</span><span>{{ money(history.payable_amount) }}</span></div>
            <p v-if="!row.production_history?.length">No posted production hours yet.</p>
          </div>
        </article>
        <p v-if="!workspace?.employees?.length" class="empty-state">No employees have been added.</p>
      </div>
    </section>

    <section id="employee-type-form" class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Planning assumptions</p><h2>{{ employeeType.name ? 'Edit employee type' : 'Add employee type' }}</h2><p>Set how many kilograms one worker should make in the planned hours. This supplies the theoretical rate until real production evidence exists.</p></div></div>
      <div class="field-grid">
        <SystemFormControl v-model="employeeType.employee_type_name" label="Employee type" />
        <SystemFormControl v-model="employeeType.capacity_per_worker" label="Food per worker (kg)" type="number" step="0.1" min="0" />
        <SystemFormControl v-model="employeeType.expected_hours_per_run" label="Planned hours per worker" type="number" step="0.1" min="0" />
        <label class="employee-select-field"><span>Payment basis</span><SystemSelect v-model="employeeType.payment_basis" :options="paymentOptions" /></label>
        <SystemFormControl v-model="employeeType.payment_rate" label="Payment rate" type="number" step="0.1" min="0" />
        <SystemFormControl v-model="employeeType.description" label="Role description" />
        <SystemFormControl v-model="employeeType.working_assumptions" label="Capacity assumptions" />
      </div>
      <label class="check-field"><SystemCheckboxShadcn v-model="employeeType.enabled" /><span>Use this employee type in capacity planning</span></label>
      <div class="button-row"><SystemOperationalButton v-if="employeeType.name" variant="outline" :disabled="savingType" @click="resetEmployeeType">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="savingType" @click="submitEmployeeType">{{ employeeType.name ? 'Save employee type' : 'Add employee type' }}</SystemOperationalButton></div>
    </section>

    <section class="data-section" aria-labelledby="employee-type-list-heading">
      <div class="section-heading"><div><p class="eyebrow">Configured roles</p><h2 id="employee-type-list-heading">Employee types</h2></div></div>
      <div class="record-list"><article v-for="row in workspace?.employee_types || []" :key="row.name" :data-employee-type="row.name" :class="{ 'is-saved': savedTypeName === row.name }"><div><strong>{{ row.employee_type_name }}</strong><small>{{ quantity(row.capacity_per_worker) }} kg per worker in {{ quantity(row.expected_hours_per_run) }} hours · {{ row.payment_basis }} {{ money(row.payment_rate) }}</small></div><div><SystemBadge>{{ row.enabled ? 'Active' : 'Disabled' }}</SystemBadge><SystemOperationalButton variant="outline" @click="editEmployeeType(row)">Edit</SystemOperationalButton></div></article><p v-if="!workspace?.employee_types?.length" class="empty-state">No employee types have been added.</p></div>
    </section>
  </section>
</template>

<style scoped>
.capacity-panel{margin-top:var(--spacing-m);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface);box-shadow:0 1px 2px color-mix(in oklch,var(--theme-text) 5%,transparent)}.capacity-heading{align-items:center}.capacity-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.capacity-summary article{display:grid;gap:var(--spacing-3xs);min-width:0;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.capacity-summary span,.capacity-summary small,.record-list small,.employee-profile small{color:var(--theme-text-muted)}.capacity-summary strong{font-size:var(--font-size-2);font-variant-numeric:tabular-nums}.capacity-decision{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);margin-top:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-secondary)}.capacity-decision.is-warning{border-color:color-mix(in oklch,var(--theme-primary) 38%,var(--theme-border));background:color-mix(in oklch,var(--theme-primary) 5%,var(--theme-surface-raised))}.capacity-decision p{margin:var(--spacing-3xs) 0 0;color:var(--theme-text-muted)}.capacity-columns{display:grid;grid-template-columns:minmax(17rem,.7fr) minmax(22rem,1.3fr);gap:var(--spacing-s);margin-top:var(--spacing-s)}.capacity-detail{display:grid;align-content:start;gap:var(--spacing-s);min-width:0;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.capacity-detail h3{margin:var(--spacing-3xs) 0 0;font-size:var(--font-size-0)}.capacity-detail dl{display:grid;gap:var(--spacing-2xs);margin:0}.capacity-detail dl div{display:flex;justify-content:space-between;gap:var(--spacing-s);padding-bottom:var(--spacing-2xs);border-bottom:var(--border-width-1) solid var(--theme-border)}.capacity-detail dt{color:var(--theme-text-muted)}.capacity-detail dd{margin:0;font-weight:var(--font-weight-600);text-align:right}.run-evidence{display:grid;gap:var(--spacing-2xs)}.run-evidence article{display:grid;grid-template-columns:minmax(9rem,1fr) repeat(4,auto);align-items:center;gap:var(--spacing-xs);padding:var(--spacing-xs);border-radius:var(--component-radius-button);background:var(--theme-secondary)}.run-evidence small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.run-evidence article>span{color:var(--theme-text-muted);white-space:nowrap}.employee-select-field{display:grid;align-content:start;gap:var(--spacing-3xs);min-width:0;color:var(--theme-text);font-size:var(--font-size--2);font-weight:var(--font-weight-600)}.employee-select-field>span{line-height:.875rem}.employee-select-field :deep(.system-component--select){margin-top:0!important}.check-field{display:flex;align-items:center;gap:var(--spacing-xs);min-height:2.75rem}.check-row{display:flex;flex-wrap:wrap;gap:var(--spacing-m)}.document-area{display:grid;gap:var(--spacing-xs);margin:var(--spacing-s) 0}.employee-list,.record-list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.employee-list>article,.record-list>article{display:grid;gap:var(--spacing-xs);padding:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.employee-list>article:last-of-type,.record-list>article:last-of-type{border-bottom:0}.employee-list>article.is-saved,.record-list>article.is-saved{background:color-mix(in oklch,var(--theme-primary) 5%,var(--theme-surface-raised))}.employee-profile{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s)}.employee-profile small{display:block;margin-top:var(--spacing-3xs)}.employee-profile__facts{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:var(--spacing-xs)}.employee-profile__facts>span{color:var(--theme-text-muted);font-size:var(--font-size--2)}.employee-history{display:grid;gap:var(--spacing-3xs);padding-top:var(--spacing-xs);border-top:var(--border-width-1) solid var(--theme-border)}.employee-history>div{display:grid;grid-template-columns:7rem minmax(10rem,1fr) repeat(3,minmax(5rem,auto));gap:var(--spacing-xs);padding:var(--spacing-2xs) 0;color:var(--theme-text-muted);font-size:var(--font-size--2)}.employee-history p{margin:0;color:var(--theme-text-muted);font-size:var(--font-size--2)}.record-list>article{grid-template-columns:minmax(0,1fr) auto;align-items:center}.record-list>article>div:last-child{display:flex;align-items:center;justify-content:flex-end;gap:var(--spacing-xs)}.record-list small{display:block;margin-top:var(--spacing-3xs)}.empty-state{margin:0;padding:var(--spacing-m);color:var(--theme-text-muted);text-align:center}@media(max-width:70rem){.capacity-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.capacity-columns{grid-template-columns:1fr}.run-evidence article{grid-template-columns:minmax(9rem,1fr) repeat(2,auto)}.run-evidence article>b{grid-column:2/-1;text-align:right}.employee-history>div{grid-template-columns:repeat(3,minmax(0,1fr))}.employee-history>div>strong{grid-column:span 2}}@media(max-width:44rem){.capacity-panel{padding:var(--spacing-s)}.capacity-summary{grid-template-columns:1fr 1fr}.capacity-summary strong{font-size:var(--font-size-0)}.capacity-decision,.employee-profile{align-items:flex-start;flex-direction:column}.run-evidence article{grid-template-columns:1fr 1fr}.run-evidence article>div{grid-column:1/-1}.employee-profile__facts{justify-content:flex-start}.employee-history>div,.record-list>article{grid-template-columns:1fr}.employee-history>div>strong{grid-column:auto}.record-list>article>div:last-child{justify-content:flex-start}}@media(max-width:24rem){.capacity-summary{grid-template-columns:1fr}}
.capacity-decision.is-under{border-color:color-mix(in oklch,var(--theme-error) 52%,var(--theme-border));background:color-mix(in oklch,var(--theme-error) 10%,var(--theme-surface-raised))}.capacity-decision.is-ready{border-color:color-mix(in oklch,var(--theme-success) 52%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 10%,var(--theme-surface-raised))}
</style>
