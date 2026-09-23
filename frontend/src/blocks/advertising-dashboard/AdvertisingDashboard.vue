<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { SystemBadge, SystemFormControl, SystemMultiFileUploader, SystemOperationalButton, SystemSelect, SystemTextarea } from "@/desyium"
import { getAdvertisingLibrary, saveAdvertisingCampaign } from "@/resources/api"

const fallbackOptions = {
  statuses: ["Draft", "In review", "Changes needed", "Approved", "Placed", "Archived"],
  project_types: ["Residence", "Instagram", "Meta", "Google Ads", "Cross-channel", "Other"],
  channels: ["Physical poster", "Instagram feed", "Instagram story", "Meta feed", "Meta story", "Google Ads", "Other"],
  residences: ["", "Goldfields", "Metanoia", "Huis Visser", "Other"],
}
const library = ref({ campaigns: [], can_manage: false, options: fallbackOptions })
const selectedName = ref("")
const editing = ref(false)
const busy = ref(false)
const error = ref("")
const notice = ref("")
const files = ref([])
const filters = reactive({ search: "", channel: "", status: "" })
const form = reactive(emptyForm())

const options = computed(() => ({ ...fallbackOptions, ...(library.value.options || {}) }))
const channelOptions = computed(() => [{ label: "All channels", value: "" }, ...toOptions(options.value.channels)])
const statusFilterOptions = computed(() => [{ label: "All statuses", value: "" }, ...toOptions(options.value.statuses)])
const statusOptions = computed(() => toOptions(options.value.statuses))
const projectTypeOptions = computed(() => toOptions(options.value.project_types))
const primaryChannelOptions = computed(() => toOptions(options.value.channels))
const residenceOptions = computed(() => toOptions(options.value.residences, "No residence"))
const isPhysical = computed(() => form.primary_channel === "Physical poster")
const campaigns = computed(() => {
  const query = filters.search.trim().toLowerCase()
  return library.value.campaigns.filter(campaign => {
    const searchable = [campaign.campaign_title, campaign.residence, campaign.primary_channel, campaign.concept_summary].join(" ").toLowerCase()
    return (!query || searchable.includes(query)) && (!filters.channel || campaign.primary_channel === filters.channel) && (!filters.status || campaign.status === filters.status)
  })
})
const selectedCampaign = computed(() => library.value.campaigns.find(campaign => campaign.name === selectedName.value) || campaigns.value[0] || null)
const metrics = computed(() => ({
  total: library.value.campaigns.length,
  review: library.value.campaigns.filter(campaign => ["In review", "Changes needed"].includes(campaign.status)).length,
  approved: library.value.campaigns.filter(campaign => ["Approved", "Placed"].includes(campaign.status)).length,
  assets: library.value.campaigns.reduce((total, campaign) => total + (campaign.assets?.length || 0), 0),
}))

function emptyForm() {
  return { name: "", campaign_title: "", status: "Draft", project_type: "Residence", residence: "Goldfields", primary_channel: "Physical poster", initiative_date: new Date().toISOString().slice(0, 10), concept_summary: "", qr_destination: "", digital_destination: "", reviewer: "", notes: "" }
}
function toOptions(values, emptyLabel = "None") {
  return (values || []).map(value => ({ label: value || emptyLabel, value }))
}
function badgeTheme(status) {
  if (["Approved", "Placed"].includes(status)) return "green"
  if (status === "Changes needed") return "red"
  return undefined
}
function resetForm(values = emptyForm()) {
  Object.assign(form, emptyForm(), values)
  files.value = (values.assets || []).map(asset => ({ file_url: asset.file_url, file_name: asset.file_name || asset.asset_title, ...asset }))
}
function startCreate() {
  resetForm()
  editing.value = true
  notice.value = ""
  error.value = ""
}
function startEdit(campaign) {
  resetForm(campaign)
  selectedName.value = campaign.name
  editing.value = true
  notice.value = ""
  error.value = ""
}
function cancelEdit() {
  editing.value = false
  resetForm(selectedCampaign.value || emptyForm())
}
function selectCampaign(campaign) {
  selectedName.value = campaign.name
  editing.value = false
  notice.value = ""
  error.value = ""
}
function guessAssetType(fileName) {
  const lower = String(fileName || "").toLowerCase()
  if (lower.endsWith(".pdf") && lower.includes("pack")) return "Print pack"
  if (lower.endsWith(".pdf")) return "Poster"
  if (lower.includes("story")) return "Story image"
  if (lower.includes("google")) return "Google image"
  if (/\.(png|jpe?g|webp|svg)$/.test(lower)) return isPhysical.value ? "Poster" : "Feed image"
  if (/\.(json|txt|md)$/.test(lower)) return "Copy"
  return "Other"
}
function assetFormat(fileName) {
  return String(fileName || "").split(".").pop()?.toUpperCase() || "File"
}
async function loadLibrary(preferredName = "") {
  busy.value = true
  error.value = ""
  try {
    library.value = await getAdvertisingLibrary()
    selectedName.value = preferredName || selectedName.value || library.value.campaigns[0]?.name || ""
  } catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}
