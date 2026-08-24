<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import {
  SystemBadge,
  SystemCard,
  SystemCheckbox,
  SystemDatePicker,
  SystemFormControl,
  SystemLinkedRecordField,
  SystemOperationalButton,
  SystemSelect,
  SystemTextarea,
} from "@/desyium"
import {
  getAuxiliaryCatalogue,
  getAuxiliaryRecord,
  getAuxiliaryRecordList,
  saveAuxiliaryRecord,
} from "@/resources/api"

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
const contract = ref(null)
const values = reactive({})
const tables = reactive({})
const loading = ref(true)
const saving = ref(false)
const error = ref("")
const fieldErrors = reactive({})
const selectedForm = computed(() => catalogue.value.find((row) => row.doctype === props.doctype))
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
    catalogue.value = await getAuxiliaryCatalogue()
    records.value = []
    contract.value = null
    clearReactive(values)
    clearReactive(tables)
    if (props.mode === "list" && props.doctype) {
      records.value = await getAuxiliaryRecordList(props.doctype)
    } else if (["create", "edit"].includes(props.mode) && props.doctype) {
      const result = await getAuxiliaryRecord(props.doctype, props.mode === "edit" ? props.recordName : undefined)
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

function clearReactive(target) {
  Object.keys(target).forEach((key) => delete target[key])
}
function fieldComponent(field) {
  if (field.type === "Check") return SystemCheckbox
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
    const result = await saveAuxiliaryRecord(props.doctype, props.mode === "edit" ? props.recordName : undefined, normalizedValues(values, topFields), normalizedTables)
    emit("saved", result)
    emit("navigate", { mode: "edit", doctype: props.doctype, name: result.name })
  } catch (caught) {
    error.value = caught?.message || "The record could not be saved."
  } finally {
    saving.value = false
  }
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
      <p v-if="!records.length" class="state-message">No records yet.</p>
      <ul v-else>
        <li v-for="record in records" :key="record.name"><span><strong>{{ record.label }}</strong><small>{{ record.name }}</small></span><SystemOperationalButton variant="subtle" @click="emit('navigate', { mode: 'edit', doctype, name: record.name })">Edit</SystemOperationalButton></li>
      </ul>
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

      <footer class="posting-bar"><div><SystemBadge>{{ mode === "create" ? "NEW RECORD" : "EDITING" }}</SystemBadge><p>Required fields are checked by Frappe before this record is saved.</p></div><SystemOperationalButton type="submit" theme="blue" variant="solid" size="lg" :loading="saving" loading-text="Saving">Save record</SystemOperationalButton></footer>
    </form>
  </section>
</template>

<style scoped>
.auxiliary-records{width:min(100%,90rem);min-height:calc(100vh - 8rem);margin-inline:auto;padding:var(--spacing-l) var(--spacing-m) var(--spacing-xl-2xl)}.auxiliary-records__header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-m);margin-bottom:var(--spacing-m)}.auxiliary-records__header h1{margin:var(--spacing-3xs) 0;font-size:var(--font-size-2);font-weight:var(--font-weight-700)}.auxiliary-records__header p{max-width:48rem;margin:0;color:var(--theme-text-muted)}.auxiliary-records__catalogue{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-s)}.auxiliary-records__card{display:flex;flex-direction:column;justify-content:space-between;gap:var(--spacing-m);min-height:13rem;padding:var(--spacing-m)!important;background:var(--theme-surface)!important}.auxiliary-records__card h2{margin:var(--spacing-xs) 0 var(--spacing-2xs);font-size:var(--font-size-1);font-weight:var(--font-weight-650)}.auxiliary-records__card p{margin:0;color:var(--theme-text-muted)}.auxiliary-records__list{padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface)}.auxiliary-records__list ul{display:grid;margin:0;padding:0;list-style:none}.auxiliary-records__list li{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);min-height:3.75rem;padding:var(--spacing-xs);border-bottom:var(--border-width-1) solid var(--theme-border)}.auxiliary-records__list li:last-child{border-bottom:0}.auxiliary-records__list span,.auxiliary-records__list small{display:block}.auxiliary-records__list small{margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.auxiliary-records__table-row{display:grid;grid-template-columns:auto repeat(auto-fit,minmax(min(100%,12rem),1fr)) auto;gap:var(--spacing-xs);align-items:end;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-canvas)}.auxiliary-records__table-row>*{min-width:0}@media(max-width:64rem){.auxiliary-records__catalogue{grid-template-columns:repeat(2,minmax(0,1fr))}.auxiliary-records__table-row{grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr))}.auxiliary-records__table-row>.row-number{grid-column:1/-1}.auxiliary-records__table-row>*:last-child{justify-self:start}}@media(max-width:44rem){.auxiliary-records{padding:var(--spacing-m) var(--spacing-s) var(--spacing-xl)}.auxiliary-records__header{flex-direction:column}.auxiliary-records__catalogue{grid-template-columns:1fr}.auxiliary-records__table-row{grid-template-columns:1fr}.auxiliary-records__table-row>.row-number{position:static}.auxiliary-records__list li{align-items:flex-start;flex-direction:column}}
</style>
