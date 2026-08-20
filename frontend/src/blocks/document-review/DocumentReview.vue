<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemCheckbox, SystemFileUploader, SystemFormControl, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { applyDocumentMeasurements, createDocumentExtractionDraft, reviewDocumentExtraction } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const form = reactive({ source_file: "", document_type: "Remaining Stock Sheet", production_run: "", default_location: "Ingredients", raw_text: "" })
const draft = ref(null)
const busy = ref(false)
const error = ref("")
const typeOptions = [{ label: "Remaining stock sheet", value: "Remaining Stock Sheet" }, { label: "Usage sheet", value: "Usage Sheet" }, { label: "Stock audit", value: "Stock Audit" }]
const locationOptions = computed(() => (props.snapshot?.options?.locations || []).map(value => ({ label: value, value })))
const runOptions = computed(() => (props.snapshot?.recent_runs || []).filter(run => !run.docstatus).map(run => ({ label: `${run.production_date}: ${run.finished_item}`, value: run.name })))
const itemOptions = computed(() => (props.inventory?.items || []).map(item => ({ label: item.item_name, value: item.item_code })))
function onUpload(file) { form.source_file = file.file_url }
async function extract() { busy.value = true; error.value = ""; try { draft.value = await createDocumentExtractionDraft({ ...form, business_name: "BulkBite" }) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
async function review() { busy.value = true; error.value = ""; try { draft.value = await reviewDocumentExtraction(draft.value.name, draft.value.rows.filter(row => row.accepted).map(row => ({ ...row, accepted: 1 }))) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
async function applyRows() { busy.value = true; error.value = ""; try { const result = await applyDocumentMeasurements(draft.value.name); draft.value.status = "Applied"; draft.value.applied_reference = result.name; emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false } }
</script>

<template>
  <section data-block="document-review" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Documents</p><h1>Worker sheet review</h1><p>The document and supplied OCR text produce suggestions only. A person must check the rows before anything is applied.</p></div><div class="step-rail"><span class="is-current">1 Source</span><span>2 Review</span><span>3 Apply</span></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section v-if="!draft" class="form-section">
      <div class="field-grid">
        <label class="field-shell"><span>Document type</span><SystemSelect v-model="form.document_type" :options="typeOptions" size="lg" /></label>
        <label class="field-shell"><span>Default location</span><SystemSelect v-model="form.default_location" :options="locationOptions" size="lg" /></label>
        <label v-if="form.document_type !== 'Stock Audit'" class="field-shell field-shell--wide"><span>Production draft</span><SystemSelect v-model="form.production_run" :options="runOptions" placeholder="Choose draft run" size="lg" /></label>
      </div>
      <SystemFileUploader :upload-args="{ private: true }" @success="onUpload"><template #default="upload"><SystemOperationalButton variant="outline" :loading="upload.uploading" @click="upload.openFileSelector">{{ form.source_file ? "Replace worker sheet" : "Upload worker sheet" }}</SystemOperationalButton></template></SystemFileUploader>
      <p class="field-note">{{ form.source_file || "Private source document required." }}</p>
      <label class="field-shell"><span>OCR or transcribed text</span><SystemTextarea v-model="form.raw_text" :rows="9" placeholder="Paste one measurement per line, for example: Chicken breast, 2.4 kg" /></label>
      <p class="safety-note">This interface does not inspect the uploaded image. It parses only the text you supply and holds the result for review.</p>
      <SystemOperationalButton theme="blue" variant="solid" size="lg" :loading="busy" @click="extract">Create review draft</SystemOperationalButton>
    </section>
    <section v-else class="data-section">
      <div class="section-heading"><div><p class="eyebrow">Human review</p><h2>Proposed measurements</h2></div><SystemBadge>{{ draft.status }}</SystemBadge></div>
      <p v-if="draft.warnings" class="safety-note">{{ draft.warnings }}</p>
      <div class="measurement-list">
        <article v-for="(row, index) in draft.rows" :key="index" class="measurement-row measurement-row--review">
          <div><strong>{{ row.source_line || row.proposed_item_name }}</strong><small>{{ Number(row.confidence || 0).toFixed(0) }}% match · {{ row.warning || "No warning" }}</small></div>
          <label class="field-shell"><span>Matched item</span><SystemSelect v-model="row.item_code" :options="itemOptions" size="lg" /></label>
          <SystemFormControl v-model="row.qty" type="number" label="Quantity" min="0" step="0.001" size="lg" />
          <SystemCheckbox v-model="row.accepted" label="Accept row" />
        </article>
      </div>
      <footer class="posting-bar">
        <p v-if="draft.applied_reference">Applied to {{ draft.applied_reference }}</p>
        <SystemOperationalButton v-if="draft.status !== 'Reviewed' && draft.status !== 'Applied'" variant="outline" size="lg" :loading="busy" @click="review">Confirm reviewed rows</SystemOperationalButton>
        <SystemOperationalButton v-if="draft.status === 'Reviewed'" theme="blue" variant="solid" size="lg" :loading="busy" @click="applyRows">Apply approved rows</SystemOperationalButton>
      </footer>
    </section>
  </section>
</template>
