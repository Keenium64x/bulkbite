<script setup>
import { computed } from "vue"
import { SystemBadge, SystemOperationalButton } from "@/desyium"

const props = defineProps({ workspace: { type: Object, required: true }, busy: { type: Boolean, default: false } })
const emit = defineEmits(["navigate", "refresh"])
const urgentRequests = computed(() => props.workspace.requests.filter(item => ["Urgent", "High"].includes(item.priority) && !["Complete", "Cancelled"].includes(item.status)).slice(0, 5))
const recentCampaigns = computed(() => props.workspace.campaigns.slice(0, 5))
const metrics = computed(() => props.workspace.metrics || {})
function theme(status) { return ["Approved", "Placed", "Complete"].includes(status) ? "green" : status === "Changes needed" ? "red" : undefined }
</script>

<template>
  <section class="advertising-section" aria-labelledby="advertising-overview-heading">
    <header class="advertising-section-header">
      <div><p class="advertising-eyebrow">Current workload</p><h2 id="advertising-overview-heading">Overview</h2><p>Requests enter here, become campaigns, pass review, and finish with files and measured placements.</p></div>
      <SystemOperationalButton variant="outline" :loading="busy" @click="emit('refresh')">Refresh</SystemOperationalButton>
    </header>
    <section class="advertising-metrics" aria-label="Advertising summary">
      <div class="advertising-metric"><strong>{{ metrics.open_requests || 0 }}</strong><span>open requests</span></div>
      <div class="advertising-metric"><strong>{{ metrics.active_campaigns || 0 }}</strong><span>active campaigns</span></div>
      <div class="advertising-metric"><strong>{{ metrics.awaiting_review || 0 }}</strong><span>awaiting review</span></div>
      <div class="advertising-metric"><strong>{{ metrics.approved_assets || 0 }}</strong><span>approved files</span></div>
    </section>
    <div class="advertising-grid">
      <article class="advertising-card">
        <header class="advertising-section-header"><div><h3>Priority requests</h3><p>Needs that should be picked up first.</p></div><SystemOperationalButton variant="ghost" @click="emit('navigate', 'requests')">All requests</SystemOperationalButton></header>
        <div v-if="urgentRequests.length" class="advertising-list">
          <div v-for="item in urgentRequests" :key="item.name" class="advertising-list-row"><div class="advertising-list-row__body"><strong>{{ item.request_title }}</strong><small>{{ item.name }} · {{ item.primary_channel }} · due {{ item.due_date || 'not set' }}</small></div><SystemBadge>{{ item.priority }}</SystemBadge></div>
        </div>
        <p v-else class="advertising-empty">No high-priority requests.</p>
      </article>
      <article class="advertising-card">
        <header class="advertising-section-header"><div><h3>Recent campaigns</h3><p>Latest production and review activity.</p></div><SystemOperationalButton variant="ghost" @click="emit('navigate', 'campaigns')">All campaigns</SystemOperationalButton></header>
        <div v-if="recentCampaigns.length" class="advertising-list">
          <div v-for="campaign in recentCampaigns" :key="campaign.name" class="advertising-list-row"><div class="advertising-list-row__body"><strong>{{ campaign.campaign_title }}</strong><small>{{ campaign.residence || campaign.project_type }} · {{ campaign.primary_channel }}</small></div><SystemBadge :theme="theme(campaign.status)">{{ campaign.status }}</SystemBadge></div>
        </div>
        <p v-else class="advertising-empty">No campaigns have been started yet.</p>
      </article>
      <article class="advertising-card advertising-card--raised">
        <h3>Fast handoff</h3><p>Open Requests, capture the real need and exact destination, then copy the generated Codex brief. That brief routes the work into the existing advertising factory without making you restate the rules.</p>
        <SystemOperationalButton variant="solid" @click="emit('navigate', 'requests')">Create request</SystemOperationalButton>
      </article>
      <article class="advertising-card advertising-card--raised">
        <h3>Release boundary</h3><p>Everything stays a review draft until Faith or French approves it. Recording a request or campaign never publishes, prints, spends, or implies university approval.</p>
        <SystemOperationalButton variant="outline" @click="emit('navigate', 'review')">Open review queue</SystemOperationalButton>
      </article>
    </div>
  </section>
</template>
