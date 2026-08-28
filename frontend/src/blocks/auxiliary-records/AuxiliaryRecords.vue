<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import {
  SystemBadge,
  SystemCard,
  SystemCheckboxShadcn,
  SystemDatePicker,
  SystemDialog,
  SystemDialogContent,
  SystemDialogDescription,
  SystemDialogFooter,
  SystemDialogHeader,
  SystemDialogTitle,
  SystemFormControl,
  SystemLinkedRecordField,
  SystemOperationalButton,
  SystemSelect,
  SystemTextarea,
} from "@/desyium"
import { auxiliaryRecordSystem, recordDefinition } from "@/forms/auxiliary-records.definition"
import { DELETE_OUTCOME, DELETE_STAGE, deletionOutcomeAllowed, finalDeleteRequest, normalizeDeletionPlan, relatedTypeChoices } from "@/forms/auxiliary-record-deletion"

// =============================================================================
// region AUXILIARY RECORD WORKFLOW
// =============================================================================

const props = defineProps({
  doctype: { type: String, default: "" },
  recordName: { type: String, default: "" },
  mode: { type: String, default: "catalogue" },
})
const emit = defineEmits(["navigate", "saved"])
const catalogue = ref([])
const records = ref([])
const workspace = ref(null)
const contract = ref(null)
const values = reactive({})
const tables = reactive({})
const loading = ref(true)
const saving = ref(false)
const error = ref("")
const fieldErrors = reactive({})
const search = ref("")
const activeFilters = reactive({})
const selectedNames = ref([])
const deleteStage = ref(DELETE_STAGE.CLOSED)
const deletePlan = ref(null)
const deleteBusy = ref(false)
const deleteNames = ref([])
const deleteOutcome = ref("")
const deleteOutcomesByDoctype = reactive({})
const currentListDoctype = ref("")
const selectedForm = computed(() => catalogue.value.find((row) => row.doctype === props.doctype))
const availableFilters = computed(() => {
  const preferred = recordDefinition(props.doctype).list?.filters || []
  const filters = workspace.value?.filters || []
  return preferred.length ? [...filters].sort((left, right) => preferred.indexOf(left.field) - preferred.indexOf(right.field)).filter((row) => preferred.includes(row.field)) : filters
})
const allSelected = computed(() => Boolean(records.value.length && records.value.every((row) => selectedNames.value.includes(row.name))))
const canDelete = computed(() => Boolean(workspace.value?.permissions?.bulkDelete))
const deleteConnections = computed(() => [...(deletePlan.value?.roots || []), ...(deletePlan.value?.dependencies || [])].filter((row) => row.linkedBy.length))
const deleteOutcomeAllowed = computed(() => deletionOutcomeAllowed(deletePlan.value, deleteOutcome.value))
const deleteOutcomeBlockers = computed(() => deletePlan.value?.resolution?.blockers || deletePlan.value?.blockers || [])
const deleteRecordCount = computed(() => (deletePlan.value?.resolution?.deleteCount || 0) + (deletePlan.value?.resolution?.archiveCount || 0))
const deleteRelatedTypes = computed(() => relatedTypeChoices(deletePlan.value))
const deleteOpen = computed({ get: () => Boolean(deleteStage.value), set: (open) => { if (!open) cancelDelete() } })
const pageTitle = computed(() => {
  if (props.mode === "create") return `Add ${selectedForm.value?.label || props.doctype}`
  if (props.mode === "edit") return `Edit ${selectedForm.value?.label || props.doctype}`
  if (props.mode === "list") return selectedForm.value?.label || props.doctype
  return "Setup records"
})

onMounted(loadCurrentView)
watch(() => [props.doctype, props.recordName, props.mode], loadCurrentView)

async function loadCurrentView() {
  loading.value = true
  error.value = ""
  try {
    catalogue.value = await auxiliaryRecordSystem.resources.catalogue()
    records.value = []
    contract.value = null
    clearReactive(values)
    clearReactive(tables)
    workspace.value = null
    selectedNames.value = []
    if (props.mode === "list" && props.doctype) {
      if (currentListDoctype.value !== props.doctype) {
        search.value = ""
        clearReactive(activeFilters)
        currentListDoctype.value = props.doctype
      }
      await loadWorkspace()
    } else if (["create", "edit"].includes(props.mode) && props.doctype) {
      const result = await auxiliaryRecordSystem.resources.load(props.doctype, props.mode === "edit" ? props.recordName : undefined)
      contract.value = result.contract
      Object.assign(values, result.values || {})
      Object.assign(tables, result.tables || {})
    }
  } catch (caught) {
    error.value = caught?.message || "Setup records could not be loaded."
  } finally {
    loading.value = false
  }
}

