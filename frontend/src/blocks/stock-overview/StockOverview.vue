<script setup>
import { computed, ref } from "vue"
import { SystemBadge, SystemCard, SystemLinkedRecordField, SystemOperationalButton, SystemScanCodeField } from "@/desyium"
import { useRouter } from "vue-router"

const props = defineProps({
  mode: { type: String, default: "dashboard" },
  snapshot: { type: Object, default: null },
  inventory: { type: Object, default: null },
  plan: { type: Object, default: null },
  scanResult: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
})

const emit = defineEmits(["scan", "map-scan", "open-workflow"])
const router = useRouter()
const scanCode = ref("")
const mappingItem = ref("")
const itemOptions = computed(() => (props.inventory?.items || []).map((item) => ({ label: item.item_name, value: item.item_code })))
const nextWeek = computed(() => props.plan?.next_production?.row || props.plan?.rows?.[0])
const stockEnough = computed(() => (props.plan?.total_requirements || []).filter(item => item.shortage_qty <= 0).length)

function submitScan(code) { if (String(code || "").trim()) emit("scan", String(code).trim()) }
function assignCode() { if (mappingItem.value && props.scanResult?.scan_code) emit("map-scan", mappingItem.value, props.scanResult.scan_code) }

function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: digits })
}
</script>

<template>
  <section data-block="stock-overview" class="workflow-block">
    <header v-if="mode === 'dashboard'" class="workflow-header">
      <div>
        <p class="eyebrow">Dashboard</p>
        <h1>What needs attention now</h1>
        <p>See today’s operating position, then go straight to the work that needs attention.</p>
      </div>
      <div class="metric-board" aria-label="Workspace totals">
        <div><strong>{{ plan?.customer_demand?.total_customers || 0 }}</strong><span>customers planned</span></div>
        <div><strong>{{ number(plan?.customer_demand?.weekly_output_qty, 1) }} kg</strong><span>food per week</span></div>
        <div><strong>{{ plan?.buying?.shortage_count || 0 }}</strong><span>items to buy</span></div>
        <div><strong>R {{ number(plan?.buying?.expected_cost) }}</strong><span>expected spend</span></div>
      </div>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="loading && !inventory" class="state-message" role="status">Loading current stock...</div>

    <div v-if="mode === 'dashboard'" class="workflow-grid">
      <SystemCard class="work-panel"><p class="panel-index">Customer direction</p><h2>{{ plan?.plan_title || "No active direction" }}</h2><p v-if="plan">{{ plan.customer_demand.total_customers }} customers currently require {{ number(plan.customer_demand.weekly_output_qty, 1) }} kg per week.</p><p v-else>Set the customer mix and repeating meal cycle.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">{{ plan ? "Update direction" : "Set direction" }}</SystemOperationalButton></SystemCard>
      <SystemCard class="work-panel"><p class="panel-index">Next production</p><h2>{{ nextWeek?.finished_item_name || "No meal scheduled" }}</h2><p v-if="nextWeek">Meal {{ nextWeek.week_number }} · {{ number(nextWeek.weekly_servings, 0) }} portions · {{ number(nextWeek.planned_output_qty, 1) }} kg</p><p v-else>Choose the repeating meals in Planning.</p><SystemOperationalButton variant="outline" :disabled="!nextWeek" @click="emit('open-workflow', 'production')">Open production</SystemOperationalButton></SystemCard>
      <SystemCard class="work-panel"><p class="panel-index">Buying</p><h2>{{ plan?.buying?.shortage_count || 0 }} items need stock</h2><p>{{ stockEnough }} planned ingredients have enough stock. {{ plan?.buying?.missing_offer_count || 0 }} shortages still need a supplier price.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'buying')">View shopping list</SystemOperationalButton></SystemCard>
      <SystemCard class="work-panel"><p class="panel-index">Purchases</p><h2>Record what was bought</h2><p>Upload the supplier receipt after shopping so actual stock and prices are updated.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'receipts')">Add receipt</SystemOperationalButton></SystemCard>
    </div>

    <header v-if="mode === 'stock'" class="workflow-header">
      <div><p class="eyebrow">Stock</p><h1>Current ingredient stock</h1><p>Check balances, scan an item, and reconcile a physical count below.</p></div>
      <SystemBadge>{{ inventory?.location || "Ingredients" }}</SystemBadge>
    </header>

    <div v-if="mode === 'stock'" class="workflow-grid dashboard-secondary">
      <SystemCard class="work-panel work-panel--scan">
        <p class="panel-index">Quick check</p>
        <h2>Find an ingredient</h2>
        <p>Scan a QR code or barcode, or type the code printed on the label.</p>
        <SystemScanCodeField v-model="scanCode" :busy="loading" autofocus @scan="submitScan" />
        <div v-if="scanResult?.matched" class="scan-result" aria-live="polite">
          <SystemBadge class="status-badge">MATCHED</SystemBadge>
          <strong>{{ scanResult.item_name }}</strong>
          <span>{{ scanResult.item_code }} · {{ scanResult.uom }}</span>
        </div>
        <div v-else-if="scanResult && !scanResult.matched" class="scan-result scan-result--unknown" aria-live="polite">
          <SystemBadge>NOT MAPPED</SystemBadge>
          <strong>{{ scanResult.scan_code }}</strong>
          <span>{{ scanResult.reason }}</span>
          <SystemLinkedRecordField v-model="mappingItem" label="Assign to item" :options="itemOptions" placeholder="Choose an ingredient" create-label="Add item" manage-label="Manage items" @create="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Item' } })" @manage="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Item' } })" />
          <SystemOperationalButton variant="outline" :disabled="!mappingItem" @click="assignCode">Save code mapping</SystemOperationalButton>
        </div>
      </SystemCard>

      <SystemCard class="work-panel work-panel--shortage"><p class="panel-index">Stock readiness</p><h2>{{ plan?.buying?.shortage_count || 0 }} ingredients short</h2><p>{{ stockEnough }} planned ingredients are covered by current stock.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'buying')">Open buying</SystemOperationalButton></SystemCard>
    </div>

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="stock-heading">
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

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="requirements-heading">
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

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="recent-heading">
      <div class="section-heading"><div><p class="eyebrow">Activity</p><h2 id="recent-heading">Recent records</h2></div></div>
      <div class="record-grid">
        <article v-for="receipt in snapshot?.recent_receipts || []" :key="receipt.name" class="record-strip">
          <span>RECEIPT</span><strong>{{ receipt.supplier }}</strong><small>{{ receipt.invoice_date }} · {{ receipt.status }}</small><b>R {{ number(receipt.total_amount) }}</b>
        </article>
        <article v-for="run in snapshot?.recent_runs || []" :key="run.name" class="record-strip">
          <span>PRODUCTION</span><strong>{{ run.finished_item }}</strong><small>{{ run.production_date }} · {{ run.docstatus ? "Posted" : "Draft" }}</small><b>{{ number(run.actual_output_qty) }} kg</b>
        </article>
        <p v-if="!snapshot?.recent_receipts?.length && !snapshot?.recent_runs?.length">No recent operational records.</p>
      </div>
    </section>
  </section>
</template>
