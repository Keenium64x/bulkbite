<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemCheckbox, SystemFileUploader, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { applyDocumentMeasurements, createDocumentExtractionDraft, reviewDocumentExtraction } from "@/resources/api"
import { useRouter } from "vue-router"

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const router = useRouter()
const form = reactive({ source_file: "", document_type: "Remaining Stock Sheet", production_run: "", default_location: "Ingredients", raw_text: "" })
const draft = ref(null)
const busy = ref(false)
const error = ref("")
const typeOptions = [{ label: "Remaining stock sheet", value: "Remaining Stock Sheet" }, { label: "Usage sheet", value: "Usage Sheet" }, { label: "Stock audit", value: "Stock Audit" }]
const locationOptions = computed(() => (props.snapshot?.options?.locations || []).map(value => ({ label: value, value })))
const runOptions = computed(() => (props.snapshot?.recent_runs || []).filter(run => !run.docstatus).map(run => ({ label: `${run.production_date}: ${run.finished_item}`, value: run.name })))
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
function onUpload(file) { form.source_file = file.file_url }
async function extract() {
  error.value = ""
  if (!form.source_file) { error.value = "Upload the private worker sheet."; return }
  if (!form.default_location) { error.value = "Choose the default stock location."; return }
  if (form.document_type !== "Stock Audit" && !form.production_run) { error.value = "Choose the production draft this sheet belongs to."; return }
  busy.value = true
  try { draft.value = await createDocumentExtractionDraft({ ...form, business_name: "BulkBite" }) } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
async function review() {
  error.value = ""
  if (!draft.value.rows.some((row) => row.accepted)) { error.value = "Approve at least one measurement row."; return }
  busy.value = true
  try { draft.value = await reviewDocumentExtraction(draft.value.name, draft.value.rows.map(row => ({ ...row, qty: Number(row.qty), accepted: row.accepted ? 1 : 0 }))) } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
async function applyRows() { busy.value = true; error.value = ""; try { const result = await applyDocumentMeasurements(draft.value.name); draft.value.status = "Applied"; draft.value.applied_reference = result.name; emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false } }
</script>

<template>
  <section data-block="document-review" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Worker sheets</p><h1>Turn a written sheet into a draft</h1><p>Upload the evidence, let the parser extract measurements, and check every suggested row before applying it.</p></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section v-if="!draft" class="form-section"><div class="section-heading"><div><p class="eyebrow">Upload</p><h2>Add the worker sheet</h2><p>The private file stays as evidence. Local extraction runs first, then configured AI can strengthen the structured suggestions.</p></div></div>
      <div class="field-grid">
        <label class="field-shell"><span>Document type</span><SystemSelect v-model="form.document_type" :options="typeOptions" size="lg" /></label>
        <SystemLinkedRecordField v-model="form.default_location" label="Default location" :options="locationOptions" create-label="Add location" manage-label="Manage locations" @create="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Location' } })" @manage="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Location' } })" />
        <label v-if="form.document_type !== 'Stock Audit'" class="field-shell field-shell--wide"><span>Production draft</span><SystemSelect v-model="form.production_run" :options="runOptions" placeholder="Choose draft run" size="lg" /></label>
      </div>
      <SystemFileUploader :upload-args="{ private: true }" @success="onUpload"><template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading" @click="upload.openFileSelector">{{ form.source_file ? "Replace worker sheet" : "Upload worker sheet" }}</SystemOperationalButton></template></SystemFileUploader>
      <p class="field-note">{{ form.source_file || "Private source document required." }}</p>
      <label class="field-shell"><span>Optional transcription or correction</span><SystemTextarea v-model="form.raw_text" :rows="6" placeholder="Leave blank to use extraction, or paste one measurement per line, for example: Chicken breast, 2.4 kg" /></label>
      <p class="safety-note">Extraction creates suggestions only. No stock changes until a person reviews the rows and applies them.</p>
      <SystemOperationalButton variant="solid" size="lg" :loading="busy" @click="extract">Extract measurements</SystemOperationalButton>
    </section>
    <section v-else class="data-section">
      <div class="section-heading"><div><p class="eyebrow">Review</p><h2>Check every suggestion</h2><p>Fix the item or quantity, then accept only rows that match the written sheet.</p><small>{{ draft.text_provider }} · {{ draft.parser_mode }}</small></div><SystemBadge>{{ draft.status }}</SystemBadge></div>
      <p v-if="draft.warnings" class="safety-note">{{ draft.warnings }}</p>
      <div class="measurement-list">
        <article v-for="(row, index) in draft.rows" :key="index" class="measurement-row measurement-row--review">
          <div><strong>{{ row.source_quote || row.source_line || row.proposed_item_name }}</strong><small>{{ row.source_page ? `Page ${row.source_page} · ` : "" }}{{ Number(row.confidence || 0).toFixed(0) }}% match · {{ row.warning || "No warning" }}</small></div>
          <SystemLinkedRecordField v-model="row.item_code" label="Matched item" :options="itemOptions" create-label="Add item" manage-label="Manage items" @create="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Item' } })" @manage="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Item' } })" />
          <SystemFormControl v-model="row.qty" type="number" label="Quantity" min="0" step="0.1" size="lg" />
          <SystemCheckbox v-model="row.accepted" label="Accept row" />
        </article>
      </div>
      <footer class="posting-bar">
        <p v-if="draft.applied_reference">Applied to {{ draft.applied_reference }}</p>
        <SystemOperationalButton v-if="draft.status !== 'Reviewed' && draft.status !== 'Applied'" variant="outline" size="lg" :loading="busy" @click="review">Confirm reviewed rows</SystemOperationalButton>
        <SystemOperationalButton v-if="draft.status === 'Reviewed'" variant="solid" size="lg" :loading="busy" @click="applyRows">Apply approved rows</SystemOperationalButton>
      </footer>
    </section>
  </section>
</template>