async function loadWorkspace(page = 1) {
  const filters = Object.entries(activeFilters).filter(([, value]) => value !== "" && value !== null && value !== undefined).map(([field, value]) => ({ field, operator: "=", value }))
  workspace.value = await auxiliaryRecordSystem.resources.list(props.doctype, { search: search.value.trim() || undefined, page, page_size: auxiliaryRecordSystem.page.pageSize, filters })
  records.value = workspace.value.rows || []
  selectedNames.value = selectedNames.value.filter((name) => records.value.some((row) => row.name === name))
}
async function applyListQuery() {
  loading.value = true
  error.value = ""
  try { await loadWorkspace(1) }
  catch (caught) { error.value = caught?.message || "Setup records could not be filtered." }
  finally { loading.value = false }
}
function filterOptions(filter) {
  return [{ label: "All", value: "" }, ...(filter.options || [])]
}
function toggleSelected(name, checked) {
  selectedNames.value = checked ? [...new Set([...selectedNames.value, name])] : selectedNames.value.filter((value) => value !== name)
}
function toggleAll(checked) {
  selectedNames.value = checked ? records.value.map((row) => row.name) : []
}

function clearReactive(target) {
  Object.keys(target).forEach((key) => delete target[key])
}
function fieldComponent(field) {
  if (field.type === "Check") return SystemCheckboxShadcn
  if (field.type === "Date") return SystemDatePicker
  if (field.type === "Select") return SystemSelect
  if (["Small Text", "Text", "Long Text"].includes(field.type)) return SystemTextarea
  if (field.type === "Link") return SystemLinkedRecordField
  return SystemFormControl
}
function componentOwnsLabel(field) {
  return !["Select", "Small Text", "Text", "Long Text"].includes(field.type)
}
function fieldProps(field, value) {
  if (field.type === "Check") return { label: field.label, disabled: field.read_only }
  if (field.type === "Date") return { label: field.label, disabled: field.read_only, clearable: !field.required, format: "YYYY-MM-DD" }
  if (field.type === "Select") return { options: field.options || [], disabled: field.read_only, size: "lg" }
  if (["Small Text", "Text", "Long Text"].includes(field.type)) return { placeholder: field.description || "", disabled: field.read_only, rows: 3 }
  if (field.type === "Link") return {
    label: field.label,
    description: field.description || "",
    options: field.link_options || [],
    disabled: field.read_only,
    placeholder: `Choose ${field.label.toLowerCase()}`,
    createLabel: `Add ${field.options}`,
    manageLabel: `Manage ${field.options}`,
  }
  return {
    label: field.label,
    description: field.description || "",
    type: inputType(field.type),
    disabled: field.read_only,
    required: field.required,
    min: field.non_negative ? 0 : undefined,
    step: field.type === "Currency" ? "0.01" : field.type === "Float" ? "0.1" : field.type === "Int" ? "1" : undefined,
    modelValue: value,
    size: "lg",
  }
}
function inputType(type) {
  if (["Int", "Float", "Currency"].includes(type)) return "number"
  if (type === "Date") return "date"
  if (type === "Email") return "email"
  if (type === "Phone") return "tel"
  return "text"
}
function setValue(target, name, value) {
  target[name] = value
  Object.keys(fieldErrors).filter((key) => key === name || key.endsWith(`.${name}`)).forEach((key) => delete fieldErrors[key])
}
function addTableRow(table) {
  tables[table.name] ||= []
  tables[table.name].push(Object.fromEntries(table.fields.map((field) => [field.name, field.default ?? null])))
}
function removeTableRow(table, index) {
  tables[table.name].splice(index, 1)
}
function openLinked(type, doctype) {
  emit("navigate", { mode: type, doctype })
}
async function save() {
  if (!validateContract()) return
  saving.value = true
  error.value = ""
  try {
    const topFields = contract.value.sections.flatMap((section) => section.fields)
    const normalizedTables = Object.fromEntries(contract.value.tables.map((table) => [
      table.name,
      (tables[table.name] || []).map((row) => normalizedValues(row, table.fields)),
    ]))
    const result = await auxiliaryRecordSystem.resources.save(props.doctype, props.mode === "edit" ? props.recordName : undefined, normalizedValues(values, topFields), normalizedTables)
    emit("saved", result)
    emit("navigate", { mode: "edit", doctype: props.doctype, name: result.name })
  } catch (caught) {
    error.value = caught?.message || "The record could not be saved."
  } finally {
    saving.value = false
  }
}
async function reviewDelete(names) {
  if (!names.length || deleteBusy.value) return
  deleteNames.value = [...names]
  deleteStage.value = DELETE_STAGE.REVIEW
  deletePlan.value = null
  deleteOutcome.value = DELETE_OUTCOME.DELETE
  clearReactive(deleteOutcomesByDoctype)
  deleteBusy.value = true
  error.value = ""
  try { await refreshDeleteResolution() }
  catch (caught) { error.value = caught?.message || "The deletion plan could not be prepared."; cancelDelete() }
  finally { deleteBusy.value = false }
}
async function chooseDeleteOutcome(outcome) {
  deleteOutcome.value = outcome
  await updateDeleteResolution()
}
async function chooseRelatedDeleteOutcome(doctype, outcome) {
  deleteOutcomesByDoctype[doctype] = outcome
  await updateDeleteResolution()
}
async function refreshDeleteResolution() {
  deletePlan.value = normalizeDeletionPlan(await auxiliaryRecordSystem.resources.planDelete(props.doctype, deleteNames.value, deleteOutcome.value, deleteOutcomesByDoctype))
}
async function updateDeleteResolution() {
  if (deleteBusy.value) return
  deleteBusy.value = true
  error.value = ""
  try { await refreshDeleteResolution() }
  catch (caught) { error.value = caught?.message || "The deletion choices could not be checked." }
  finally { deleteBusy.value = false }
}
function continueDelete() {
  if (deleteOutcomeAllowed.value) deleteStage.value = DELETE_STAGE.APPROVAL
}
async function approveDelete() {
  if (!deleteOutcomeAllowed.value || deleteBusy.value) return
  deleteBusy.value = true
  error.value = ""
  try {
    await auxiliaryRecordSystem.resources.deleteMany(finalDeleteRequest(props.doctype, deleteNames.value, deletePlan.value, deleteOutcome.value, deleteOutcomesByDoctype))
    const deletedCurrentRecord = props.mode === "edit" && deleteNames.value.includes(props.recordName)
    cancelDelete()
    if (deletedCurrentRecord) emit("navigate", { mode: "list", doctype: props.doctype })
    else await loadWorkspace(workspace.value?.page || 1)
  } catch (caught) { error.value = caught?.message || "The records could not be deleted." }
  finally { deleteBusy.value = false }
}
function cancelDelete() {
  deleteStage.value = DELETE_STAGE.CLOSED
  deletePlan.value = null
  deleteNames.value = []
  deleteOutcome.value = ""
  clearReactive(deleteOutcomesByDoctype)
}
function validateContract() {
  Object.keys(fieldErrors).forEach((key) => delete fieldErrors[key])
  for (const section of contract.value.sections) {
    for (const field of section.fields) validateField(field, values[field.name], field.name)
  }
  for (const table of contract.value.tables) {
    for (const [index, row] of (tables[table.name] || []).entries()) {
      for (const field of table.fields) validateField(field, row[field.name], `${table.name}.${index}.${field.name}`)
    }
  }
  if (Object.keys(fieldErrors).length) { error.value = "Check the marked required or numeric fields."; return false }
  return true
}
function validateField(field, value, key) {
  if (field.required && (value === null || value === undefined || String(value).trim() === "")) fieldErrors[key] = `${field.label} is required.`
  if (["Int", "Float", "Currency"].includes(field.type) && value !== "" && value !== null && value !== undefined) {
    const number = Number(value)
    if (!Number.isFinite(number)) fieldErrors[key] = `${field.label} must be a number.`
    else if (field.non_negative && number < 0) fieldErrors[key] = `${field.label} cannot be negative.`
  }
}
function normalizedValues(source, fields) {
  return Object.fromEntries(fields.map((field) => [field.name, coerceValue(field, source[field.name])]))
}
function coerceValue(field, value) {
  if (field.type === "Check") return value ? 1 : 0
  if (field.type === "Int") return value === "" || value === null ? null : Math.trunc(Number(value))
  if (["Float", "Currency"].includes(field.type)) return value === "" || value === null ? null : Number(value)
  return value
}

