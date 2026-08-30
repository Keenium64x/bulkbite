<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { BarChart } from "echarts/charts"
import { GridComponent, TooltipComponent } from "echarts/components"
import { use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import { SystemBadge, SystemCalendar, SystemCard, SystemChart, SystemDatePicker, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton, SystemScanCodeField, SystemSelect, SystemStat, SystemTextarea } from "@/desyium"
import { createCustomOperationalAction, recordContainerMovement, updateOperationalAction } from "@/resources/api"

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent])

const props = defineProps({
  mode: { type: String, default: "dashboard" },
  snapshot: { type: Object, default: null },
  inventory: { type: Object, default: null },
  plan: { type: Object, default: null },
  scanResult: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
})

const emit = defineEmits(["scan", "map-scan", "open-workflow", "changed"])
const router = useRouter()
const scanCode = ref("")
const mappingItem = ref("")
const costBasis = ref("expected")
const actionBusy = ref("")
const actionEditors = ref({})
const customActionOpen = ref(false)
const customActionBusy = ref(false)
const customAction = ref({ title: "", due_date: "", consequence_note: "", target_section: "operations", notes: "" })
const containerBusy = ref(false)
const containerMovement = ref({ container_asset: "", movement_type: "", customer_reference: "", notes: "" })

const itemOptions = computed(() => (props.inventory?.items || []).map((item) => ({ label: item.item_name, value: item.item_code })))
const nextWeek = computed(() => props.plan?.next_production?.row || props.plan?.rows?.[0])
const stockEnough = computed(() => (props.plan?.total_requirements || []).filter((item) => item.shortage_qty <= 0).length)
const requirementCount = computed(() => (props.plan?.total_requirements || []).length)
const currentShortageCount = computed(() => Math.max(requirementCount.value - stockEnough.value, 0))
const stockCoverage = computed(() => requirementCount.value ? Math.round((stockEnough.value / requirementCount.value) * 100) : 0)
const stockValue = computed(() => (props.inventory?.items || []).reduce((total, item) => total + Number(item.stock_value || 0), 0))
const latestReceipt = computed(() => props.snapshot?.recent_receipts?.[0] || null)
const latestRun = computed(() => props.snapshot?.recent_runs?.[0] || null)
const operations = computed(() => props.plan?.operations || props.snapshot?.operations || {})
const primaryAction = computed(() => operations.value?.primary || null)
const calendarActions = computed(() => operations.value?.calendar?.actions || [])
const actionQueueCount = computed(() => operations.value?.actions?.length || 0)
const calendarConfig = { defaultMode: "Month", disableModes: ["Week", "Day"], isEditMode: false, allowCustomClickEvents: true, enableShortcuts: false, showIcon: false, weekends: [] }
const calendarEvents = computed(() => calendarActions.value.map((item) => ({
  id: item.name,
  title: item.title,
  fromDate: String(item.due_date),
  toDate: String(item.due_date),
  fromTime: "09:00",
  toTime: "09:30",
  isFullDay: true,
  color: item.display_status === "Missed" ? "orange" : item.display_status === "Completed" ? "green" : item.display_status === "Rescheduled" ? "blue" : item.display_status === "Cancelled" ? "blue" : "amber",
  operationalAction: item,
})))
const containers = computed(() => operations.value?.containers || {})
const containerOptions = computed(() => (containers.value?.assets || []).filter((item) => !["Lost", "Retired"].includes(item.lifecycle_state)).map((item) => ({ label: `${item.asset_code} · ${item.lifecycle_state}`, value: item.name })))
const movementOptions = ["Filled for Production", "Issued to Customer", "Returned by Customer", "Sent to Maintenance", "Returned from Maintenance", "Marked Lost", "Retired"].map((value) => ({ label: value, value }))
const latestRunName = computed(() => {
  const itemCode = latestRun.value?.finished_item
  return props.snapshot?.options?.recipes?.find((recipe) => recipe.item === itemCode)?.recipe_name || itemCode || "No production recorded"
})
const nextWork = computed(() => [
  {
    key: "buying",
    eyebrow: "Buy",
    title: currentShortageCount.value ? `${currentShortageCount.value} ingredients still needed` : "Planned ingredients are covered",
    detail: props.plan?.buying?.missing_offer_count ? `${props.plan.buying.missing_offer_count} need a supplier price before the basket is complete.` : `Expected basket ${money(props.plan?.buying?.expected_cost)}.`,
    action: "Open buying",
    variant: currentShortageCount.value ? "solid" : "outline",
  },
  {
    key: "receipts",
    eyebrow: "Receive",
    title: latestReceipt.value ? `${latestReceipt.value.supplier} receipt is ${String(latestReceipt.value.status || "recorded").toLowerCase()}` : "Record food that arrived",
    detail: latestReceipt.value ? `${latestReceipt.value.invoice_date} · ${money(latestReceipt.value.total_amount)}` : "Upload and review the supplier receipt, then add the food to stock.",
    action: "Add receipt",
    variant: "outline",
  },
  {
    key: "production",
    eyebrow: "Cook",
    title: nextWeek.value?.finished_item_name || "No production is scheduled",
    detail: nextWeek.value ? `${number(nextWeek.value.planned_output_qty, 1)} kg planned for meal ${nextWeek.value.week_number}.` : "Update the meal direction before opening production.",
    action: "Open production",
    variant: "outline",
    disabled: !nextWeek.value,
  },
  {
    key: "export",
    eyebrow: "Review",
    title: "Compare theory with actual spend",
    detail: "Check receipt spend, production usage, price changes, and accountant exports.",
    action: "View reports",
    variant: "ghost",
  },
])
const finances = computed(() => props.plan?.financial_summary || null)
const actualAvailable = computed(() => Boolean(finances.value?.actual))
const selectedPosition = computed(() => {
  if (costBasis.value === "actual" && actualAvailable.value) return finances.value.actual
  return finances.value?.expected || { food_cost: 0, gross_profit: 0, margin_percent: 0 }
})
const basisLabel = computed(() => costBasis.value === "actual" && actualAvailable.value ? "Actual production cost" : "Expected recipe cost")
const chartOption = computed(() => ({
  animation: false,
  aria: { enabled: true, label: { description: `${basisLabel.value}. Four-week revenue ${money(finances.value?.revenue)}, food cost ${money(selectedPosition.value.food_cost)}, and gross profit before overheads ${money(selectedPosition.value.gross_profit)}.` } },
  grid: { left: 8, right: 8, top: 16, bottom: 38, containLabel: true },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => money(value) },
  xAxis: { type: "category", data: ["Revenue", "Food cost", "Gross profit"], axisLine: { lineStyle: { color: themeColor("--theme-border") } }, axisTick: { show: false }, axisLabel: { color: themeColor("--theme-text-muted"), fontSize: 12 } },
  yAxis: { type: "value", axisLabel: { color: themeColor("--theme-text-muted"), formatter: (value) => `R${compactNumber(value)}` }, splitLine: { lineStyle: { color: themeColor("--theme-border") } } },
  series: [{
    type: "bar",
    barMaxWidth: 54,
    data: [
      { value: Number(finances.value?.revenue || 0), itemStyle: { color: themeColor("--theme-text"), borderRadius: [7, 7, 0, 0] } },
      { value: Number(selectedPosition.value.food_cost || 0), itemStyle: { color: themeColor("--theme-text-muted"), borderRadius: [7, 7, 0, 0] } },
      { value: Number(selectedPosition.value.gross_profit || 0), itemStyle: { color: themeColor("--theme-primary"), borderRadius: [7, 7, 0, 0] } },
    ],
  }],
}))

