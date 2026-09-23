<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemFormControl, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { getAdvertisingRequestBrief, saveAdvertisingRequest, startAdvertisingRequest } from "@/resources/api"

const props = defineProps({ workspace: { type: Object, required: true }, busy: { type: Boolean, default: false } })
const emit = defineEmits(["saved", "navigate"])
const editing = ref(false)
const saving = ref(false)
const error = ref("")
const form = reactive(emptyForm())
const options = computed(() => props.workspace.options || {})
const choice = (values, emptyLabel = "None") => (values || []).map(value => ({ label: value || emptyLabel, value }))
const physical = computed(() => form.primary_channel === "Physical poster")

function emptyForm() { return { name: "", request_title: "", status: "New", priority: "Normal", request_date: new Date().toISOString().slice(0, 10), due_date: "", project_type: "Residence", residence: "Goldfields", primary_channel: "Physical poster", formats: "poster-a4-print-600", meal: "", need: "", pain_point: "", exact_wording: "", qr_destination: "", digital_destination: "", reviewer: "", notes: "" } }
function open(values = null) { Object.assign(form, emptyForm(), values || {}); editing.value = true; error.value = "" }
async function save() {
  if (!form.request_title.trim() || !form.need.trim()) { error.value = "Add a title and describe what you need."; return }
  if (form.project_type === "Residence" && !form.residence) { error.value = "Choose the residence."; return }
  saving.value = true; error.value = ""
  try { const saved = await saveAdvertisingRequest({ ...form, residence: form.project_type === "Residence" ? form.residence : "", qr_destination: physical.value ? form.qr_destination : "" }); editing.value = false; emit("saved", `${saved.name} is ready for production.`) }
  catch (exception) { error.value = exception.message }
  finally { saving.value = false }
}
async function start(item) {
  saving.value = true; error.value = ""
  try { const campaign = await startAdvertisingRequest(item.name); emit("saved", `${campaign.name} started from ${item.name}.`); emit("navigate", "campaigns") }
  catch (exception) { error.value = exception.message }
  finally { saving.value = false }
}
async function copyBrief(item) {
  saving.value = true; error.value = ""
  try { const result = await getAdvertisingRequestBrief(item.name); await navigator.clipboard.writeText(result.brief); emit("saved", `${item.name} Codex brief copied.`) }
  catch (exception) { error.value = exception.message }
  finally { saving.value = false }
}
</script>

<template>
  <section class="advertising-section" aria-labelledby="advertising-requests-heading">
    <header class="advertising-section-header"><div><p class="advertising-eyebrow">Intake</p><h2 id="advertising-requests-heading">Requests</h2><p>Describe the outcome in plain language. The request preserves channel rules, food truth, destinations, and review ownership.</p></div><SystemOperationalButton variant="solid" @click="open()">New request</SystemOperationalButton></header>
    <div v-if="error" class="advertising-message advertising-message--error" role="alert">{{ error }}</div>
    <article v-if="editing" class="advertising-card">
      <header><h3>{{ form.name ? 'Edit request' : 'What do you need?' }}</h3><p>This becomes the reusable factory handoff. Keep one central pain point and name the meal when the creative must show food.</p></header>
      <div class="advertising-form-grid">
        <SystemFormControl v-model="form.request_title" label="Request title" placeholder="Goldfields exam-week posters" />
        <label class="advertising-field"><span>Priority</span><SystemSelect v-model="form.priority" :options="choice(options.priorities)" /></label>
        <SystemFormControl v-model="form.due_date" type="date" label="Needed by" />
        <label class="advertising-field"><span>Project group</span><SystemSelect v-model="form.project_type" :options="choice(options.project_types)" /></label>
        <label v-if="form.project_type === 'Residence'" class="advertising-field"><span>Residence</span><SystemSelect v-model="form.residence" :options="choice(options.residences, 'No residence')" /></label>
        <label class="advertising-field"><span>Primary channel</span><SystemSelect v-model="form.primary_channel" :options="choice(options.channels)" /></label>
        <SystemFormControl v-model="form.formats" label="Required formats" placeholder="poster-a4-print-600, instagram-feed" />
        <SystemFormControl v-model="form.meal" label="Meal truth lock" placeholder="Beef Bolognese Pasta — spaghetti, beef tomato sauce" />
        <label class="advertising-field advertising-field--wide"><span>What do you need?</span><SystemTextarea v-model="form.need" :rows="4" placeholder="The outcome, audience, timing, quantity, and anything that must be delivered." /></label>
        <label class="advertising-field advertising-field--wide"><span>One pain point or thought</span><SystemTextarea v-model="form.pain_point" :rows="2" placeholder="Dinner decisions during exam week." /></label>
        <label class="advertising-field advertising-field--wide"><span>Exact wording that must appear</span><SystemTextarea v-model="form.exact_wording" :rows="2" /></label>
        <SystemFormControl v-if="physical" v-model="form.qr_destination" class="advertising-field--wide" type="url" label="Exact registered poster QR destination" placeholder="https://bulkbite.co.za/qr/..." />
        <SystemFormControl v-else v-model="form.digital_destination" class="advertising-field--wide" type="url" label="Clickable digital destination" placeholder="https://bulkbite.co.za/..." />
        <SystemFormControl v-model="form.reviewer" label="Reviewer" placeholder="Faith or French" />
        <label class="advertising-field advertising-field--wide"><span>Notes and holds</span><SystemTextarea v-model="form.notes" :rows="2" /></label>
      </div>
      <div class="advertising-actions"><SystemOperationalButton variant="outline" @click="editing = false">Cancel</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="saving" @click="save">Save request</SystemOperationalButton></div>
    </article>
    <div v-else class="advertising-list">
      <article v-for="item in workspace.requests" :key="item.name" class="advertising-card">
        <header class="advertising-section-header"><div><p class="advertising-eyebrow">{{ item.name }}</p><h3>{{ item.request_title }}</h3><p>{{ item.need }}</p></div><div class="advertising-actions"><SystemBadge>{{ item.priority }}</SystemBadge><SystemBadge>{{ item.status }}</SystemBadge></div></header>
        <dl class="advertising-data"><div><dt>Scope</dt><dd>{{ item.residence || item.project_type }}</dd></div><div><dt>Channel</dt><dd>{{ item.primary_channel }}</dd></div><div><dt>Due</dt><dd>{{ item.due_date || 'Not set' }}</dd></div></dl>
        <div class="advertising-actions"><SystemOperationalButton variant="ghost" @click="open(item)">Edit</SystemOperationalButton><SystemOperationalButton variant="outline" :loading="saving" @click="copyBrief(item)">Copy Codex brief</SystemOperationalButton><SystemOperationalButton v-if="workspace.can_manage && !item.campaign" variant="solid" :loading="saving" @click="start(item)">Start production</SystemOperationalButton><SystemOperationalButton v-if="item.campaign" variant="outline" @click="emit('navigate', 'campaigns')">Open {{ item.campaign }}</SystemOperationalButton></div>
      </article>
      <p v-if="!workspace.requests.length" class="advertising-empty">No requests yet. Add one to start a fast, consistent handoff.</p>
    </div>
  </section>
</template>