// endregion AUXILIARY RECORD WORKFLOW
</script>

<template>
  <section data-block="auxiliary-records" class="auxiliary-records workflow-block" aria-labelledby="auxiliary-records-heading">
    <header class="auxiliary-records__header">
      <div>
        <p class="eyebrow">Setup</p>
        <h1 id="auxiliary-records-heading">{{ pageTitle }}</h1>
        <p>{{ mode === "catalogue" ? "Create and maintain the records used by receipts, recipes, production, and stock counts." : "Changes become available to linked fields after saving." }}</p>
      </div>
      <SystemOperationalButton v-if="mode !== 'catalogue'" variant="subtle" @click="emit('navigate', { mode: 'catalogue' })">All setup records</SystemOperationalButton>
    </header>

    <div v-if="loading" class="state-message" role="status">Loading setup records...</div>
    <div v-else-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>

    <div v-else-if="mode === 'catalogue'" class="auxiliary-records__catalogue">
      <SystemCard v-for="form in catalogue" :key="form.doctype" class="auxiliary-records__card">
        <div><SystemBadge>SETUP</SystemBadge><h2>{{ form.label }}</h2><p>{{ form.description }}</p></div>
        <div class="button-row">
          <SystemOperationalButton variant="subtle" @click="emit('navigate', { mode: 'list', doctype: form.doctype })">Manage</SystemOperationalButton>
          <SystemOperationalButton v-if="form.can_create" variant="solid" theme="blue" @click="emit('navigate', { mode: 'create', doctype: form.doctype })">Add {{ form.singular_label }}</SystemOperationalButton>
        </div>
      </SystemCard>
    </div>

    <section v-else-if="mode === 'list'" class="auxiliary-records__list">
      <div class="section-heading"><div><p class="eyebrow">Manage records</p><h2>{{ selectedForm?.label }}</h2></div><SystemOperationalButton v-if="selectedForm?.can_create" theme="blue" variant="solid" @click="emit('navigate', { mode: 'create', doctype })">Add {{ selectedForm.singular_label }}</SystemOperationalButton></div>
      <div class="auxiliary-records__list-tools">
        <SystemFormControl v-model="search" label="Search records" placeholder="Search by name" @keyup.enter="applyListQuery" />
        <SystemDatePicker v-for="filter in availableFilters.filter((row) => row.type === 'date')" :key="filter.field" v-model="activeFilters[filter.field]" :label="filter.label" format="YYYY-MM-DD" clearable />
        <label v-for="filter in availableFilters.filter((row) => row.type !== 'date')" :key="filter.field" class="field-shell"><span>{{ filter.label }}</span><SystemSelect v-model="activeFilters[filter.field]" :options="filterOptions(filter)" placeholder="All" /></label>
        <SystemOperationalButton variant="subtle" @click="applyListQuery">Filter</SystemOperationalButton>
      </div>
      <div v-if="records.length && canDelete" class="auxiliary-records__selection-bar">
        <label><SystemCheckboxShadcn :model-value="allSelected" @update:model-value="toggleAll" /><span>Select all on this page</span></label>
        <span>{{ selectedNames.length }} selected</span>
        <SystemOperationalButton class="auxiliary-records__destructive-action" variant="outline" :disabled="!selectedNames.length" @click="reviewDelete(selectedNames)">Delete selected</SystemOperationalButton>
      </div>
      <p v-if="!records.length" class="state-message">No records yet.</p>
      <ul v-else>
        <li v-for="record in records" :key="record.name"><SystemCheckboxShadcn v-if="canDelete" :model-value="selectedNames.includes(record.name)" :aria-label="`Select ${record.title}`" @update:model-value="toggleSelected(record.name, $event)" /><span><strong>{{ record.title }}</strong><small>{{ record.name }}</small></span><SystemOperationalButton variant="subtle" @click="emit('navigate', { mode: 'edit', doctype, name: record.name })">Edit</SystemOperationalButton></li>
      </ul>
      <footer v-if="workspace && (workspace.page > 1 || workspace.has_next)" class="auxiliary-records__pagination"><span>Showing {{ records.length }} of {{ workspace.total }}</span><div class="button-row"><SystemOperationalButton variant="subtle" :disabled="workspace.page <= 1" @click="loadWorkspace(workspace.page - 1)">Previous</SystemOperationalButton><SystemOperationalButton variant="subtle" :disabled="!workspace.has_next" @click="loadWorkspace(workspace.page + 1)">Next</SystemOperationalButton></div></footer>
    </section>

    <form v-else-if="contract" class="auxiliary-records__form" @submit.prevent="save">
      <section v-for="section in contract.sections" :key="section.label" class="form-section">
        <div class="section-heading"><div><h2>{{ section.label }}</h2><p v-if="section.description">{{ section.description }}</p></div></div>
        <div class="field-grid">
          <template v-for="field in section.fields" :key="field.name">
            <component
              v-if="componentOwnsLabel(field)"
              :is="fieldComponent(field)"
              v-bind="fieldProps(field, values[field.name])"
              :model-value="values[field.name]"
              :error="fieldErrors[field.name]"
              @update:model-value="setValue(values, field.name, $event)"
              @create="openLinked('create', field.options)"
              @manage="openLinked('list', field.options)"
            />
            <label v-else class="field-shell">
              <span>{{ field.label }}<small v-if="field.required" aria-hidden="true"> *</small></span>
              <component
                :is="fieldComponent(field)"
                v-bind="fieldProps(field, values[field.name])"
                :model-value="values[field.name]"
                @update:model-value="setValue(values, field.name, $event)"
              />
              <small v-if="fieldErrors[field.name]" class="field-error">{{ fieldErrors[field.name] }}</small>
            </label>
          </template>
        </div>
      </section>

      <section v-for="table in contract.tables" :key="table.name" class="form-section auxiliary-records__table">
        <div class="section-heading"><div><h2>{{ table.label }}</h2><p>{{ table.description }}</p></div><SystemOperationalButton variant="subtle" @click="addTableRow(table)">Add row</SystemOperationalButton></div>
        <p v-if="!tables[table.name]?.length" class="state-message">No rows added.</p>
        <div v-for="(row, rowIndex) in tables[table.name]" :key="rowIndex" class="auxiliary-records__table-row">
          <span class="row-number">{{ rowIndex + 1 }}</span>
          <template v-for="field in table.fields" :key="field.name">
            <component
              v-if="componentOwnsLabel(field)"
              :is="fieldComponent(field)"
              v-bind="fieldProps(field, row[field.name])"
              :model-value="row[field.name]"
              :error="fieldErrors[`${table.name}.${rowIndex}.${field.name}`]"
              @update:model-value="setValue(row, field.name, $event)"
              @create="openLinked('create', field.options)"
              @manage="openLinked('list', field.options)"
            />
            <label v-else class="field-shell">
              <span>{{ field.label }}<small v-if="field.required" aria-hidden="true"> *</small></span>
              <component
                :is="fieldComponent(field)"
                v-bind="fieldProps(field, row[field.name])"
                :model-value="row[field.name]"
                @update:model-value="setValue(row, field.name, $event)"
              />
              <small v-if="fieldErrors[`${table.name}.${rowIndex}.${field.name}`]" class="field-error">{{ fieldErrors[`${table.name}.${rowIndex}.${field.name}`] }}</small>
            </label>
          </template>
          <SystemOperationalButton variant="ghost" @click="removeTableRow(table, rowIndex)">Remove</SystemOperationalButton>
        </div>
      </section>

      <footer class="posting-bar"><div><SystemBadge>{{ mode === "create" ? "NEW RECORD" : "EDITING" }}</SystemBadge><p>Required fields are checked by Frappe before this record is saved.</p></div><div class="button-row"><SystemOperationalButton v-if="mode === 'edit' && selectedForm?.can_delete" class="auxiliary-records__destructive-action" type="button" variant="outline" @click="reviewDelete([recordName])">Delete</SystemOperationalButton><SystemOperationalButton type="submit" theme="blue" variant="solid" size="lg" :loading="saving" loading-text="Saving">Save record</SystemOperationalButton></div></footer>
    </form>

    <SystemDialog v-model:open="deleteOpen">
      <SystemDialogContent class="auxiliary-records__delete-dialog">
        <SystemDialogHeader><p class="eyebrow">{{ deleteStage === DELETE_STAGE.APPROVAL ? 'Final approval' : 'Deletion review' }}</p><SystemDialogTitle>{{ deleteStage === DELETE_STAGE.APPROVAL ? `Apply this deletion plan to ${deleteRecordCount} record${deleteRecordCount === 1 ? '' : 's'}?` : `Review ${deleteNames.length} selected record${deleteNames.length === 1 ? '' : 's'}` }}</SystemDialogTitle><SystemDialogDescription>{{ deleteStage === DELETE_STAGE.APPROVAL ? `${deletePlan.resolution.deleteCount} records will be deleted, ${deletePlan.resolution.unlinkCount} links cleared, and ${deletePlan.resolution.archiveCount} records hidden but preserved for history.` : 'Choose the default action, then override it for any related record type below.' }}</SystemDialogDescription></SystemDialogHeader>
        <div class="auxiliary-records__delete-body">
          <div v-if="deleteBusy && !deletePlan" class="state-message" role="status">Checking every connected record...</div>
          <template v-else-if="deletePlan">
            <section class="auxiliary-records__delete-summary"><strong>Selected records</strong><ul><li v-for="row in deletePlan.roots" :key="`${row.doctype}:${row.name}`">{{ row.doctype }}: {{ row.title || row.name }}</li></ul></section>
            <section v-if="deletePlan.dependencies.length" class="auxiliary-records__delete-summary"><strong>Related managed records</strong><ul><li v-for="row in deletePlan.dependencies" :key="`${row.doctype}:${row.name}`">{{ row.doctype }}: {{ row.title || row.name }}</li></ul></section>
            <section v-if="deleteConnections.length" class="auxiliary-records__delete-summary"><strong>Connections and linking fields</strong><ul><li v-for="row in deleteConnections" :key="`${row.doctype}:${row.name}`"><span>{{ row.doctype }}: {{ row.title || row.name }}</span><small>{{ row.linkedBy.map((link) => `${link.doctype}.${link.fieldLabel}`).join(', ') }}</small></li></ul></section>
            <section v-if="deleteRelatedTypes.length" class="auxiliary-records__delete-summary auxiliary-records__delete-type-choices"><strong>Related record choices</strong><p>Each row inherits the default until you choose a different action.</p><div v-for="row in deleteRelatedTypes" :key="row.doctype" class="auxiliary-records__delete-type-row"><div><strong>{{ row.doctype }}</strong><small>{{ row.recordCount }} records · {{ row.linkCount }} links<span v-if="row.historyCount"> · {{ row.historyCount }} preserved for history</span></small></div><SystemSelect v-if="row.configurable" :model-value="deleteOutcomesByDoctype[row.doctype] || deleteOutcome" :options="[{ label: 'Delete related records', value: DELETE_OUTCOME.DELETE }, { label: 'Unlink and keep records', value: DELETE_OUTCOME.UNLINK }]" :disabled="deleteBusy" @update:model-value="chooseRelatedDeleteOutcome(row.doctype, $event)" /><small v-else>Protected history stays unchanged.</small></div></section>
            <section v-if="deletePlan.resolution.archiveCount || deletePlan.resolution.preserveCount" class="auxiliary-records__delete-summary"><strong>Preserved history</strong><p>{{ deletePlan.resolution.archiveCount }} selected or managed records will be hidden from setup but retained for immutable references. {{ deletePlan.resolution.preserveCount }} history records remain unchanged.</p></section>
            <section v-if="deleteOutcomeBlockers.length" class="state-message state-message--error" role="alert"><strong>{{ deleteOutcome ? 'This option is blocked' : 'Deletion restrictions' }}</strong><ul><li v-for="row in deleteOutcomeBlockers" :key="`${row.doctype}:${row.name}:${row.reason}`">{{ row.doctype }} {{ row.title || row.name }}: {{ row.reason }}</li></ul></section>
          </template>
        </div>
        <div v-if="deleteStage === DELETE_STAGE.REVIEW && deletePlan" class="auxiliary-records__delete-outcomes" aria-label="Default related record action"><button type="button" :aria-pressed="deleteOutcome === DELETE_OUTCOME.UNLINK" @click="chooseDeleteOutcome(DELETE_OUTCOME.UNLINK)"><strong>Default to unlink</strong><small>Keep mutable related records and clear optional links.</small></button><button class="auxiliary-records__delete-outcome--danger" type="button" :aria-pressed="deleteOutcome === DELETE_OUTCOME.DELETE" @click="chooseDeleteOutcome(DELETE_OUTCOME.DELETE)"><strong>Default to delete</strong><small>Delete mutable related records unless a row overrides this choice.</small></button></div>
        <SystemDialogFooter class="auxiliary-records__delete-actions"><SystemOperationalButton variant="subtle" :disabled="deleteBusy" @click="cancelDelete">Cancel</SystemOperationalButton><SystemOperationalButton v-if="deleteStage === DELETE_STAGE.REVIEW" class="auxiliary-records__destructive-action" variant="outline" :disabled="deleteBusy || !deleteOutcomeAllowed" @click="continueDelete">Continue to final approval</SystemOperationalButton><SystemOperationalButton v-else class="auxiliary-records__destructive-action auxiliary-records__destructive-action--solid" variant="solid" :loading="deleteBusy" loading-text="Applying plan" :disabled="!deleteOutcomeAllowed" @click="approveDelete">Approve deletion plan</SystemOperationalButton></SystemDialogFooter>
      </SystemDialogContent>
    </SystemDialog>
  </section>