async function saveCampaign() {
  error.value = ""
  notice.value = ""
  if (!form.campaign_title.trim()) { error.value = "Add a campaign title."; return }
  if (form.project_type === "Residence" && !form.residence) { error.value = "Choose the residence."; return }
  if (isPhysical.value && !form.qr_destination.trim()) { error.value = "A physical poster campaign needs its exact registered QR destination."; return }
  busy.value = true
  try {
    const payload = {
      ...form,
      residence: form.project_type === "Residence" ? form.residence : "",
      qr_destination: isPhysical.value ? form.qr_destination : "",
      assets: files.value.map(file => ({
        asset_title: file.asset_title || file.file_name || "Advertising asset",
        asset_type: file.asset_type || guessAssetType(file.file_name),
        channel: file.channel || form.primary_channel,
        format: file.format || assetFormat(file.file_name),
        review_status: file.review_status || (form.status === "Approved" ? "Approved" : "Review"),
        file_url: file.file_url,
        destination_url: file.destination_url || (isPhysical.value ? form.qr_destination : form.digital_destination),
        notes: file.notes || "",
      })),
    }
    const saved = await saveAdvertisingCampaign(payload)
    editing.value = false
    notice.value = `${saved.campaign_title} saved with ${saved.assets.length} file${saved.assets.length === 1 ? "" : "s"}.`
    await loadLibrary(saved.name)
  } catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

onMounted(loadLibrary)
</script>

<template>
  <section data-block="advertising-dashboard" class="advertising-workspace">
    <header class="advertising-header">
      <div><p class="eyebrow">Advertising</p><h1>Campaign library</h1><p>Find the latest artwork, keep the exact destination beside it, and move each campaign through review without publishing automatically.</p></div>
      <SystemOperationalButton v-if="library.can_manage" variant="solid" size="lg" @click="startCreate">Add campaign</SystemOperationalButton>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="notice" class="state-message" role="status">{{ notice }}</div>

    <section class="advertising-metrics" aria-label="Advertising summary">
      <div><strong>{{ metrics.total }}</strong><span>campaigns</span></div>
      <div><strong>{{ metrics.review }}</strong><span>need review</span></div>
      <div><strong>{{ metrics.approved }}</strong><span>approved or placed</span></div>
      <div><strong>{{ metrics.assets }}</strong><span>stored files</span></div>
    </section>

    <section class="advertising-filters" aria-label="Campaign filters">
      <SystemFormControl v-model="filters.search" label="Search campaigns" placeholder="Name, residence, channel, or idea" />
      <label class="field-shell"><span>Channel</span><SystemSelect v-model="filters.channel" :options="channelOptions" /></label>
      <label class="field-shell"><span>Status</span><SystemSelect v-model="filters.status" :options="statusFilterOptions" /></label>
      <SystemOperationalButton variant="outline" :loading="busy" @click="loadLibrary(selectedName)">Refresh</SystemOperationalButton>
    </section>

    <section v-if="editing" class="advertising-editor" aria-labelledby="campaign-editor-heading">
      <div class="section-heading"><div><p class="eyebrow">{{ form.name ? "Edit campaign" : "New campaign" }}</p><h2 id="campaign-editor-heading">Campaign details and files</h2><p>Poster QR destinations are recorded only for physical campaigns. Digital campaigns keep their clickable destination separately.</p></div></div>
      <div class="advertising-form-grid">
        <SystemFormControl v-model="form.campaign_title" label="Campaign title" />
        <label class="field-shell"><span>Status</span><SystemSelect v-model="form.status" :options="statusOptions" /></label>
        <label class="field-shell"><span>Project group</span><SystemSelect v-model="form.project_type" :options="projectTypeOptions" /></label>
        <label v-if="form.project_type === 'Residence'" class="field-shell"><span>Residence</span><SystemSelect v-model="form.residence" :options="residenceOptions" /></label>
        <label class="field-shell"><span>Primary channel</span><SystemSelect v-model="form.primary_channel" :options="primaryChannelOptions" /></label>
        <SystemFormControl v-model="form.initiative_date" type="date" label="Initiative date" />
        <SystemFormControl v-if="isPhysical" v-model="form.qr_destination" class="advertising-field-wide" type="url" label="Exact poster QR destination" placeholder="https://bulkbite.co.za/qr/..." />
        <SystemFormControl v-else v-model="form.digital_destination" class="advertising-field-wide" type="url" label="Clickable digital destination" placeholder="https://bulkbite.co.za/..." />
        <SystemFormControl v-model="form.reviewer" label="Reviewer" placeholder="Faith, French, or assigned reviewer" />
        <label class="field-shell advertising-field-wide"><span>One idea / pain point</span><SystemTextarea v-model="form.concept_summary" :rows="3" /></label>
        <label class="field-shell advertising-field-wide"><span>Notes and holds</span><SystemTextarea v-model="form.notes" :rows="3" placeholder="Food fidelity, resolution, approval, placement, or publishing holds" /></label>
      </div>
      <div class="advertising-upload">
        <div><strong>Private campaign files</strong><p>Upload print packs, final images, previews, source packages, or copy files. They remain permission-controlled.</p></div>
        <SystemMultiFileUploader v-model="files" accept="image/*,.pdf,.zip,.json,.txt,.md" label="Add advertising files" />
        <ul v-if="files.length"><li v-for="file in files" :key="file.file_url">{{ file.file_name || file.file_url }}</li></ul>
      </div>
      <footer class="advertising-actions">
        <SystemOperationalButton variant="outline" :disabled="busy" @click="cancelEdit">Cancel</SystemOperationalButton>
        <SystemOperationalButton variant="solid" :loading="busy" @click="saveCampaign">Save campaign</SystemOperationalButton>
      </footer>
    </section>

    <section v-else class="advertising-library">
      <aside class="campaign-list" aria-label="Campaigns">
        <button v-for="campaign in campaigns" :key="campaign.name" type="button" class="campaign-row" :class="{ 'is-selected': selectedCampaign?.name === campaign.name }" @click="selectCampaign(campaign)">
          <span><strong>{{ campaign.campaign_title }}</strong><small>{{ campaign.residence || campaign.project_type }} · {{ campaign.primary_channel }}</small></span>
          <SystemBadge :theme="badgeTheme(campaign.status)">{{ campaign.status }}</SystemBadge>
        </button>
        <p v-if="!campaigns.length" class="empty-state">No campaigns match these filters.</p>
      </aside>

      <article v-if="selectedCampaign" class="campaign-detail">
        <header class="campaign-detail__header">
          <div><p class="eyebrow">{{ selectedCampaign.name }}</p><h2>{{ selectedCampaign.campaign_title }}</h2><p>{{ selectedCampaign.concept_summary || "No concept summary recorded yet." }}</p></div>
          <div class="campaign-detail__actions"><SystemBadge :theme="badgeTheme(selectedCampaign.status)">{{ selectedCampaign.status }}</SystemBadge><SystemOperationalButton v-if="library.can_manage" variant="outline" @click="startEdit(selectedCampaign)">Edit</SystemOperationalButton></div>
        </header>
        <dl class="campaign-facts">
          <div><dt>Group</dt><dd>{{ selectedCampaign.residence || selectedCampaign.project_type }}</dd></div>
          <div><dt>Channel</dt><dd>{{ selectedCampaign.primary_channel }}</dd></div>
          <div><dt>Started</dt><dd>{{ selectedCampaign.initiative_date }}</dd></div>
          <div><dt>Reviewer</dt><dd>{{ selectedCampaign.reviewer || "Not assigned" }}</dd></div>
        </dl>
        <section class="destination-record">
          <div v-if="selectedCampaign.primary_channel === 'Physical poster'"><span>Poster QR destination</span><a v-if="selectedCampaign.qr_destination" :href="selectedCampaign.qr_destination" target="_blank" rel="noreferrer">{{ selectedCampaign.qr_destination }}</a><strong v-else>HOLD-QR</strong></div>
          <div v-else><span>Clickable destination</span><a v-if="selectedCampaign.digital_destination" :href="selectedCampaign.digital_destination" target="_blank" rel="noreferrer">{{ selectedCampaign.digital_destination }}</a><strong v-else>Not recorded</strong></div>
          <p>{{ selectedCampaign.primary_channel === "Physical poster" ? "The printed QR belongs to this exact route. Physical proof scanning is still required before release." : "Digital artwork does not inherit poster QR or stamp whitespace." }}</p>
        </section>
        <section class="asset-section">
          <div class="section-heading"><div><p class="eyebrow">Files</p><h3>Campaign assets</h3></div><SystemBadge>{{ selectedCampaign.assets?.length || 0 }}</SystemBadge></div>
          <div class="asset-list">
            <article v-for="asset in selectedCampaign.assets || []" :key="asset.name || asset.file_url">
              <div><strong>{{ asset.asset_title }}</strong><small>{{ asset.asset_type }} · {{ asset.format || asset.channel }}</small></div>
              <SystemBadge :theme="badgeTheme(asset.review_status)">{{ asset.review_status }}</SystemBadge>
              <a :href="asset.file_url" target="_blank" rel="noreferrer">Open or download</a>
            </article>
            <p v-if="!selectedCampaign.assets?.length" class="empty-state">No files have been attached to this campaign yet.</p>
          </div>
        </section>
        <p v-if="selectedCampaign.notes" class="campaign-notes"><strong>Notes and holds</strong>{{ selectedCampaign.notes }}</p>
      </article>
      <div v-else class="campaign-detail campaign-detail--empty"><strong>No campaigns yet</strong><p>Add the first initiative, then attach its review exports or print pack.</p></div>
    </section>
  </section>
</template>

<style scoped>
.advertising-workspace { width: min(100%, var(--grid-max-width)); margin: 0 auto; padding: var(--spacing-l) var(--spacing-m) var(--spacing-xl-2xl); display: grid; gap: var(--spacing-m); color: var(--theme-text); }
.advertising-header { display: flex; align-items: end; justify-content: space-between; gap: var(--spacing-m); }
.advertising-header h1, .campaign-detail h2 { margin: 0; }
.advertising-header p, .campaign-detail p, .advertising-upload p { margin: var(--spacing-2xs) 0 0; color: var(--theme-text-muted); }
.eyebrow { margin: 0 0 var(--spacing-3xs); color: var(--theme-text-muted); font-size: var(--font-size--2); font-weight: var(--font-weight-600); letter-spacing: var(--font-letter-spacing-2); text-transform: uppercase; }
.advertising-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); overflow: hidden; }
.advertising-metrics div { padding: var(--spacing-m); display: grid; gap: var(--spacing-3xs); border-right: 1px solid var(--theme-border); }
.advertising-metrics div:last-child { border-right: 0; }
.advertising-metrics strong { font-size: var(--font-size-3); }
.advertising-metrics span { color: var(--theme-text-muted); font-size: var(--font-size--1); }
.advertising-filters { display: grid; grid-template-columns: minmax(15rem, 2fr) repeat(2, minmax(10rem, 1fr)) auto; gap: var(--spacing-s); align-items: end; padding: var(--spacing-m); border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); }
.field-shell { display: grid; gap: var(--spacing-3xs); min-width: 0; }
.field-shell > span { font-size: var(--font-size--1); font-weight: var(--font-weight-600); }
.advertising-library { min-height: 32rem; display: grid; grid-template-columns: minmax(17rem, 0.72fr) minmax(0, 1.65fr); gap: var(--spacing-m); }
.campaign-list, .campaign-detail, .advertising-editor { border: 1px solid var(--theme-border); border-radius: var(--radius-l); background: var(--theme-surface); }
.campaign-list { align-self: start; display: grid; overflow: hidden; }
.campaign-row { width: 100%; min-height: 4.5rem; padding: var(--spacing-s) var(--spacing-m); display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-s); border: 0; border-bottom: 1px solid var(--theme-border); background: transparent; color: inherit; text-align: left; cursor: pointer; }
.campaign-row:last-child { border-bottom: 0; }
.campaign-row:hover, .campaign-row:focus-visible, .campaign-row.is-selected { background: var(--theme-surface-raised); }
.campaign-row:focus-visible { outline: 2px solid var(--theme-primary); outline-offset: -2px; }
.campaign-row span { min-width: 0; display: grid; gap: var(--spacing-3xs); }
.campaign-row small { color: var(--theme-text-muted); }
.campaign-detail { min-width: 0; padding: var(--spacing-l); display: grid; align-content: start; gap: var(--spacing-m); }
.campaign-detail__header { display: flex; align-items: start; justify-content: space-between; gap: var(--spacing-m); }
.campaign-detail__actions { display: flex; align-items: center; gap: var(--spacing-xs); }
.campaign-facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--spacing-s); margin: 0; }
.campaign-facts div { min-width: 0; padding: var(--spacing-s); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.campaign-facts dt { color: var(--theme-text-muted); font-size: var(--font-size--2); }
.campaign-facts dd { margin: var(--spacing-3xs) 0 0; font-weight: var(--font-weight-600); overflow-wrap: anywhere; }
.destination-record { padding: var(--spacing-m); display: grid; gap: var(--spacing-xs); border: 1px solid var(--theme-border); border-radius: var(--radius-m); }
.destination-record div { display: grid; gap: var(--spacing-3xs); }
.destination-record span { color: var(--theme-text-muted); font-size: var(--font-size--2); font-weight: var(--font-weight-600); text-transform: uppercase; }
.destination-record a { color: var(--theme-primary); overflow-wrap: anywhere; }
.destination-record p { margin: 0; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: var(--spacing-s); }
.section-heading h2, .section-heading h3 { margin: 0; }
.asset-section { display: grid; gap: var(--spacing-s); }
.asset-list { display: grid; border-top: 1px solid var(--theme-border); }
.asset-list article { min-height: 4rem; padding: var(--spacing-s) 0; display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: var(--spacing-s); border-bottom: 1px solid var(--theme-border); }
.asset-list article > div { display: grid; gap: var(--spacing-3xs); }
.asset-list small { color: var(--theme-text-muted); }
.asset-list a { color: var(--theme-primary); font-weight: var(--font-weight-600); }
.campaign-notes { padding: var(--spacing-s); display: grid; gap: var(--spacing-3xs); border-left: 3px solid var(--theme-primary); background: var(--theme-surface-raised); white-space: pre-line; }
.advertising-editor { padding: var(--spacing-l); display: grid; gap: var(--spacing-m); }
.advertising-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--spacing-s); align-items: end; }
.advertising-field-wide { grid-column: span 2; }
.advertising-upload { padding: var(--spacing-m); display: grid; gap: var(--spacing-s); border: 1px solid var(--theme-border); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.advertising-upload ul { margin: 0; padding-left: var(--spacing-l); color: var(--theme-text-muted); }
.advertising-actions { display: flex; justify-content: flex-end; gap: var(--spacing-s); }
.empty-state, .campaign-detail--empty { padding: var(--spacing-l); color: var(--theme-text-muted); }
.campaign-detail--empty { min-height: 18rem; align-content: center; justify-items: center; text-align: center; }
.state-message { padding: var(--spacing-s) var(--spacing-m); border: 1px solid var(--theme-border); border-radius: var(--radius-m); background: var(--theme-surface-raised); }
.state-message--error { color: var(--theme-danger, var(--theme-text)); }
@media (max-width: 72rem) {
  .advertising-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .advertising-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .campaign-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 52rem) {
  .advertising-workspace { padding: var(--spacing-m) var(--spacing-s) var(--spacing-xl); }
  .advertising-header, .campaign-detail__header { align-items: stretch; flex-direction: column; }
  .advertising-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .advertising-metrics div:nth-child(2) { border-right: 0; }
  .advertising-metrics div:nth-child(-n+2) { border-bottom: 1px solid var(--theme-border); }
  .advertising-library { grid-template-columns: 1fr; min-height: 0; }
  .campaign-detail, .advertising-editor { padding: var(--spacing-m); }
}
@media (max-width: 38rem) {
  .advertising-filters, .advertising-form-grid, .campaign-facts { grid-template-columns: 1fr; }
  .advertising-field-wide { grid-column: auto; }
  .asset-list article { grid-template-columns: minmax(0, 1fr) auto; }
  .asset-list article a { grid-column: 1 / -1; }
  .advertising-actions { flex-direction: column-reverse; }
}
</style>
