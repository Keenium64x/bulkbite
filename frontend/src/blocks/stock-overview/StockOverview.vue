<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { SystemAccordion, SystemAccordionContent, SystemAccordionItem, SystemAccordionTrigger, SystemBadge, SystemCalendar, SystemCard, SystemDatePicker, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton, SystemScanCodeField, SystemSelect, SystemTextarea } from "@/desyium"
import { createCustomOperationalAction, recordContainerMovement, updateOperationalAction } from "@/resources/api"

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
const actionBusy = ref("")
const actionEditors = ref({})
const customActionOpen = ref(false)
const customActionBusy = ref(false)
const customAction = ref({ title: "", due_date: "", consequence_note: "", target_section: "operations", notes: "" })
const containerBusy = ref(false)
const containerMovement = ref({ container_asset: "", movement_type: "", customer_reference: "", notes: "" })

const itemOptions = computed(() => (props.inventory?.items || []).map((item) => ({ label: item.item_name, value: item.item_code })))
const requirementsByItem = computed(() => new Map((props.plan?.total_requirements || []).map((item) => [item.item_code, item])))
const stockRows = computed(() => {
  const rows = new Map((props.inventory?.items || []).map((item) => [item.item_code, { ...item, requirement: requirementsByItem.value.get(item.item_code) || null }]))
  for (const requirement of props.plan?.total_requirements || []) {
    if (rows.has(requirement.item_code)) continue
    rows.set(requirement.item_code, {
      item_code: requirement.item_code,
      item_name: requirement.item_name,
      actual_qty: requirement.available_qty || 0,
      stock_uom: requirement.uom,
      valuation_rate: 0,
      stock_value: 0,
      requirement,
    })
  }
  return [...rows.values()]
})
const nextWeek = computed(() => props.plan?.next_production?.row || props.plan?.rows?.[0])
const stockEnough = computed(() => (props.plan?.total_requirements || []).filter((item) => item.shortage_qty <= 0).length)
const requirementCount = computed(() => (props.plan?.total_requirements || []).length)
const currentShortageCount = computed(() => Math.max(requirementCount.value - stockEnough.value, 0))
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
    key: "stock",
    eyebrow: "Receive",
    title: "Record food that arrived",
    detail: "Count what came in and reconcile it into stock.",
    action: "Reconcile stock",
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
])