</template>

<style scoped>
.auxiliary-records{width:min(100%,90rem);min-height:calc(100vh - 8rem);margin-inline:auto;padding:var(--spacing-l) var(--spacing-m) var(--spacing-xl-2xl)}.auxiliary-records__header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-m);margin-bottom:var(--spacing-m)}.auxiliary-records__header h1{margin:var(--spacing-3xs) 0;font-size:var(--font-size-2);font-weight:var(--font-weight-700)}.auxiliary-records__header p{max-width:48rem;margin:0;color:var(--theme-text-muted)}.auxiliary-records__catalogue{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-s)}.auxiliary-records__card{display:flex;flex-direction:column;justify-content:space-between;gap:var(--spacing-m);min-height:13rem;padding:var(--spacing-m)!important;background:var(--theme-surface)!important}.auxiliary-records__card h2{margin:var(--spacing-xs) 0 var(--spacing-2xs);font-size:var(--font-size-1);font-weight:var(--font-weight-650)}.auxiliary-records__card p{margin:0;color:var(--theme-text-muted)}.auxiliary-records__list{padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface)}.auxiliary-records__list-tools{display:grid;grid-template-columns:minmax(14rem,1.5fr) repeat(auto-fit,minmax(10rem,1fr)) auto;align-items:end;gap:var(--spacing-xs);margin-bottom:var(--spacing-s)}.auxiliary-records__selection-bar{display:flex;align-items:center;gap:var(--spacing-s);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-secondary)}.auxiliary-records__selection-bar label{display:flex;align-items:center;gap:var(--spacing-2xs);margin-right:auto}.auxiliary-records__destructive-action{border-color:color-mix(in oklch,var(--theme-error) 52%,var(--theme-border))!important;color:var(--theme-error)!important}.auxiliary-records__destructive-action--solid{background:var(--theme-error)!important;color:var(--theme-error-foreground)!important}.auxiliary-records__list ul{display:grid;margin:0;padding:0;list-style:none}.auxiliary-records__list li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:var(--spacing-s);min-height:3.75rem;padding:var(--spacing-xs);border-bottom:var(--border-width-1) solid var(--theme-border)}.auxiliary-records__list li:last-child{border-bottom:0}.auxiliary-records__list span,.auxiliary-records__list small{display:block}.auxiliary-records__list small{margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.auxiliary-records__pagination{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding-top:var(--spacing-s)}.auxiliary-records__table-row{display:grid;grid-template-columns:auto repeat(auto-fit,minmax(min(100%,12rem),1fr)) auto;gap:var(--spacing-xs);align-items:end;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-canvas)}.auxiliary-records__table-row>*{min-width:0}.auxiliary-records__delete-dialog{width:min(calc(100vw - 2rem),42rem);max-height:min(82vh,50rem);overflow:auto;background:var(--theme-surface-raised);color:var(--theme-text)}.auxiliary-records__delete-dialog ul{display:grid;gap:var(--spacing-3xs);margin:var(--spacing-xs) 0 0;padding-left:var(--spacing-m)}.auxiliary-records__delete-summary{padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-secondary)}.auxiliary-records__delete-summary small{display:block;color:var(--theme-text-muted)}.auxiliary-records__delete-actions{display:flex;justify-content:flex-end;gap:var(--spacing-xs)}@media(max-width:64rem){.auxiliary-records__catalogue{grid-template-columns:repeat(2,minmax(0,1fr))}.auxiliary-records__list-tools{grid-template-columns:repeat(2,minmax(0,1fr))}.auxiliary-records__table-row{grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr))}.auxiliary-records__table-row>.row-number{grid-column:1/-1}.auxiliary-records__table-row>*:last-child{justify-self:start}}@media(max-width:44rem){.auxiliary-records{padding:var(--spacing-m) var(--spacing-s) var(--spacing-xl)}.auxiliary-records__header{flex-direction:column}.auxiliary-records__catalogue,.auxiliary-records__list-tools{grid-template-columns:1fr}.auxiliary-records__selection-bar,.auxiliary-records__pagination{align-items:stretch;flex-direction:column}.auxiliary-records__selection-bar label{margin-right:0}.auxiliary-records__table-row{grid-template-columns:1fr}.auxiliary-records__table-row>.row-number{position:static}.auxiliary-records__list li{grid-template-columns:auto minmax(0,1fr)}.auxiliary-records__list li>*:last-child{grid-column:2}.auxiliary-records__delete-actions{align-items:stretch;flex-direction:column-reverse}.auxiliary-records__delete-actions>*{width:100%}}
:global(.auxiliary-records__delete-dialog){box-sizing:border-box!important;display:grid!important;width:min(calc(100vw - 2rem),42rem)!important;height:min(50rem,calc(100dvh - 2rem))!important;max-height:calc(100dvh - 2rem)!important;min-height:0!important;grid-template-rows:auto minmax(0,1fr) auto auto!important;overflow:hidden!important}
.auxiliary-records__delete-body{display:grid;min-width:0;min-height:0;gap:var(--spacing-xs);overflow-x:hidden;overflow-y:scroll;padding-right:var(--spacing-xs);overscroll-behavior:contain;scrollbar-gutter:stable;scrollbar-color:var(--theme-border) transparent;scrollbar-width:thin}
.auxiliary-records__delete-body::-webkit-scrollbar{width:.55rem}.auxiliary-records__delete-body::-webkit-scrollbar-track{background:transparent}.auxiliary-records__delete-body::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background:var(--theme-border);background-clip:padding-box}
.auxiliary-records__delete-type-choices{display:grid;gap:var(--spacing-xs)}
.auxiliary-records__delete-type-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(11rem,15rem);align-items:center;gap:var(--spacing-xs);padding-top:var(--spacing-xs);border-top:var(--border-width-1) solid var(--theme-border)}
.auxiliary-records__delete-type-row>*{min-width:0}
.auxiliary-records__delete-outcomes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-xs)}
.auxiliary-records__delete-outcomes button{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface);color:var(--theme-text);text-align:left}
.auxiliary-records__delete-outcomes button[aria-pressed=true]{border-color:var(--theme-primary);box-shadow:0 0 0 2px color-mix(in oklch,var(--theme-primary) 18%,transparent)}
.auxiliary-records__delete-outcomes button:disabled{opacity:.5}.auxiliary-records__delete-outcomes small{color:var(--theme-text-muted)}
.auxiliary-records__delete-outcome--danger{border-color:color-mix(in oklch,var(--theme-error) 42%,var(--theme-border))!important}
@media(max-width:44rem){.auxiliary-records__delete-type-row,.auxiliary-records__delete-outcomes{grid-template-columns:1fr}}
</style>
