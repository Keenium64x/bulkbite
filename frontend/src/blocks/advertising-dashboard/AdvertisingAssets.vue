<script setup>
import { computed, reactive } from "vue"
import { SystemBadge, SystemFormControl, SystemOperationalButton, SystemSelect } from "@/desyium"
const props = defineProps({ workspace: { type: Object, required: true }, busy: { type: Boolean, default: false } })
const emit = defineEmits(["refresh"])
const filters = reactive({ search: "", type: "", status: "" })
const options = computed(() => props.workspace.options || {})
const choice = (values, label) => [{ label, value: "" }, ...(values || []).map(value => ({ label: value, value }))]
const assets = computed(() => props.workspace.assets.filter(asset => {
  const query = filters.search.trim().toLowerCase()
  const text = [asset.asset_title, asset.campaign_title, asset.channel, asset.format].join(" ").toLowerCase()
  return (!query || text.includes(query)) && (!filters.type || asset.asset_type === filters.type) && (!filters.status || asset.review_status === filters.status)
}))
function theme(status) { return status === "Approved" ? "green" : status === "Changes needed" ? "red" : undefined }
</script>
<template>
  <section class="advertising-section" aria-labelledby="advertising-assets-heading">
    <header class="advertising-section-header"><div><p class="advertising-eyebrow">Library</p><h2 id="advertising-assets-heading">Assets</h2><p>One searchable place for previews, final artwork, print packs, copy, and source archives.</p></div><SystemOperationalButton variant="outline" :loading="busy" @click="emit('refresh')">Refresh</SystemOperationalButton></header>
    <section class="advertising-card advertising-filters"><SystemFormControl v-model="filters.search" label="Search files" placeholder="File or campaign" /><label class="advertising-field"><span>Type</span><SystemSelect v-model="filters.type" :options="choice(options.asset_types, 'All types')" /></label><label class="advertising-field"><span>Status</span><SystemSelect v-model="filters.status" :options="choice(options.asset_statuses, 'All statuses')" /></label></section>
    <div class="advertising-grid">
      <article v-for="asset in assets" :key="asset.name || asset.file_url" class="advertising-card"><header class="advertising-section-header"><div><p class="advertising-eyebrow">{{ asset.campaign }}</p><h3>{{ asset.asset_title }}</h3><p>{{ asset.campaign_title }}</p></div><SystemBadge :theme="theme(asset.review_status)">{{ asset.review_status }}</SystemBadge></header><dl class="advertising-data"><div><dt>Type</dt><dd>{{ asset.asset_type }}</dd></div><div><dt>Channel</dt><dd>{{ asset.channel }}</dd></div><div><dt>Format</dt><dd>{{ asset.format || 'File' }}</dd></div></dl><div class="advertising-actions"><SystemOperationalButton :as="'a'" :href="asset.file_url" target="_blank" rel="noreferrer" variant="outline">Open or download</SystemOperationalButton></div></article>
    </div>
    <p v-if="!assets.length" class="advertising-empty">No assets match these filters.</p>
  </section>
</template>
