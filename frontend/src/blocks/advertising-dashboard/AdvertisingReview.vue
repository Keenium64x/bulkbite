<script setup>
import { reactive, ref } from "vue"
import { SystemBadge, SystemOperationalButton, SystemTextarea } from "@/desyium"
import { reviewAdvertisingCampaign } from "@/resources/api"
const props = defineProps({ workspace: { type: Object, required: true } })
const emit = defineEmits(["saved"])
const notes = reactive({})
const saving = ref("")
const error = ref("")
async function review(campaign, outcome) { saving.value = campaign.name; error.value = ""; try { await reviewAdvertisingCampaign(campaign.name, outcome, notes[campaign.name] || ""); emit("saved", `${campaign.campaign_title}: ${outcome}.`) } catch (exception) { error.value = exception.message } finally { saving.value = "" } }
</script>
<template>
  <section class="advertising-section" aria-labelledby="advertising-review-heading">
    <header><p class="advertising-eyebrow">Human gate</p><h2 id="advertising-review-heading">Review</h2><p>Approve only after the message, food, dimensions, destination, and required physical proof are correct. Approval here does not publish or spend.</p></header>
    <div v-if="error" class="advertising-message advertising-message--error" role="alert">{{ error }}</div>
    <article v-for="campaign in workspace.review_queue" :key="campaign.name" class="advertising-card">
      <header class="advertising-section-header"><div><p class="advertising-eyebrow">{{ campaign.name }}</p><h3>{{ campaign.campaign_title }}</h3><p>{{ campaign.hook || campaign.concept_summary || 'No creative premise recorded.' }}</p></div><SystemBadge>{{ campaign.status }}</SystemBadge></header>
      <dl class="advertising-data"><div><dt>Reviewer</dt><dd>{{ campaign.reviewer || 'Not assigned' }}</dd></div><div><dt>Files</dt><dd>{{ campaign.assets.length }}</dd></div><div><dt>Destination</dt><dd>{{ campaign.primary_channel === 'Physical poster' ? (campaign.qr_destination || 'HOLD-QR') : (campaign.digital_destination || 'Not recorded') }}</dd></div></dl>
      <div class="advertising-list"><div v-for="asset in campaign.assets" :key="asset.name" class="advertising-list-row"><div class="advertising-list-row__body"><strong>{{ asset.asset_title }}</strong><small>{{ asset.asset_type }} · {{ asset.format || asset.channel }}</small></div><SystemBadge>{{ asset.review_status }}</SystemBadge><a :href="asset.file_url" target="_blank" rel="noreferrer">Inspect</a></div></div>
      <label class="advertising-field"><span>Review notes</span><SystemTextarea v-model="notes[campaign.name]" :rows="3" placeholder="Required correction or approval evidence" /></label>
      <div v-if="workspace.can_manage" class="advertising-actions"><SystemOperationalButton variant="outline" :loading="saving === campaign.name" @click="review(campaign, 'Changes needed')">Request changes</SystemOperationalButton><SystemOperationalButton variant="solid" :loading="saving === campaign.name" @click="review(campaign, 'Approved')">Approve</SystemOperationalButton></div>
    </article>
    <p v-if="!workspace.review_queue.length" class="advertising-empty">Nothing is waiting for review.</p>
  </section>
</template>
