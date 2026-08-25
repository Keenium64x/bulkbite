<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import {
  SystemBadge, SystemCheckbox, SystemDatePicker, SystemFormControl, SystemLinkedRecordField,
  SystemMultiFileUploader, SystemOperationalButton, SystemSelect, SystemTabs, SystemTabsContent,
  SystemTabsList, SystemTabsTrigger,
} from "@/desyium"
import { getEmployeeWorkspace, saveEmployee, saveEmployeeType } from "@/resources/api"

// =============================================================================
// region EMPLOYEE MANAGEMENT WORKSPACE
// =============================================================================

const emit = defineEmits(["close", "changed"])
const workspace = ref(null)
const busy = ref(false)
const error = ref("")
const success = ref("")
const activeTab = ref("overview")
const documents = ref([])
const capacityOptions = ["Meals per Production Run", "Kg per Production Run", "Customers Served", "Hours Available", "Runs per Period"].map(value => ({ label: value, value }))
const paymentOptions = ["Once-off", "Hourly", "Weekly", "Monthly", "Per Production Run"].map(value => ({ label: value, value }))
const statusOptions = ["Active", "Inactive", "On Leave", "Ended"].map(value => ({ label: value, value }))
const employeeTypeOptions = computed(() => (workspace.value?.employee_types || []).map(row => ({ label: row.employee_type_name, value: row.name })))
const employeeType = reactive(newEmployeeType())
const employee = reactive(newEmployee())

