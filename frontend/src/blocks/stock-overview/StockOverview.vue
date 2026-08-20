<script setup>
import { ref } from "vue"
import { SystemBadge, SystemCard, SystemFormControl, SystemOperationalButton } from "@/desyium"

defineProps({
  snapshot: { type: Object, default: null },
  inventory: { type: Object, default: null },
  plan: { type: Object, default: null },
  scanResult: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
})

const emit = defineEmits(["scan", "open-workflow"])
const scanCode = ref("")

function submitScan() {
  if (scanCode.value.trim()) emit("scan", scanCode.value.trim())
}

function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: digits })
}
</script>

<template>
  <section data-block="stock-overview" class="workflow-block">
    <header class="workflow-header workflow-header--ink">
      <div>
        <p class="eyebrow">Operations</p>
        <h1>Stock overview</h1>
        <p>Receipts add stock. Production uses it. Counts correct it. Every posted movement keeps its evidence.</p>
      </div>
      <div class="metric-board" aria-label="Workspace totals">
        <div><strong>{{ snapshot?.counts?.ingredients || 0 }}</strong><span>ingredients</span></div>
        <div><strong>{{ snapshot?.counts?.received_receipts || 0 }}</strong><span>receipts posted</span></div>
        <div><strong>{{ snapshot?.counts?.draft_production_runs || 0 }}</strong><span>runs to finish</span></div>
        <div><strong>{{ snapshot?.counts?.posted_production_runs || 0 }}</strong><span>runs posted</span></div>
      </div>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="loading && !inventory" class="state-message" role="status">Loading current stock...</div>

    <div class="workflow-grid">
      <SystemCard class="work-panel work-panel--scan">
        <p class="panel-index">Stock lookup</p>
        <h2>Find stock item</h2>
        <p>Scan a QR code or barcode, or type the code printed on the label.</p>
        <form class="inline-action" @submit.prevent="submitScan">
          <SystemFormControl v-model="scanCode" label="QR or barcode" placeholder="Scan or type code" size="lg" />
          <SystemOperationalButton type="submit" theme="blue" variant="solid" size="lg">Find item</SystemOperationalButton>
        </form>
        <div v-if="scanResult" class="scan-result" aria-live="polite">
          <SystemBadge class="status-badge">MATCHED</SystemBadge>
          <strong>{{ scanResult.item_name }}</strong>
          <span>{{ scanResult.item_code }} · {{ scanResult.uom }}</span>
        </div>
      </SystemCard>

      <SystemCard class="work-panel work-panel--shortage">
        <p class="panel-index">Plan status</p>
        <h2>{{ plan?.plan_title || "FOUR-WEEK PLAN" }}</h2>
        <p>{{ plan?.date_note || "The imported plan is relative until production dates are confirmed." }}</p>
        <div class="shortage-summary">
          <strong>{{ plan?.total_requirements?.filter(item => item.shortage_qty > 0).length || 0 }}</strong>
          <span>ingredients short</span>
        </div>
        <SystemOperationalButton variant="outline" @click="emit('open-workflow', 'production')">Open production</SystemOperationalButton>
      </SystemCard>
    </div>

    <section class="data-section" aria-labelledby="stock-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Ingredients</p><h2 id="stock-heading">Current stock</h2></div>
        <SystemBadge>{{ inventory?.location || "Ingredients" }}</SystemBadge>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Ingredient</th><th>On hand</th><th>Unit</th><th>Rate</th><th>Stock value</th></tr></thead>
          <tbody>
            <tr v-for="item in inventory?.items || []" :key="item.item_code">
              <td><strong>{{ item.item_name }}</strong><small>{{ item.item_code }}</small></td>
              <td class="number-cell">{{ number(item.actual_qty, 3) }}</td>
              <td>{{ item.stock_uom }}</td>
              <td class="money-cell">R {{ number(item.valuation_rate) }}</td>
              <td class="money-cell">R {{ number(item.stock_value) }}</td>
            </tr>
            <tr v-if="!inventory?.items?.length"><td colspan="5">No ingredient records are available.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="data-section" aria-labelledby="requirements-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Planned demand</p><h2 id="requirements-heading">Plan requirements</h2></div>
        <SystemBadge>{{ plan?.status || "NO PLAN" }}</SystemBadge>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Ingredient</th><th>Expected</th><th>Available</th><th>Difference</th><th>Unit</th></tr></thead>
          <tbody>
            <tr v-for="item in plan?.total_requirements || []" :key="item.item_code" :class="{ 'is-short': item.shortage_qty > 0 }">
              <td><strong>{{ item.item_name }}</strong></td>
              <td class="number-cell">{{ number(item.required_qty, 3) }}</td>
              <td class="number-cell">{{ number(item.available_qty, 3) }}</td>
              <td class="number-cell">{{ item.shortage_qty > 0 ? `SHORT ${number(item.shortage_qty, 3)}` : "ENOUGH" }}</td>
              <td>{{ item.uom }}</td>
            </tr>
            <tr v-if="!plan?.total_requirements?.length"><td colspan="5">No active plan requirements are available.</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="data-section" aria-labelledby="recent-heading">
      <div class="section-heading"><div><p class="eyebrow">Activity</p><h2 id="recent-heading">Recent records</h2></div></div>
      <div class="record-grid">
        <article v-for="receipt in snapshot?.recent_receipts || []" :key="receipt.name" class="record-strip">
          <span>RECEIPT</span><strong>{{ receipt.supplier }}</strong><small>{{ receipt.invoice_date }} · {{ receipt.status }}</small><b>R {{ number(receipt.total_amount) }}</b>
        </article>
        <article v-for="run in snapshot?.recent_runs || []" :key="run.name" class="record-strip">
          <span>PRODUCTION</span><strong>{{ run.finished_item }}</strong><small>{{ run.production_date }} · {{ run.docstatus ? "Posted" : "Draft" }}</small><b>{{ number(run.actual_output_qty) }} meals</b>
        </article>
        <p v-if="!snapshot?.recent_receipts?.length && !snapshot?.recent_runs?.length">No recent operational records.</p>
      </div>
    </section>
  </section>
</template>