function submitScan(code) { if (String(code || "").trim()) emit("scan", String(code).trim()) }
function assignCode() { if (mappingItem.value && props.scanResult?.scan_code) emit("map-scan", mappingItem.value, props.scanResult.scan_code) }
function number(value, digits = 2) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: digits }) }
function dateLabel(value) { return value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "No date" }
function money(value) { return `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
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
      <div><p class="eyebrow">Dashboard</p><h1>BulkBite at a glance</h1><p>See current stock position and move straight to the next job.</p></div>
      <SystemBadge>{{ plan?.customer_demand?.total_customers || 0 }} customers planned</SystemBadge>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="loading && !inventory" class="state-message" role="status">Loading current stock...</div>

    <template v-if="mode === 'dashboard'">
      <div v-if="!plan" class="dashboard-empty">
        <SystemCard class="dashboard-empty__card"><p class="panel-index">Start here</p><h2>Set the current customer and meal direction</h2><p>The Dashboard tracks stock and buying as soon as a plan exists.</p><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'planning')">Set direction</SystemOperationalButton></SystemCard>
      </div>

      <div v-else class="dashboard-grid">
		<SystemCard v-if="primaryAction" class="next-action-panel" :class="`is-${primaryAction.severity}`">
		  <div class="next-action-panel__marker" aria-hidden="true"><span>{{ primaryAction.severity === 'ready' ? '✓' : '!' }}</span></div>
		  <div class="next-action-panel__message"><div class="next-action-panel__topline"><p class="panel-index">What needs to happen next</p><button type="button" class="queue-indicator" @click="emit('open-workflow', 'operations')">{{ actionQueueCount }} {{ actionQueueCount === 1 ? 'action' : 'actions' }} waiting</button></div><h2>{{ primaryAction.title }}</h2><p>{{ primaryAction.reason }}</p><small v-if="primaryAction.due_date">Due {{ dateLabel(primaryAction.due_date) }}</small></div>
		  <div class="next-action-panel__steps" v-if="primaryAction.recovery_steps?.length"><strong>Recovery steps</strong><ol><li v-for="step in primaryAction.recovery_steps" :key="step">{{ step }}</li></ol></div>
		  <div class="next-action-panel__actions"><SystemOperationalButton variant="solid" @click="emit('open-workflow', primaryAction.action_section)">{{ primaryAction.action_label }}</SystemOperationalButton><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'operations')">Operations calendar</SystemOperationalButton></div>
		</SystemCard>

        <SystemAccordion type="multiple" :default-value="['direction']" class="operating-panel--full">
          <SystemAccordionItem value="direction" class="operating-panel">
          <SystemAccordionTrigger class="dashboard-panel__trigger">
            <div><span>Current direction</span><strong>{{ plan.plan_title }}</strong></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="operating-panel__content">
          <div class="operating-figures"><div><strong>{{ plan.customer_demand.total_customers }}</strong><span>customers</span></div><div><strong>{{ number(plan.customer_demand.weekly_output_qty, 1) }} kg</strong><span>food per week</span></div><div><strong>{{ currentShortageCount }}</strong><span>items to buy</span></div></div>
          <div class="next-production"><span>Next production</span><strong>{{ nextWeek?.finished_item_name || "No meal scheduled" }}</strong><small v-if="nextWeek">Meal {{ nextWeek.week_number }} · {{ number(nextWeek.planned_output_qty, 1) }} kg planned</small></div>
          <SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Update direction</SystemOperationalButton>
          </SystemAccordionContent>
          </SystemAccordionItem>
        </SystemAccordion>

      </div>

      <SystemAccordion v-if="plan" type="multiple" :default-value="['next-work']">
        <SystemAccordionItem value="next-work" class="action-panel">
        <SystemAccordionTrigger class="dashboard-panel__trigger">
          <div><span>Next work</span><strong>Move the kitchen forward</strong></div>
        </SystemAccordionTrigger>
        <SystemAccordionContent class="action-panel__content">
        <div class="action-panel__grid"><article v-for="work in nextWork" :key="work.key" class="work-action"><p class="panel-index">{{ work.eyebrow }}</p><h3>{{ work.title }}</h3><p>{{ work.detail }}</p><SystemOperationalButton :variant="work.variant" :disabled="work.disabled" @click="emit('open-workflow', work.key)">{{ work.action }}</SystemOperationalButton></article></div>
        </SystemAccordionContent>
        </SystemAccordionItem>
      </SystemAccordion>
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
	    <SystemAccordion v-if="mode === 'stock'" type="multiple" :default-value="['current-stock']" class="stock-sections">
	      <SystemAccordionItem value="current-stock" class="data-section stock-section">
	        <SystemAccordionTrigger class="stock-section__trigger">
	          <div class="section-heading"><div><p class="eyebrow">Ingredients</p><h2 id="stock-heading">Current stock</h2><p>Look up a code, review on-hand stock, and compare it with the active plan.</p></div><SystemBadge>{{ inventory?.location || "Ingredients" }}</SystemBadge></div>
	        </SystemAccordionTrigger>
	        <SystemAccordionContent class="stock-section__content">
	          <div class="stock-lookup">
	            <SystemScanCodeField v-model="scanCode" :busy="loading" autofocus @scan="submitScan" />
	            <div v-if="scanResult?.matched" class="scan-result" aria-live="polite"><SystemBadge class="status-badge">MATCHED</SystemBadge><strong>{{ scanResult.item_name }}</strong><span>{{ scanResult.item_code }} · {{ scanResult.uom }}</span></div>
	            <div v-else-if="scanResult && !scanResult.matched" class="scan-result scan-result--unknown" aria-live="polite"><SystemBadge>NOT MAPPED</SystemBadge><strong>{{ scanResult.scan_code }}</strong><span>{{ scanResult.reason }}</span><SystemLinkedRecordField v-model="mappingItem" label="Assign to item" :options="itemOptions" placeholder="Choose an ingredient" create-label="Add item" manage-label="Manage items" @create="router.push({ name: 'AuxiliaryRecordCreate', params: { doctype: 'BulkBite Item' } })" @manage="router.push({ name: 'BulkBiteSetupList', params: { doctype: 'BulkBite Item' } })" /><SystemOperationalButton variant="outline" :disabled="!mappingItem" @click="assignCode">Save code mapping</SystemOperationalButton></div>
	          </div>
	          <div class="table-wrap"><table><thead><tr><th>Ingredient</th><th>On hand</th><th>Planned need</th><th>Unit</th></tr></thead><tbody><tr v-for="item in stockRows" :key="item.item_code" :class="item.requirement?.shortage_qty > 0 ? 'is-short' : item.requirement ? 'is-ready' : ''"><td><strong>{{ item.item_name }}</strong><small>{{ item.item_code }}</small></td><td class="number-cell"><strong>{{ number(item.actual_qty, 3) }}</strong><small v-if="item.requirement?.shortage_qty > 0">{{ number(item.requirement.shortage_qty, 3) }} short</small><small v-else-if="item.requirement">Enough for the plan</small></td><td class="number-cell">{{ item.requirement ? number(item.requirement.required_qty, 3) : "Not planned" }}</td><td>{{ item.stock_uom }}</td></tr><tr v-if="!stockRows.length"><td colspan="4">No ingredient records are available.</td></tr></tbody></table></div>
	        </SystemAccordionContent>
	      </SystemAccordionItem>
	    </SystemAccordion>
  </section>
</template>

<style scoped>
.stock-sections{display:grid;gap:var(--spacing-s);margin-top:var(--spacing-m)}
.stock-section{overflow:hidden}
.stock-section__trigger{width:100%;text-align:left;text-decoration:none!important}
.stock-section__trigger .section-heading{width:100%;padding-right:var(--spacing-xs)}
.stock-section__content{display:grid;gap:var(--spacing-m)}
.stock-section tbody tr.is-short td{background:color-mix(in oklch,var(--theme-error) 7%,var(--theme-surface-raised))}.stock-section tbody tr.is-ready td{background:color-mix(in oklch,var(--theme-success) 7%,var(--theme-surface-raised))}.stock-section tbody tr.is-short td:first-child{box-shadow:inset .2rem 0 0 var(--theme-error)}.stock-section tbody tr.is-ready td:first-child{box-shadow:inset .2rem 0 0 var(--theme-success)}.stock-section tbody tr.is-short .number-cell small{color:var(--theme-error)}.stock-section tbody tr.is-ready .number-cell small{color:var(--theme-success)}
.stock-lookup{display:grid;grid-template-columns:minmax(16rem,28rem) minmax(0,1fr);align-items:start;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}
.stock-lookup .scan-result{margin:0}
@media(max-width:54rem){.stock-lookup{grid-template-columns:1fr}.stock-section__trigger,.stock-section__content{padding-inline:var(--spacing-s)}}
.next-action-panel{grid-column:1/-1;display:grid;grid-template-columns:auto minmax(0,1fr) minmax(15rem,.58fr) auto;align-items:center;gap:var(--spacing-m);padding:var(--spacing-l);border:var(--border-width-1) solid color-mix(in oklch,var(--theme-primary) 32%,var(--theme-border))!important;border-radius:var(--component-radius-block)!important;background:color-mix(in oklch,var(--theme-primary) 5%,var(--theme-surface-raised))!important;box-shadow:0 .75rem 2rem color-mix(in oklch,var(--theme-text) 7%,transparent)!important}.next-action-panel.is-overdue{border-color:color-mix(in oklch,var(--theme-error) 50%,var(--theme-border))!important;background:color-mix(in oklch,var(--theme-error) 7%,var(--theme-surface))!important}.next-action-panel.is-ready{border-color:color-mix(in oklch,var(--theme-success) 35%,var(--theme-border))!important;background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface))!important}.next-action-panel__marker{display:grid;place-items:center;width:3.5rem;height:3.5rem;border-radius:999px;background:var(--theme-primary);color:var(--theme-primary-foreground);font-size:var(--font-size-2);font-weight:var(--font-weight-700)}.next-action-panel.is-overdue .next-action-panel__marker{background:var(--theme-error)}.next-action-panel.is-ready .next-action-panel__marker{background:var(--theme-success)}.next-action-panel__message{min-width:0}.next-action-panel__topline{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-xs)}.next-action-panel h2{margin:var(--spacing-2xs) 0 0;font-size:var(--font-size-2)}.next-action-panel p{margin:var(--spacing-3xs) 0 0}.next-action-panel p:not(.panel-index),.next-action-panel small{color:var(--theme-text-muted)}.next-action-panel__steps{padding-left:var(--spacing-m);border-left:var(--border-width-1) solid var(--theme-border)}.next-action-panel__steps ol{margin:var(--spacing-2xs) 0 0;padding-left:var(--spacing-m);color:var(--theme-text-muted)}.next-action-panel__actions{display:grid;gap:var(--spacing-xs)}.queue-indicator{min-height:2rem;padding:var(--spacing-3xs) var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:999px;background:var(--theme-surface-raised);color:var(--theme-text-muted);font:inherit;font-size:var(--font-size--2);cursor:pointer}.queue-indicator:hover{border-color:color-mix(in oklch,var(--theme-primary) 38%,var(--theme-border));color:var(--theme-text)}.calendar-section{min-height:40rem}.operations-calendar{height:34rem;min-width:0}.calendar-event-detail{display:grid;gap:var(--spacing-xs);min-width:min(22rem,80vw);padding:var(--spacing-s)}.calendar-event-detail strong{font-size:var(--font-size-0)}.calendar-event-detail small,.calendar-event-detail p{margin:0;color:var(--theme-text-muted)}.inline-action-editor{display:grid;gap:var(--spacing-xs);padding-top:var(--spacing-xs);border-top:var(--border-width-1) solid var(--theme-border)}.custom-action-form{display:grid;gap:var(--spacing-s)}.custom-action-form__fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:start;gap:var(--spacing-xs)}.container-stock-position{display:grid;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.container-stock-position h3{margin:0}.container-stock-position td small{display:block;color:var(--theme-text-muted)}
@media(max-width:54rem){.next-action-panel{grid-template-columns:auto minmax(0,1fr)}.next-action-panel__steps,.next-action-panel__actions{grid-column:1/-1}.next-action-panel__steps{padding-left:0;border-left:0}.operations-calendar{height:30rem;min-width:0}.calendar-section{min-width:0;overflow-x:hidden}.custom-action-form__fields{grid-template-columns:1fr}}
.container-movement-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) auto;align-items:end;gap:var(--spacing-xs);margin:var(--spacing-s) 0;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}
@media(max-width:54rem){.container-movement-form{grid-template-columns:1fr}.container-movement-form :deep(button){width:100%}}
.dashboard-header{align-items:end}.dashboard-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--spacing-m)}.dashboard-empty__card{border:var(--border-width-1) solid var(--theme-border)!important;border-radius:var(--component-radius-block)!important;background:var(--theme-surface)!important;box-shadow:0 1px 2px color-mix(in oklch,var(--theme-text) 5%,transparent)!important}.operating-panel--full{grid-column:1/-1}.operating-panel h2,.action-panel h2,.dashboard-empty__card h2{margin:var(--spacing-3xs) 0;font:var(--font-weight-700) var(--font-size-1)/1.3 var(--font-family-b)}.action-panel p:not(.panel-index),.dashboard-empty__card p:not(.panel-index){margin:var(--spacing-2xs) 0 0;color:var(--theme-text-muted)}.evidence-note{margin:var(--spacing-s) 0 0;padding:var(--spacing-xs) var(--spacing-s);border-radius:var(--component-radius-control);background:color-mix(in oklch,var(--theme-primary) 8%,var(--theme-surface-raised));color:var(--theme-text-muted);font-size:var(--font-size--1)}.operating-panel__content{display:grid;align-content:start;gap:var(--spacing-s)}.operating-figures{display:grid;grid-template-columns:repeat(3,1fr);overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.operating-figures div{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.operating-figures div:last-child{border-right:0}.operating-figures strong{font-size:var(--font-size-1);font-variant-numeric:tabular-nums}.operating-figures span,.next-production span,.next-production small{color:var(--theme-text-muted);font-size:var(--font-size--2)}.next-production{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-s);border-left:3px solid var(--theme-primary);border-radius:0 var(--component-radius-control) var(--component-radius-control) 0;background:var(--theme-surface-raised)}.action-panel{margin-top:var(--spacing-m)}.action-panel__grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.work-action{display:flex;min-width:0;flex-direction:column;align-items:flex-start;gap:var(--spacing-xs);padding:var(--spacing-s);border-right:var(--border-width-1) solid var(--theme-border)}.work-action:last-child{border-right:0}.work-action h3{margin:0;font-size:var(--font-size-0);line-height:1.35}.work-action>p:not(.panel-index){min-height:3.9em;margin:0;color:var(--theme-text-muted);font-size:var(--font-size--1);line-height:1.45}.work-action :deep(button){width:100%;margin-top:auto}.dashboard-empty{display:grid;grid-template-columns:minmax(0,42rem);justify-content:center}.dashboard-empty__card{display:grid;gap:var(--spacing-s);padding:var(--spacing-l)}
@media(max-width:72rem){.action-panel__grid{grid-template-columns:repeat(2,minmax(0,1fr))}.work-action:nth-child(2n){border-right:0}.work-action:nth-child(-n+2){border-bottom:var(--border-width-1) solid var(--theme-border)}}
@media(max-width:44rem){.dashboard-empty__card{padding:var(--spacing-s)}.operating-figures{grid-template-columns:1fr}.operating-figures div{border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.operating-figures div:last-child{border-bottom:0}.action-panel__grid{grid-template-columns:1fr}.work-action,.work-action:nth-child(2n),.work-action:nth-child(-n+2){border-right:0;border-bottom:var(--border-width-1) solid var(--theme-border)}.work-action:last-child{border-bottom:0}.work-action>p:not(.panel-index){min-height:0}}
@media(max-width:44rem){.next-action-panel{grid-template-columns:1fr;padding:var(--spacing-s)}.next-action-panel__marker{width:2.75rem;height:2.75rem}.next-action-panel__topline{align-items:flex-start;flex-direction:column}.next-action-panel__steps,.next-action-panel>:deep(button){grid-column:auto}}
.dashboard-panel__trigger{width:100%;text-align:left;text-decoration:none!important}.dashboard-panel__trigger>div{display:grid;gap:var(--spacing-3xs)}.dashboard-panel__trigger span{color:var(--theme-text-muted);font-size:var(--font-size--2);font-weight:var(--font-weight-600);letter-spacing:var(--font-letter-spacing-2);text-transform:uppercase}.dashboard-panel__trigger strong{font:var(--font-weight-700) var(--font-size-1)/1.3 var(--font-family-b)}
.operating-figures div,.operating-figures strong{min-width:0}.operating-figures strong{overflow-wrap:anywhere}
</style>
