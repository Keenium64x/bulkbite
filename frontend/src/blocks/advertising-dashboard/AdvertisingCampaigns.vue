<script setup>
import { computed, reactive, ref } from "vue"
import { SystemBadge, SystemFormControl, SystemMultiFileUploader, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { saveAdvertisingCampaign } from "@/resources/api"

const props = defineProps({ workspace: { type: Object, required: true }, busy: { type: Boolean, default: false } })
const emit = defineEmits(["saved"])
const selectedName = ref("")
const editing = ref(false)
const saving = ref(false)
const error = ref("")
const files = ref([])
const filters = reactive({ search: "", channel: "", status: "" })
const form = reactive(emptyForm())
const options = computed(() => props.workspace.options || {})
const choice = (values, first = null) => [...(first ? [first] : []), ...(values || []).map(value => ({ label: value || "None", value }))]
const campaigns = computed(() => props.workspace.campaigns.filter(campaign => {
  const query = filters.search.trim().toLowerCase()
  const text = [campaign.campaign_title, campaign.residence, campaign.project_type, campaign.primary_channel, campaign.hook, campaign.concept_summary].join(" ").toLowerCase()
  return (!query || text.includes(query)) && (!filters.channel || campaign.primary_channel === filters.channel) && (!filters.status || campaign.status === filters.status)
}))
const selected = computed(() => props.workspace.campaigns.find(item => item.name === selectedName.value) || campaigns.value[0] || null)
const physical = computed(() => form.primary_channel === "Physical poster")
function emptyForm() { return { name: "", source_request: "", campaign_title: "", status: "Draft", project_type: "Residence", residence: "Goldfields", primary_channel: "Physical poster", initiative_date: new Date().toISOString().slice(0, 10), due_date: "", audience: "Stellenbosch university students", objective: "", pain_point: "", hook: "", concept_summary: "", qr_destination: "", digital_destination: "", owner: "", reviewer: "", approval_notes: "", notes: "" } }
function theme(status) { return ["Approved", "Placed"].includes(status) ? "green" : status === "Changes needed" ? "red" : undefined }
function open(values = null) { Object.assign(form, emptyForm(), values || {}); files.value = (values?.assets || []).map(asset => ({ ...asset, file_url: asset.file_url, file_name: asset.file_name || asset.asset_title })); editing.value = true; error.value = "" }
function select(item) { selectedName.value = item.name; editing.value = false }
function guessType(name) { const lower = String(name || "").toLowerCase(); if (lower.endsWith(".pdf") && lower.includes("pack")) return "Print pack"; if (lower.endsWith(".pdf")) return "Poster"; if (lower.includes("story")) return "Story image"; if (lower.includes("google")) return "Google image"; if (/\.(png|jpe?g|webp|svg)$/.test(lower)) return physical.value ? "Poster" : "Feed image"; if (/\.(json|txt|md)$/.test(lower)) return "Copy"; return "Other" }
async function save() {
  if (!form.campaign_title.trim()) { error.value = "Add a campaign title."; return }
  if (form.project_type === "Residence" && !form.residence) { error.value = "Choose the residence."; return }
  if (physical.value && !form.qr_destination.trim()) { error.value = "A physical poster campaign needs its exact registered QR destination."; return }
  saving.value = true; error.value = ""
  try {
    const saved = await saveAdvertisingCampaign({ ...form, residence: form.project_type === "Residence" ? form.residence : "", qr_destination: physical.value ? form.qr_destination : "", assets: files.value.map(file => ({ asset_title: file.asset_title || file.file_name || "Advertising asset", asset_type: file.asset_type || guessType(file.file_name), channel: file.channel || form.primary_channel, format: file.format || String(file.file_name || "").split(".").pop()?.toUpperCase() || "File", review_status: file.review_status || (form.status === "Approved" ? "Approved" : "Review"), file_url: file.file_url, destination_url: file.destination_url || (physical.value ? form.qr_destination : form.digital_destination), notes: file.notes || "" })) })
    selectedName.value = saved.name; editing.value = false; emit("saved", `${saved.campaign_title} saved with ${saved.assets.length} file${saved.assets.length === 1 ? "" : "s"}.`)
  } catch (exception) { error.value = exception.message }
  finally { saving.value = false }
}
</script>

<template>
  <section class="advertising-section" aria-labelledby="advertising-campaigns-heading">
    <header class="advertising-section-header"><div><p class="advertising-eyebrow">Production</p><h2 id="advertising-campaigns-heading">Campaigns</h2><p>Hold the creative strategy, exact destination, review state, and useful team files in one record.</p></div><SystemOperationalButton v-if="workspace.can_manage" variant="solid" @click="open()">Add campaign</SystemOperationalButton></header>
    <div v-if="error" class="advertising-message advertising-message--error" role="alert">{{ error }}</div>
    <section v-if="editing" class="advertising-card">
      <header><h3>{{ form.name ? 'Edit campaign' : 'New campaign' }}</h3><p>Use one hook and one pain point. Physical posters require the exact QR; digital work keeps its clickable destination separately.</p></header>
      <div class="advertising-form-grid">
        <SystemFormControl v-model="form.campaign_title" label="Campaign title" />
        <label class="advertising-field"><span>Status</span><SystemSelect v-model="form.status" :options="choice(options.statuses)" /></label>
        <label class="advertising-field"><span>Project group</span><SystemSelect v-model="form.project_type" :options="choice(options.project_types)" /></label>
        <label v-if="form.project_type === 'Residence'" class="advertising-field"><span>Residence</span><SystemSelect v-model="form.residence" :options="choice(options.residences)" /></label>
        <label class="advertising-field"><span>Primary channel</span><SystemSelect v-model="form.primary_channel" :options="choice(options.channels)" /></label>
        <SystemFormControl v-model="form.initiative_date" type="date" label="Started" />
        <SystemFormControl v-model="form.due_date" type="date" label="Due date" />
        <SystemFormControl v-model="form.audience" label="Audience" />
        <label class="advertising-field advertising-field--wide"><span>Objective</span><SystemTextarea v-model="form.objective" :rows="2" /></label>
        <label class="advertising-field advertising-field--wide"><span>One pain point</span><SystemTextarea v-model="form.pain_point" :rows="2" /></label>
        <label class="advertising-field advertising-field--wide"><span>Hook</span><SystemTextarea v-model="form.hook" :rows="2" /></label>
        <label class="advertising-field advertising-field--wide"><span>Creative premise</span><SystemTextarea v-model="form.concept_summary" :rows="3" /></label>
        <SystemFormControl v-if="physical" v-model="form.qr_destination" class="advertising-field--wide" type="url" label="Exact poster QR destination" />
        <SystemFormControl v-else v-model="form.digital_destination" class="advertising-field--wide" type="url" label="Clickable digital destination" />
        <SystemFormControl v-model="form.reviewer" label="Reviewer" />
        <label class="advertising-field advertising-field--wide"><span>Notes and holds</span><SystemTextarea v-model="form.notes" :rows="2" /></label>
      </div>
      <div class="advertising-card advertising-card--raised"><strong>Private campaign files</strong><p>Upload the useful preview, final artwork, print pack, copy sheet, or source archive—not failed intermediate renders.</p><SystemMultiFileUploader v-model="files" accept="image/*,.pdf,.zip,.json,.txt,.md" label="Add advertising files" /><div v-if="files.length" class="advertising-list"><div v-for="file in files" :key="file.file_url" class="advertising-list-row"><span>{{ file.file_name || file.file_url }}</span><SystemBadge>{{ file.review_status || 'Review' }}</SystemBadge></div></div></div>
      <div class="advertising-actions"><SystemOperationalButton variant="outline" @click="editing = false">Cancel</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="saving" @click="save">Save campaign</SystemOperationalButton></div>
    </section>
    <template v-else>
      <section class="advertising-card advertising-filters" aria-label="Campaign filters">
        <SystemFormControl v-model="filters.search" label="Search" placeholder="Campaign, residence, channel, or hook" />
        <label class="advertising-field"><span>Channel</span><SystemSelect v-model="filters.channel" :options="choice(options.channels, { label: 'All channels', value: '' })" /></label>
        <label class="advertising-field"><span>Status</span><SystemSelect v-model="filters.status" :options="choice(options.statuses, { label: 'All statuses', value: '' })" /></label>
      </section>
      <section class="advertising-split">
        <aside class="advertising-card" aria-label="Campaign list"><div class="advertising-list"><SystemOperationalButton v-for="campaign in campaigns" :key="campaign.name" variant="ghost" @click="select(campaign)"><span class="advertising-list-row__body"><strong>{{ campaign.campaign_title }}</strong><small>{{ campaign.residence || campaign.project_type }} · {{ campaign.status }}</small></span></SystemOperationalButton><p v-if="!campaigns.length" class="advertising-empty">No campaigns match these filters.</p></div></aside>
        <article v-if="selected" class="advertising-card">
          <header class="advertising-section-header"><div><p class="advertising-eyebrow">{{ selected.name }}</p><h3>{{ selected.campaign_title }}</h3><p>{{ selected.hook || selected.concept_summary || 'No hook recorded yet.' }}</p></div><div class="advertising-actions"><SystemBadge :theme="theme(selected.status)">{{ selected.status }}</SystemBadge><SystemOperationalButton v-if="workspace.can_manage" variant="outline" @click="open(selected)">Edit</SystemOperationalButton></div></header>
          <dl class="advertising-data"><div><dt>Scope</dt><dd>{{ selected.residence || selected.project_type }}</dd></div><div><dt>Channel</dt><dd>{{ selected.primary_channel }}</dd></div><div><dt>Reviewer</dt><dd>{{ selected.reviewer || 'Not assigned' }}</dd></div></dl>
          <div class="advertising-destination"><strong>{{ selected.primary_channel === 'Physical poster' ? 'Poster QR destination' : 'Clickable destination' }}</strong><a v-if="selected.primary_channel === 'Physical poster' ? selected.qr_destination : selected.digital_destination" :href="selected.primary_channel === 'Physical poster' ? selected.qr_destination : selected.digital_destination" target="_blank" rel="noreferrer">{{ selected.primary_channel === 'Physical poster' ? selected.qr_destination : selected.digital_destination }}</a><span v-else>{{ selected.primary_channel === 'Physical poster' ? 'HOLD-QR' : 'Not recorded' }}</span><small>{{ selected.primary_channel === 'Physical poster' ? 'A physical scan proof is still required before release.' : 'Digital artwork does not inherit poster QR or stamp whitespace.' }}</small></div>
          <div><strong>Files</strong><div class="advertising-list"><div v-for="asset in selected.assets" :key="asset.name || asset.file_url" class="advertising-list-row"><div class="advertising-list-row__body"><strong>{{ asset.asset_title }}</strong><small>{{ asset.asset_type }} · {{ asset.format || asset.channel }}</small></div><SystemBadge :theme="theme(asset.review_status)">{{ asset.review_status }}</SystemBadge><a :href="asset.file_url" target="_blank" rel="noreferrer">Open</a></div><p v-if="!selected.assets.length" class="advertising-empty">No files attached yet.</p></div></div>
        </article>
        <div v-else class="advertising-card advertising-empty">No campaigns yet.</div>
      </section>
    </template>
  </section>
</template>