function submitScan(code) { if (String(code || "").trim()) emit("scan", String(code).trim()) }
function assignCode() { if (mappingItem.value && props.scanResult?.scan_code) emit("map-scan", mappingItem.value, props.scanResult.scan_code) }
function selectCostBasis(value) { if (value !== "actual" || actualAvailable.value) costBasis.value = value }
function number(value, digits = 2) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: digits }) }
function dateLabel(value) { return value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "No date" }
function compactNumber(value) { return Number(value || 0).toLocaleString("en-ZA", { notation: "compact", maximumFractionDigits: 1 }) }
function money(value) { return `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function themeColor(name) { return window.getComputedStyle(document.documentElement).getPropertyValue(name).trim() }
async function changeAction(item, action) {
  const editor = actionEditors.value[item.name] || {}
  const newDate = action === "reschedule" ? editor.newDate : null
  const reason = action === "reschedule" ? editor.rescheduleReason || "Rescheduled from operations calendar." : action === "cancel" ? editor.cancelReason : null
  if (action === "reschedule" && !newDate) return
  if (action === "cancel" && !reason) return
  actionBusy.value = item.name
  try {
    await updateOperationalAction(item.name, action, newDate, reason)
    actionEditors.value[item.name] = {}
    emit("changed")
    return true
  }
  finally { actionBusy.value = "" }
}
async function saveActionChange(item, action, close) {
  if (await changeAction(item, action)) close()
}
function editAction(item, mode) {
  actionEditors.value[item.name] = { ...(actionEditors.value[item.name] || {}), mode, newDate: item.rescheduled_to || item.due_date || "" }
}
function configureAction(item) {
  const target = item.configuration || { doctype: item.schedule ? "BulkBite Operational Schedule" : "BulkBite Operational Action", name: item.schedule || item.name }
  router.push({ name: "AuxiliaryRecordEdit", params: { doctype: target.doctype, name: target.name } })
}
async function saveCustomAction() {
  if (!customAction.value.title.trim() || !customAction.value.due_date) return
  customActionBusy.value = true
  try {
    const result = await createCustomOperationalAction(customAction.value)
    customAction.value = { title: "", due_date: "", consequence_note: "", target_section: "operations", notes: "" }
    customActionOpen.value = false
    emit("changed", result.calendar)
  } finally { customActionBusy.value = false }
}
async function saveContainerMovement() {
  if (!containerMovement.value.container_asset || !containerMovement.value.movement_type) return
  containerBusy.value = true
  try {
    await recordContainerMovement({ ...containerMovement.value, posting_date: new Date().toISOString().slice(0, 10) })
    containerMovement.value = { container_asset: "", movement_type: "", customer_reference: "", notes: "" }
    emit("changed")
  } finally { containerBusy.value = false }
}
</script>

<template>
  <section data-block="stock-overview" class="workflow-block">
    <header v-if="mode === 'dashboard'" class="workflow-header dashboard-header">
      <div><p class="eyebrow">Dashboard</p><h1>BulkBite at a glance</h1><p>See the current four-week food economics and move straight to the next job.</p></div>
      <SystemBadge>{{ plan?.customer_demand?.total_customers || 0 }} customers planned</SystemBadge>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="loading && !inventory" class="state-message" role="status">Loading current stock...</div>

    <template v-if="mode === 'dashboard'">
      <div v-if="!plan" class="dashboard-empty">
        <SystemCard class="dashboard-empty__card"><p class="panel-index">Start here</p><h2>Set the current customer and meal direction</h2><p>The Dashboard can calculate revenue, buying cost, and gross profit as soon as a plan exists.</p><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'planning')">Set direction</SystemOperationalButton></SystemCard>
      </div>

      <div v-else class="dashboard-grid">
        <SystemCard class="financial-panel">
          <div class="financial-panel__header">
            <div><p class="panel-index">Four-week position</p><h2>Gross profit before overheads</h2><p>{{ finances?.qualification }}</p></div>
            <div class="basis-control" role="group" aria-label="Food cost basis">
              <SystemOperationalButton :variant="costBasis === 'expected' ? 'solid' : 'outline'" size="sm" :aria-pressed="costBasis === 'expected'" @click="selectCostBasis('expected')">Expected</SystemOperationalButton>
              <SystemOperationalButton :variant="costBasis === 'actual' ? 'solid' : 'outline'" size="sm" :disabled="!actualAvailable" :aria-pressed="costBasis === 'actual'" @click="selectCostBasis('actual')">Actual production</SystemOperationalButton>
            </div>
          </div>

          <div class="financial-panel__body">
            <div class="financial-chart" role="img" :aria-label="`${basisLabel}: revenue ${money(finances?.revenue)}, food cost ${money(selectedPosition.food_cost)}, gross profit ${money(selectedPosition.gross_profit)}`"><SystemChart autoresize :option="chartOption" /></div>
            <div class="financial-stats">
              <SystemStat :value="money(finances?.revenue)" label="Expected revenue" qualification="Current customer mix for one four-week cycle" />
              <SystemStat :value="money(selectedPosition.food_cost)" :label="costBasis === 'actual' && actualAvailable ? 'Actual food used' : 'Expected food cost'" :qualification="costBasis === 'actual' && actualAvailable ? 'Latest four posted meals in this direction' : 'Four planned recipes at current ingredient valuation'" />
              <SystemStat :value="money(selectedPosition.gross_profit)" label="Gross profit" qualification="Before overheads, labour, packaging, and tax" />
              <SystemStat :value="number(selectedPosition.margin_percent, 1)" suffix="%" label="Gross margin" :qualification="basisLabel" />
            </div>
          </div>

          <p v-if="!actualAvailable" class="evidence-note">Actual food usage appears after four production runs are posted for this direction. {{ finances?.actual_run_count || 0 }} of 4 are available, so expected recipe cost is shown.</p>
          <table class="desyium-block__visually-hidden"><caption>{{ basisLabel }} financial chart values</caption><thead><tr><th>Measure</th><th>Amount</th></tr></thead><tbody><tr><td>Revenue</td><td>{{ money(finances?.revenue) }}</td></tr><tr><td>Food cost</td><td>{{ money(selectedPosition.food_cost) }}</td></tr><tr><td>Gross profit before overheads</td><td>{{ money(selectedPosition.gross_profit) }}</td></tr></tbody></table>
        </SystemCard>

		<SystemCard v-if="primaryAction" class="next-action-panel" :class="`is-${primaryAction.severity}`">
		  <div class="next-action-panel__marker" aria-hidden="true"><span>{{ primaryAction.severity === 'ready' ? '✓' : '!' }}</span></div>
		  <div class="next-action-panel__message"><div class="next-action-panel__topline"><p class="panel-index">What needs to happen next</p><button type="button" class="queue-indicator" @click="emit('open-workflow', 'operations')">{{ actionQueueCount }} {{ actionQueueCount === 1 ? 'action' : 'actions' }} waiting</button></div><h2>{{ primaryAction.title }}</h2><p>{{ primaryAction.reason }}</p><small v-if="primaryAction.due_date">Due {{ dateLabel(primaryAction.due_date) }}</small></div>
		  <div class="next-action-panel__steps" v-if="primaryAction.recovery_steps?.length"><strong>Recovery steps</strong><ol><li v-for="step in primaryAction.recovery_steps" :key="step">{{ step }}</li></ol></div>
		  <div class="next-action-panel__actions"><SystemOperationalButton variant="solid" @click="emit('open-workflow', primaryAction.action_section)">{{ primaryAction.action_label }}</SystemOperationalButton><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'operations')">Operations calendar</SystemOperationalButton></div>
		</SystemCard>

        <SystemCard class="operating-panel">
          <p class="panel-index">Current direction</p><h2>{{ plan.plan_title }}</h2>
          <div class="operating-figures"><div><strong>{{ plan.customer_demand.total_customers }}</strong><span>customers</span></div><div><strong>{{ number(plan.customer_demand.weekly_output_qty, 1) }} kg</strong><span>food per week</span></div><div><strong>{{ currentShortageCount }}</strong><span>items to buy</span></div></div>
          <div class="next-production"><span>Next production</span><strong>{{ nextWeek?.finished_item_name || "No meal scheduled" }}</strong><small v-if="nextWeek">Meal {{ nextWeek.week_number }} · {{ number(nextWeek.planned_output_qty, 1) }} kg planned</small></div>
          <SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Update direction</SystemOperationalButton>
        </SystemCard>

        <SystemCard class="activity-panel">
          <div class="panel-heading"><div><p class="panel-index">Latest activity</p><h2>What has been recorded</h2></div><SystemBadge>{{ snapshot?.counts?.posted_production_runs || 0 }} runs posted</SystemBadge></div>
          <div class="activity-list">
            <article class="activity-item"><span>Latest receipt</span><template v-if="latestReceipt"><strong>{{ latestReceipt.supplier }}</strong><small>{{ latestReceipt.invoice_date }} · {{ latestReceipt.status }}</small><b>{{ money(latestReceipt.total_amount) }}</b></template><template v-else><strong>No receipt recorded</strong><small>Add the first supplier receipt after buying.</small></template></article>
            <article class="activity-item"><span>Latest production</span><template v-if="latestRun"><strong>{{ latestRunName }}</strong><small>{{ latestRun.production_date }} · {{ latestRun.docstatus ? "Posted" : "Draft" }}</small><b>{{ number(latestRun.actual_output_qty, 1) }} kg</b></template><template v-else><strong>No production recorded</strong><small>Open production when the next meal is ready.</small></template></article>
          </div>
		  <div class="panel-actions"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'receipts')">Open receipts</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="emit('open-workflow', 'history')">Production history</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="emit('open-workflow', 'operations')">Operations calendar</SystemOperationalButton></div>
        </SystemCard>

        <SystemCard class="readiness-panel">
          <div class="panel-heading"><div><p class="panel-index">Stock readiness</p><h2>{{ stockCoverage }}% of planned ingredients covered</h2></div><SystemBadge>{{ currentShortageCount }} short</SystemBadge></div>
          <div class="readiness-meter" role="meter" aria-label="Planned ingredient stock coverage" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="stockCoverage"><span :style="{ width: `${stockCoverage}%` }" /></div>
          <div class="operating-figures readiness-figures"><div><strong>{{ stockEnough }} of {{ requirementCount }}</strong><span>ingredients covered</span></div><div><strong>{{ money(stockValue) }}</strong><span>stock on hand value</span></div></div>
          <div class="panel-actions"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'buying')">Open buying</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="emit('open-workflow', 'stock')">View stock</SystemOperationalButton></div>
        </SystemCard>

      </div>

      <SystemCard v-if="plan" class="action-panel">
        <div class="action-panel__header"><p class="panel-index">Next work</p><h2>Move the kitchen forward</h2><p>The current plan sets the theory. Choose the job that matches what is happening now.</p></div>
        <div class="action-panel__grid"><article v-for="work in nextWork" :key="work.key" class="work-action"><p class="panel-index">{{ work.eyebrow }}</p><h3>{{ work.title }}</h3><p>{{ work.detail }}</p><SystemOperationalButton :variant="work.variant" :disabled="work.disabled" @click="emit('open-workflow', work.key)">{{ work.action }}</SystemOperationalButton></article></div>
      </SystemCard>
	</template>

	<header v-if="mode === 'operations'" class="workflow-header"><div><p class="eyebrow">Operational calendar</p><h1>Scheduled work and exceptions</h1><p>Complete, reschedule, configure, or add the operational work BulkBite must remember.</p></div><div class="button-row"><SystemOperationalButton variant="solid" @click="customActionOpen = !customActionOpen">{{ customActionOpen ? 'Close custom action' : 'Add custom action' }}</SystemOperationalButton><SystemOperationalButton variant="outline" @click="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Operational Schedule' } })">Manage schedules</SystemOperationalButton></div></header>
	<template v-if="mode === 'operations'">
	  <section v-if="customActionOpen" class="data-section custom-action-form"><div class="section-heading"><div><p class="eyebrow">One-off work</p><h2>Add a custom calendar action</h2><p>Use a recurring schedule only when this work repeats.</p></div></div><div class="custom-action-form__fields"><SystemFormControl v-model="customAction.title" label="Action" placeholder="What must happen?" /><SystemDatePicker v-model="customAction.due_date" label="Due date" format="YYYY-MM-DD" /><SystemSelect v-model="customAction.target_section" label="App destination" :options="['operations','stock','export','production'].map(value => ({ label: value, value }))" /><SystemTextarea v-model="customAction.consequence_note" label="If this is missed" /><SystemTextarea v-model="customAction.notes" label="Instructions" /></div><div class="button-row"><SystemOperationalButton variant="solid" :loading="customActionBusy" :disabled="!customAction.title.trim() || !customAction.due_date" @click="saveCustomAction">Add to calendar</SystemOperationalButton></div></section>
	  <section class="data-section"><div class="section-heading"><div><p class="eyebrow">Position</p><h2>What is due</h2></div><SystemBadge>{{ operations?.calendar?.counts?.missed || 0 }} missed</SystemBadge></div><div class="metric-board"><div><strong>{{ operations?.calendar?.counts?.missed || 0 }}</strong><span>missed</span></div><div><strong>{{ operations?.calendar?.counts?.due || 0 }}</strong><span>due or upcoming</span></div><div><strong>{{ operations?.calendar?.counts?.completed || 0 }}</strong><span>completed</span></div><div><strong>{{ operations?.calendar?.counts?.rescheduled || 0 }}</strong><span>rescheduled</span></div></div></section>
	  <section class="data-section calendar-section"><div class="section-heading"><div><p class="eyebrow">Event calendar</p><h2>Recurring and custom work</h2><p>Select an event to update it without leaving the calendar.</p></div></div><SystemCalendar class="operations-calendar" :config="calendarConfig" :events="calendarEvents"><template #event-popover-content="{ calendarEvent, close }"><div class="calendar-event-detail"><SystemBadge :theme="calendarEvent.operationalAction.display_status === 'Missed' ? 'red' : calendarEvent.operationalAction.display_status === 'Completed' ? 'green' : undefined">{{ calendarEvent.operationalAction.display_status }}</SystemBadge><strong>{{ calendarEvent.title }}</strong><small>{{ dateLabel(calendarEvent.fromDate) }} · {{ calendarEvent.operationalAction.action_type }}</small><p v-if="calendarEvent.operationalAction.consequence_note">{{ calendarEvent.operationalAction.consequence_note }}</p><div v-if="actionEditors[calendarEvent.id]?.mode === 'reschedule'" class="inline-action-editor"><SystemDatePicker v-model="actionEditors[calendarEvent.id].newDate" label="New date" format="YYYY-MM-DD" /><SystemTextarea v-model="actionEditors[calendarEvent.id].rescheduleReason" label="Reason" /><div class="button-row"><SystemOperationalButton size="sm" variant="solid" :loading="actionBusy === calendarEvent.id" :disabled="!actionEditors[calendarEvent.id].newDate" @click="saveActionChange(calendarEvent.operationalAction, 'reschedule', close)">Save new date</SystemOperationalButton><SystemOperationalButton size="sm" variant="ghost" @click="actionEditors[calendarEvent.id] = {}">Keep current date</SystemOperationalButton></div></div><div v-else-if="actionEditors[calendarEvent.id]?.mode === 'cancel'" class="inline-action-editor"><SystemTextarea v-model="actionEditors[calendarEvent.id].cancelReason" label="Why is this cancelled?" /><div class="button-row"><SystemOperationalButton size="sm" variant="solid" :loading="actionBusy === calendarEvent.id" :disabled="!actionEditors[calendarEvent.id].cancelReason" @click="saveActionChange(calendarEvent.operationalAction, 'cancel', close)">Confirm cancellation</SystemOperationalButton><SystemOperationalButton size="sm" variant="ghost" @click="actionEditors[calendarEvent.id] = {}">Keep action</SystemOperationalButton></div></div><div v-else class="button-row"><SystemOperationalButton v-if="['Due','Missed'].includes(calendarEvent.operationalAction.display_status)" size="sm" variant="solid" :loading="actionBusy === calendarEvent.id" @click="saveActionChange(calendarEvent.operationalAction, 'complete', close)">Complete</SystemOperationalButton><SystemOperationalButton v-if="['Due','Missed'].includes(calendarEvent.operationalAction.display_status)" size="sm" variant="outline" @click="editAction(calendarEvent.operationalAction, 'reschedule')">Reschedule</SystemOperationalButton><SystemOperationalButton size="sm" variant="outline" @click="configureAction(calendarEvent.operationalAction); close()">Configure</SystemOperationalButton><SystemOperationalButton v-if="['Due','Missed'].includes(calendarEvent.operationalAction.display_status)" size="sm" variant="ghost" @click="editAction(calendarEvent.operationalAction, 'cancel')">Cancel</SystemOperationalButton></div></div></template></SystemCalendar></section>
	</template>

	<header v-if="mode === 'containers'" class="workflow-header"><div><p class="eyebrow">Stock · Containers</p><h1>Reusable container control</h1><p>Track each reusable container from clean stock through filling, customer issue, return, maintenance, loss, or retirement.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'stock')">Back to stock</SystemOperationalButton><SystemOperationalButton variant="outline" @click="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Container Asset' } })">Add container</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Container Type' } })">Add container type</SystemOperationalButton></div></header>
	<template v-if="mode === 'containers'"><section class="data-section"><div class="section-heading"><div><p class="eyebrow">Fleet position</p><h2>Where the containers are</h2></div><div class="button-row"><SystemOperationalButton variant="outline" @click="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Container Asset' } })">Manage containers</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Container Type' } })">Container settings</SystemOperationalButton></div></div><div class="metric-board"><div><strong>{{ containers.states?.Clean || 0 }}</strong><span>clean</span></div><div><strong>{{ containers.states?.Filled || 0 }}</strong><span>filled</span></div><div><strong>{{ containers.states?.['With Customer'] || 0 }}</strong><span>with customers</span></div><div><strong>{{ containers.overdue || 0 }}</strong><span>overdue</span></div><div><strong>{{ containers.states?.Maintenance || 0 }}</strong><span>maintenance</span></div><div><strong>{{ money(containers.pending_replacement_charges) }}</strong><span>pending replacement charges</span></div></div><div class="container-stock-position"><div class="section-heading"><div><p class="eyebrow">Stock identity</p><h3>Container items in stock</h3><p>The Packaging item records how many containers were bought. Container assets record where each reusable physical container is now.</p></div><SystemOperationalButton variant="ghost" @click="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Item' } })">Add container stock item</SystemOperationalButton></div><div class="table-wrap"><table><thead><tr><th>Container type</th><th>Packaging item</th><th>In stock</th><th>Food capacity</th></tr></thead><tbody><tr v-for="item in containers.types || []" :key="item.name"><td><strong>{{ item.container_type_name }}</strong><small v-if="item.default_for_production">Default for production</small></td><td>{{ item.stock_item }}</td><td>{{ number(item.stock_qty) }} {{ item.stock_uom || 'Each' }}</td><td>{{ number(item.capacity_qty) }} {{ item.capacity_uom }}</td></tr></tbody></table></div></div><div class="container-movement-form"><SystemSelect v-model="containerMovement.container_asset" label="Container" :options="containerOptions" /><SystemSelect v-model="containerMovement.movement_type" label="What happened" :options="movementOptions" /><SystemFormControl v-if="containerMovement.movement_type === 'Issued to Customer'" v-model="containerMovement.customer_reference" label="Customer reference" /><SystemFormControl v-model="containerMovement.notes" label="Movement notes" /><SystemOperationalButton variant="solid" :loading="containerBusy" :disabled="!containerMovement.container_asset || !containerMovement.movement_type || (containerMovement.movement_type === 'Issued to Customer' && !containerMovement.customer_reference)" @click="saveContainerMovement">Record movement</SystemOperationalButton></div><p v-if="containerMovement.movement_type === 'Marked Lost'" class="evidence-note">Marking a customer container lost records a pending charge at twice its configured replacement price.</p><div class="table-wrap"><table><thead><tr><th>Container</th><th>Type</th><th>State</th><th>Customer</th><th>Expected return</th></tr></thead><tbody><tr v-for="item in containers.assets || []" :key="item.name" :class="{ 'is-short': item.overdue }"><td><strong>{{ item.asset_code }}</strong></td><td>{{ item.container_type }}</td><td>{{ item.lifecycle_state }}</td><td>{{ item.current_customer_reference || 'BulkBite' }}</td><td>{{ item.expected_return_date || 'Not out' }}</td></tr></tbody></table></div></section></template>

	<header v-if="mode === 'stock'" class="workflow-header"><div><p class="eyebrow">Stock</p><h1>Current ingredient stock</h1><p>Check balances, scan an item, and reconcile a physical count below.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'containers')">Containers</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="router.push({ name: 'BulkBiteSetup' })">Stock settings</SystemOperationalButton><SystemBadge>{{ inventory?.location || "Ingredients" }}</SystemBadge></div></header>
    <div v-if="mode === 'stock'" class="workflow-grid dashboard-secondary">
      <SystemCard class="work-panel work-panel--scan">
        <p class="panel-index">Quick check</p><h2>Find an ingredient</h2><p>Scan a QR code or barcode, or type the code printed on the label.</p><SystemScanCodeField v-model="scanCode" :busy="loading" autofocus @scan="submitScan" />
        <div v-if="scanResult?.matched" class="scan-result" aria-live="polite"><SystemBadge class="status-badge">MATCHED</SystemBadge><strong>{{ scanResult.item_name }}</strong><span>{{ scanResult.item_code }} · {{ scanResult.uom }}</span></div>
        <div v-else-if="scanResult && !scanResult.matched" class="scan-result scan-result--unknown" aria-live="polite"><SystemBadge>NOT MAPPED</SystemBadge><strong>{{ scanResult.scan_code }}</strong><span>{{ scanResult.reason }}</span><SystemLinkedRecordField v-model="mappingItem" label="Assign to item" :options="itemOptions" placeholder="Choose an ingredient" create-label="Add item" manage-label="Manage items" @create="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Item' } })" @manage="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Item' } })" /><SystemOperationalButton variant="outline" :disabled="!mappingItem" @click="assignCode">Save code mapping</SystemOperationalButton></div>
      </SystemCard>
      <SystemCard class="work-panel work-panel--shortage"><p class="panel-index">Stock readiness</p><h2>{{ currentShortageCount }} ingredients short</h2><p>{{ stockEnough }} planned ingredients are covered by current stock.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'buying')">Open buying</SystemOperationalButton></SystemCard>
    </div>

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="stock-heading">
      <div class="section-heading"><div><p class="eyebrow">Ingredients</p><h2 id="stock-heading">Current stock</h2></div><SystemBadge>{{ inventory?.location || "Ingredients" }}</SystemBadge></div>
      <div class="table-wrap"><table><thead><tr><th>Ingredient</th><th>On hand</th><th>Unit</th><th>Rate</th><th>Stock value</th></tr></thead><tbody><tr v-for="item in inventory?.items || []" :key="item.item_code"><td><strong>{{ item.item_name }}</strong><small>{{ item.item_code }}</small></td><td class="number-cell">{{ number(item.actual_qty, 3) }}</td><td>{{ item.stock_uom }}</td><td class="money-cell">R {{ number(item.valuation_rate) }}</td><td class="money-cell">R {{ number(item.stock_value) }}</td></tr><tr v-if="!inventory?.items?.length"><td colspan="5">No ingredient records are available.</td></tr></tbody></table></div>
    </section>

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="requirements-heading">
      <div class="section-heading"><div><p class="eyebrow">Planned demand</p><h2 id="requirements-heading">Plan requirements</h2></div><SystemBadge>{{ plan?.status || "NO PLAN" }}</SystemBadge></div>
      <div class="table-wrap"><table><thead><tr><th>Ingredient</th><th>Expected</th><th>Available</th><th>Difference</th><th>Unit</th></tr></thead><tbody><tr v-for="item in plan?.total_requirements || []" :key="item.item_code" :class="{ 'is-short': item.shortage_qty > 0 }"><td><strong>{{ item.item_name }}</strong></td><td class="number-cell">{{ number(item.required_qty, 3) }}</td><td class="number-cell">{{ number(item.available_qty, 3) }}</td><td class="number-cell">{{ item.shortage_qty > 0 ? `SHORT ${number(item.shortage_qty, 3)}` : "ENOUGH" }}</td><td>{{ item.uom }}</td></tr><tr v-if="!plan?.total_requirements?.length"><td colspan="5">No active plan requirements are available.</td></tr></tbody></table></div>
    </section>

    <section v-if="mode === 'stock'" class="data-section" aria-labelledby="recent-heading">
      <div class="section-heading"><div><p class="eyebrow">Activity</p><h2 id="recent-heading">Recent records</h2></div></div>
      <div class="record-grid"><article v-for="receipt in snapshot?.recent_receipts || []" :key="receipt.name" class="record-strip"><span>RECEIPT</span><strong>{{ receipt.supplier }}</strong><small>{{ receipt.invoice_date }} · {{ receipt.status }}</small><b>R {{ number(receipt.total_amount) }}</b></article><article v-for="run in snapshot?.recent_runs || []" :key="run.name" class="record-strip"><span>PRODUCTION</span><strong>{{ run.finished_item }}</strong><small>{{ run.production_date }} · {{ run.docstatus ? "Posted" : "Draft" }}</small><b>{{ number(run.actual_output_qty) }} kg</b></article><p v-if="!snapshot?.recent_receipts?.length && !snapshot?.recent_runs?.length">No recent operational records.</p></div>
    </section>
  </section>
</template>

<style scoped>
.next-action-panel{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(0,1fr) minmax(15rem,.58fr) auto;align-items:center;gap:var(--spacing-m);padding:var(--spacing-l);border:var(--border-width-1) solid color-mix(in oklch,var(--theme-primary) 32%,var(--theme-border))!important;border-radius:var(--component-radius-block)!important;background:color-mix(in oklch,var(--theme-primary) 5%,var(--theme-surface-raised))!important;box-shadow:0 .75rem 2rem color-mix(in oklch,var(--theme-text) 7%,transparent)!important}.next-action-panel.is-overdue{border-color:color-mix(in oklch,var(--theme-error) 50%,var(--theme-border))!important;background:color-mix(in oklch,var(--theme-error) 7%,var(--theme-surface))!important}.next-action-panel.is-ready{border-color:color-mix(in oklch,var(--theme-success) 35%,var(--theme-border))!important;background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface))!important}.next-action-panel__marker{display:grid;place-items:center;width:3.5rem;height:3.5rem;border-radius:999px;background:var(--theme-primary);color:var(--theme-primary-foreground);font-size:var(--font-size-2);font-weight:var(--font-weight-700)}.next-action-panel.is-overdue .next-action-panel__marker{background:var(--theme-error)}.next-action-panel.is-ready .next-action-panel__marker{background:var(--theme-success)}.next-action-panel__message{min-width:0}.next-action-panel__topline{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-xs)}.next-action-panel h2{margin:var(--spacing-2xs) 0 0;font-size:var(--font-size-2)}.next-action-panel p{margin:var(--spacing-3xs) 0 0}.next-action-panel p:not(.panel-index),.next-action-panel small{color:var(--theme-text-muted)}.next-action-panel__steps{padding-left:var(--spacing-m);border-left:var(--border-width-1) solid var(--theme-border)}.next-action-panel__steps ol{margin:var(--spacing-2xs) 0 0;padding-left:var(--spacing-m);color:var(--theme-text-muted)}.next-action-panel__actions{display:grid;gap:var(--spacing-xs)}.queue-indicator{min-height:2rem;padding:var(--spacing-3xs) var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:999px;background:var(--theme-surface-raised);color:var(--theme-text-muted);font:inherit;font-size:var(--font-size--2);cursor:pointer}.queue-indicator:hover{border-color:color-mix(in oklch,var(--theme-primary) 38%,var(--theme-border));color:var(--theme-text)}.calendar-section{min-height:40rem}.operations-calendar{height:34rem;min-width:0}.calendar-event-detail{display:grid;gap:var(--spacing-xs);min-width:min(22rem,80vw);padding:var(--spacing-s)}.calendar-event-detail strong{font-size:var(--font-size-0)}.calendar-event-detail small,.calendar-event-detail p{margin:0;color:var(--theme-text-muted)}.inline-action-editor{display:grid;gap:var(--spacing-xs);padding-top:var(--spacing-xs);border-top:var(--border-width-1) solid var(--theme-border)}.custom-action-form{display:grid;gap:var(--spacing-s)}.custom-action-form__fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:start;gap:var(--spacing-xs)}.container-stock-position{display:grid;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.container-stock-position h3{margin:0}.container-stock-position td small{display:block;color:var(--theme-text-muted)}
@media(max-width:54rem){.next-action-panel{grid-template-columns:auto minmax(0,1fr)}.next-action-panel__steps,.next-action-panel__actions{grid-column:1/-1}.next-action-panel__steps{padding-left:0;border-left:0}.operations-calendar{height:30rem;min-width:0}.calendar-section{min-width:0;overflow-x:hidden}.custom-action-form__fields{grid-template-columns:1fr}}
.container-movement-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto;align-items:end;gap:var(--spacing-xs);margin:var(--spacing-s) 0;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}
@media(max-width:54rem){.container-movement-form{grid-template-columns:1fr}.container-movement-form :deep(button){width:100%}}
.dashboard-header{align-items:end}.dashboard-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--spacing-m)}.financial-panel,.operating-panel,.readiness-panel,.activity-panel,.action-panel,.dashboard-empty__card{border:var(--border-width-1) solid var(--theme-border)!important;border-radius:var(--component-radius-block)!important;background:var(--theme-surface)!important;box-shadow:0 1px 2px color-mix(in oklch,var(--theme-text) 5%,transparent)!important}.financial-panel,.operating-panel,.readiness-panel,.activity-panel,.action-panel{padding:var(--spacing-m)}.financial-panel{grid-column:span 8}.operating-panel{grid-column:span 4}.readiness-panel,.activity-panel{grid-column:span 6}.financial-panel__header,.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-m)}.financial-panel__header h2,.operating-panel h2,.readiness-panel h2,.activity-panel h2,.action-panel h2,.dashboard-empty__card h2{margin:var(--spacing-3xs) 0;font:var(--font-weight-700) var(--font-size-1)/1.3 var(--font-family-b)}.financial-panel__header p:not(.panel-index),.action-panel p:not(.panel-index),.dashboard-empty__card p:not(.panel-index){margin:var(--spacing-2xs) 0 0;color:var(--theme-text-muted)}.basis-control{display:flex;flex-wrap:wrap;gap:var(--spacing-2xs);padding:var(--spacing-3xs);overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.financial-panel__body{display:grid;gap:var(--spacing-m);margin-top:var(--spacing-m)}.financial-chart{height:20rem;min-width:0}.financial-chart :deep(.system-chart){display:block;width:100%;height:100%}.financial-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));align-content:start;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);overflow:hidden;background:var(--theme-surface-raised)}.financial-stats :deep(.system-stat){min-width:0;padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:last-child){border-right:0}.financial-stats :deep(.system-stat__value){font-size:var(--font-size-1)}.evidence-note{margin:var(--spacing-s) 0 0;padding:var(--spacing-xs) var(--spacing-s);border-radius:var(--component-radius-control);background:color-mix(in oklch,var(--theme-primary) 8%,var(--theme-surface-raised));color:var(--theme-text-muted);font-size:var(--font-size--1)}.operating-panel,.readiness-panel,.activity-panel{display:grid;align-content:start;gap:var(--spacing-s)}.operating-figures{display:grid;grid-template-columns:repeat(3,1fr);overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.operating-figures div{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.operating-figures div:last-child{border-right:0}.operating-figures strong{font-size:var(--font-size-1);font-variant-numeric:tabular-nums}.operating-figures span,.next-production span,.next-production small,.activity-item span,.activity-item small{color:var(--theme-text-muted);font-size:var(--font-size--2)}.next-production{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-s);border-left:3px solid var(--theme-primary);border-radius:0 var(--component-radius-control) var(--component-radius-control) 0;background:var(--theme-surface-raised)}.readiness-meter{height:.55rem;overflow:hidden;border-radius:999px;background:var(--theme-secondary)}.readiness-meter span{display:block;height:100%;border-radius:inherit;background:var(--theme-primary)}.readiness-figures strong{font-size:var(--font-size-0)}.panel-actions{display:flex;flex-wrap:wrap;gap:var(--spacing-xs);margin-top:auto}.activity-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.activity-item{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--spacing-3xs) var(--spacing-xs);padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.activity-item:last-child{border-right:0}.activity-item>span,.activity-item>small{grid-column:1/-1}.activity-item strong{min-width:0;overflow-wrap:anywhere}.activity-item b{font-variant-numeric:tabular-nums}.action-panel{display:grid;gap:var(--spacing-m);margin-top:var(--spacing-m)}.action-panel__grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.work-action{display:flex;min-width:0;flex-direction:column;align-items:flex-start;gap:var(--spacing-xs);padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.work-action:last-child{border-right:0}.work-action h3{margin:0;font-size:var(--font-size-0);line-height:1.35}.work-action>p:not(.panel-index){min-height:3.9em;margin:0;color:var(--theme-text-muted);font-size:var(--font-size--1);line-height:1.45}.work-action :deep(button){width:100%;margin-top:auto}.dashboard-empty{display:grid;grid-template-columns:minmax(0,42rem);justify-content:center}.dashboard-empty__card{display:grid;gap:var(--spacing-s);padding:var(--spacing-l)}
.financial-panel{grid-column:1/-1}.operating-panel,.readiness-panel,.activity-panel{grid-column:span 4}.readiness-figures{grid-template-columns:repeat(2,minmax(0,1fr))}.activity-list{grid-template-columns:1fr}.activity-item{border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.activity-item:last-child{border-bottom:0}
@media(max-width:72rem){.financial-panel{grid-column:1/-1}.operating-panel,.readiness-panel,.activity-panel{grid-column:span 6}.financial-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.financial-stats :deep(.system-stat){border-bottom:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:nth-child(2n)){border-right:0}.financial-stats :deep(.system-stat:nth-last-child(-n+2)){border-bottom:0}.action-panel__grid{grid-template-columns:repeat(2,minmax(0,1fr))}.work-action:nth-child(2n){border-right:0}.work-action:nth-child(-n+2){border-bottom:var(--border-width-1) solid var(--theme-border)}}
@media(max-width:54rem){.operating-panel,.readiness-panel,.activity-panel{grid-column:1/-1}.financial-chart{height:17rem}.activity-list{grid-template-columns:1fr}.activity-item{border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.activity-item:last-child{border-bottom:0}}
@media(max-width:44rem){.financial-panel,.operating-panel,.readiness-panel,.activity-panel,.action-panel,.dashboard-empty__card{padding:var(--spacing-s)}.financial-panel__header,.panel-heading{flex-direction:column}.basis-control{width:100%}.basis-control :deep(button){flex:1}.financial-stats{grid-template-columns:1fr}.financial-stats :deep(.system-stat){border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:nth-last-child(2)){border-bottom:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:last-child){border-bottom:0}.operating-figures{grid-template-columns:1fr}.operating-figures div{border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.operating-figures div:last-child{border-bottom:0}.action-panel__grid{grid-template-columns:1fr}.work-action,.work-action:nth-child(2n),.work-action:nth-child(-n+2){border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.work-action:last-child{border-bottom:0}.work-action>p:not(.panel-index){min-height:0}.panel-actions{display:grid;grid-template-columns:1fr}.panel-actions :deep(button){width:100%}.financial-chart{height:15rem}}
@media(max-width:44rem){.next-action-panel{grid-template-columns:1fr;padding:var(--spacing-s)}.next-action-panel__marker{width:2.75rem;height:2.75rem}.next-action-panel__topline{align-items:flex-start;flex-direction:column}.next-action-panel__steps,.next-action-panel>:deep(button){grid-column:auto}.financial-panel,.operating-panel,.readiness-panel,.activity-panel,.action-panel,.dashboard-empty__card{padding:var(--spacing-s)}.financial-panel__header,.panel-heading{flex-direction:column}.basis-control{width:100%}.basis-control :deep(button){flex:1}.financial-stats{grid-template-columns:1fr}.financial-stats :deep(.system-stat){border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:nth-last-child(2)){border-bottom:var(--border-width-1) solid var(--theme-border)}.financial-stats :deep(.system-stat:last-child){border-bottom:0}.operating-figures{grid-template-columns:1fr}.operating-figures div{border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.operating-figures div:last-child{border-bottom:0}.action-panel__grid{grid-template-columns:1fr}.work-action,.work-action:nth-child(2n),.work-action:nth-child(-n+2){border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.work-action:last-child{border-bottom:0}.work-action>p:not(.panel-index){min-height:0}.panel-actions{display:grid;grid-template-columns:1fr}.panel-actions :deep(button){width:100%}.financial-chart{height:15rem}}
.operating-figures div,.operating-figures strong{min-width:0}.operating-figures strong{overflow-wrap:anywhere}
.desyium-block__visually-hidden{position:fixed!important;inset:0 auto auto 0!important;display:block!important;width:1px!important;min-width:1px!important;max-width:1px!important;height:1px!important;min-height:1px!important;max-height:1px!important;margin:0!important;padding:0!important;overflow:hidden!important;clip-path:inset(50%)!important;white-space:nowrap!important;contain:strict!important;border:0!important}
.desyium-block__visually-hidden :is(caption,thead,tbody,tr,th,td){display:block!important;width:1px!important;min-width:0!important;max-width:1px!important;height:1px!important;min-height:0!important;max-height:1px!important;margin:0!important;padding:0!important;overflow:hidden!important;border:0!important}
</style>