function today() { return new Date().toLocaleDateString("en-CA") }
function money(value) { return `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function quantity(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 }) }
function newEmployeeType() { return { name: "", employee_type_name: "", description: "", capacity_basis: "Meals per Production Run", capacity_per_worker: 1, expected_hours_per_run: 0, payment_basis: "Monthly", payment_rate: 0, working_assumptions: "", enabled: 1 } }
function newEmployee() { return { name: "", full_name: "", employee_type: "", status: "Active", available_for_production: 1, email_address: "", phone_number: "", start_date: today(), end_date: "", use_payment_override: 0, payment_basis_override: "", payment_rate_override: 0, notes: "" } }
function clearMessages() { error.value = ""; success.value = "" }
function resetEmployeeType() { Object.assign(employeeType, newEmployeeType()) }
function resetEmployee() { Object.assign(employee, newEmployee()); documents.value = [] }
function editEmployeeType(row) { Object.assign(employeeType, newEmployeeType(), row); activeTab.value = "types" }
function editEmployee(row) { Object.assign(employee, newEmployee(), row); documents.value = (row.documents || []).map(item => ({ ...item, file_url: item.document_file, file_name: item.document_type })); activeTab.value = "employees" }

async function loadWorkspace() {
  busy.value = true; clearMessages()
  try { workspace.value = await getEmployeeWorkspace() }
  catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

async function submitEmployeeType() {
  busy.value = true; clearMessages()
  try { await saveEmployeeType({ ...employeeType }); resetEmployeeType(); await loadWorkspace(); success.value = "Employee type saved."; emit("changed") }
  catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

async function submitEmployee() {
  busy.value = true; clearMessages()
  try {
    await saveEmployee({ ...employee, documents: documents.value.map(file => ({ document_type: file.document_type || file.file_name, document_file: file.file_url, expiry_date: file.expiry_date || "", notes: file.notes || "" })) })
    resetEmployee(); await loadWorkspace(); success.value = "Employee profile saved."; emit("changed")
  } catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

onMounted(loadWorkspace)

// endregion EMPLOYEE MANAGEMENT WORKSPACE
</script>

<template>
  <section data-block="employee-management" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Production</p><h1>Employees and capacity</h1><p>Maintain worker profiles here. Planning and Finance use the same role capacity and payment rules.</p></div><SystemOperationalButton variant="outline" @click="emit('close')">Back to production</SystemOperationalButton></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div><div v-if="success" class="state-message" role="status">{{ success }}</div>
    <SystemTabs v-model="activeTab" class="employee-tabs">
      <SystemTabsList class="employee-tabs__list"><SystemTabsTrigger value="overview">Capacity</SystemTabsTrigger><SystemTabsTrigger value="types">Employee types</SystemTabsTrigger><SystemTabsTrigger value="employees">Employees</SystemTabsTrigger></SystemTabsList>
      <SystemTabsContent value="overview" class="employee-tabs__content">
        <section class="capacity-summary"><article><strong>{{ workspace?.capacity?.required_workers || 0 }}</strong><span>workers required</span></article><article><strong>{{ workspace?.capacity?.active_workers || 0 }}</strong><span>active and available</span></article><article><strong>{{ workspace?.capacity?.under_capacity_types || 0 }}</strong><span>roles under capacity</span></article><article><strong>{{ money(workspace?.capacity?.expected_monthly_cost) }}</strong><span>expected labour per cycle</span></article></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Current direction</p><h2>Capacity by employee type</h2><p>Required workers recalculate from the current customer mix and each role's operational capacity.</p></div></div><div class="capacity-list"><article v-for="row in workspace?.capacity?.rows || []" :key="row.name"><div><strong>{{ row.employee_type_name }}</strong><small>{{ quantity(row.required_capacity) }} {{ row.capacity_basis }} required · {{ quantity(row.available_capacity) }} available</small><small>{{ row.payment_basis }} at {{ money(row.payment_rate) }}</small></div><div><b>{{ row.required_workers }} needed / {{ row.active_workers }} active</b><SystemBadge :theme="row.status === 'Under capacity' ? 'orange' : row.status === 'At capacity' ? 'green' : undefined">{{ row.status }}</SystemBadge></div><p v-if="row.warning">{{ row.warning }}</p></article><p v-if="!workspace?.capacity?.rows?.length" class="empty-state">Add an employee type to start capacity planning.</p></div></section>
      </SystemTabsContent>
      <SystemTabsContent value="types" class="employee-tabs__content">
        <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Role setup</p><h2>{{ employeeType.name ? 'Edit employee type' : 'Add employee type' }}</h2><p>Define what one worker can produce and how that role is paid.</p></div></div><div class="field-grid"><SystemFormControl v-model="employeeType.employee_type_name" label="Employee type" /><SystemSelect v-model="employeeType.capacity_basis" label="Capacity measured by" :options="capacityOptions" /><SystemFormControl v-model="employeeType.capacity_per_worker" label="Capacity per worker" type="number" step="0.1" /><SystemFormControl v-model="employeeType.expected_hours_per_run" label="Expected hours per run" type="number" step="0.1" /><SystemSelect v-model="employeeType.payment_basis" label="Payment basis" :options="paymentOptions" /><SystemFormControl v-model="employeeType.payment_rate" label="Payment rate" type="number" step="0.1" /><SystemFormControl v-model="employeeType.description" label="Role description" /><SystemFormControl v-model="employeeType.working_assumptions" label="Capacity assumptions" /></div><label class="check-field"><SystemCheckbox v-model="employeeType.enabled" /><span>Use this employee type</span></label><div class="button-row"><SystemOperationalButton v-if="employeeType.name" variant="outline" @click="resetEmployeeType">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="busy" @click="submitEmployeeType">Save employee type</SystemOperationalButton></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Configured roles</p><h2>Employee types</h2></div></div><div class="record-list"><article v-for="row in workspace?.employee_types || []" :key="row.name"><div><strong>{{ row.employee_type_name }}</strong><small>{{ quantity(row.capacity_per_worker) }} {{ row.capacity_basis }} · {{ row.payment_basis }} {{ money(row.payment_rate) }}</small></div><div><SystemBadge>{{ row.enabled ? 'Active' : 'Disabled' }}</SystemBadge><SystemOperationalButton variant="outline" @click="editEmployeeType(row)">Edit</SystemOperationalButton></div></article></div></section>
      </SystemTabsContent>
      <SystemTabsContent value="employees" class="employee-tabs__content">
        <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Employee profile</p><h2>{{ employee.name ? 'Edit employee' : 'Add employee' }}</h2><p>Store contact, availability, payment override, and private employee documents.</p></div></div><div class="field-grid"><SystemFormControl v-model="employee.full_name" label="Full name" /><SystemLinkedRecordField v-model="employee.employee_type" label="Employee type" :options="employeeTypeOptions" /><SystemSelect v-model="employee.status" label="Status" :options="statusOptions" /><SystemFormControl v-model="employee.phone_number" label="Phone" /><SystemFormControl v-model="employee.email_address" label="Email" type="email" /><SystemDatePicker v-model="employee.start_date" label="Start date" format="YYYY-MM-DD" /><SystemDatePicker v-model="employee.end_date" label="End date" format="YYYY-MM-DD" /><SystemFormControl v-model="employee.notes" label="Notes" /></div><div class="check-row"><label class="check-field"><SystemCheckbox v-model="employee.available_for_production" /><span>Available for production</span></label><label class="check-field"><SystemCheckbox v-model="employee.use_payment_override" /><span>Override employee type payment</span></label></div><div v-if="employee.use_payment_override" class="field-grid"><SystemSelect v-model="employee.payment_basis_override" label="Payment basis override" :options="paymentOptions" /><SystemFormControl v-model="employee.payment_rate_override" label="Payment rate override" type="number" step="0.1" /></div><div class="document-area"><strong>Private documents</strong><SystemMultiFileUploader v-model="documents" accept="image/*,.pdf" label="Add employee documents" /></div><div class="button-row"><SystemOperationalButton v-if="employee.name" variant="outline" @click="resetEmployee">Cancel edit</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="busy" @click="submitEmployee">Save employee</SystemOperationalButton></div></section>
        <section class="data-section"><div class="section-heading"><div><p class="eyebrow">People</p><h2>Employee profiles</h2></div></div><div class="record-list"><article v-for="row in workspace?.employees || []" :key="row.name"><div><strong>{{ row.full_name }}</strong><small>{{ row.employee_type }} · {{ row.phone_number || row.email_address || 'No contact details' }}</small><small>{{ row.documents?.length || 0 }} private documents</small></div><div><SystemBadge :theme="row.status === 'Active' ? 'green' : undefined">{{ row.status }}</SystemBadge><SystemOperationalButton variant="outline" @click="editEmployee(row)">Open profile</SystemOperationalButton></div></article><p v-if="!workspace?.employees?.length" class="empty-state">No employees have been added.</p></div></section>
      </SystemTabsContent>
    </SystemTabs>
  </section>
</template>

<style scoped>
.employee-tabs,.employee-tabs__content{display:grid;gap:var(--spacing-m)}.employee-tabs__list{justify-content:flex-start!important;width:fit-content;max-width:100%;overflow-x:auto}.employee-tabs__list :deep([role="tab"]){min-height:2.75rem}.capacity-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.capacity-summary article{display:grid;gap:var(--spacing-2xs);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.capacity-summary strong{font-size:var(--font-size-2)}.capacity-summary span,.capacity-list small,.record-list small{color:var(--theme-text-muted)}.capacity-list,.record-list{display:grid;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden}.capacity-list article,.record-list article{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:var(--spacing-s);padding:var(--spacing-s);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.capacity-list article:last-child,.record-list article:last-child{border-bottom:0}.capacity-list small,.record-list small{display:block;margin-top:var(--spacing-3xs)}.capacity-list article>div:last-of-type,.record-list article>div:last-child{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:var(--spacing-xs)}.capacity-list article>p{grid-column:1/-1;margin:0;color:var(--theme-text-muted)}.check-field{display:flex;align-items:center;gap:var(--spacing-xs);min-height:2.75rem}.document-area{display:grid;gap:var(--spacing-xs);margin:var(--spacing-s) 0}.empty-state{margin:0;padding:var(--spacing-l);color:var(--theme-text-muted);text-align:center}@media(max-width:700px){.capacity-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.capacity-list article,.record-list article{grid-template-columns:1fr}.capacity-list article>div:last-of-type,.record-list article>div:last-child{justify-content:flex-start}}@media(max-width:420px){.capacity-summary{grid-template-columns:1fr}}
</style>
