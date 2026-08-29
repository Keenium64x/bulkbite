<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { SystemBadge, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton, SystemSelect } from "@/desyium"
import { calculateCapacityScenario, cancelProductionPlan, saveMonthlyProductionPlan } from "@/resources/api"
import { syncOfflineMutation } from "@/resources/api"
import { clearFormDraft, clearSyncOutcome, listQueuedMutations, loadFormDraft, loadSyncOutcome, offlineState, saveFormDraft } from "@/native/offlineStore"
import { syncDraftMutation } from "@/native/offlineSync"
import { runtimeConfig } from "@/config/runtime"
import { nativeState } from "@/native/lifecycle"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null }, mode: { type: String, default: "planning" } })
const emit = defineEmits(["changed", "open-employees"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const offlineNotice = ref("")
const formDirty = ref(false)
const queuedMutationId = ref("")
const queuedMutation = ref(null)
const draftLocked = computed(() => Boolean(queuedMutationId.value))
const form = reactive({ name: "", plan_title: "", status: "Active", customer_mix: [], plan_rows: [], purchase_routes: [], forecast_weeks: 4, default_team_template: "", capacity_windows: [], capacity_runs: [], forecast_customer_mix: [] })
const scenarioForecast = ref([])
let scenarioTimer
let hydrating = false
const planTypes = computed(() => props.snapshot?.options?.customer_plan_types || [])
const recipeOptions = computed(() => (props.snapshot?.options?.recipes || []).map(row => ({ label: row.recipe_name, value: row.name })))
const teamTemplates = computed(() => props.snapshot?.options?.team_templates || [])
const teamTemplateOptions = computed(() => teamTemplates.value.map(row => ({ label: row.template_name, value: row.name })))
const dayOptions = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(value => ({ label: value, value }))
const outputModeOptions = [{ label: "Auto balance remaining food", value: "Auto" }, { label: "Fixed deliberate output", value: "Fixed" }]
const allocationTypeOptions = ["Future Customers", "Internal Consumption", "Unallocated Buffer"].map(value => ({ label: value, value }))
const scenarioWeeks = computed(() => props.mode === "forecasting" ? Number(form.forecast_weeks || 8) : 4)
const scenarioTargetMix = computed(() => props.mode === "forecasting"
  ? form.forecast_customer_mix
  : form.customer_mix.map(row => ({ plan_type: row.plan_type, target_customers: Number(row.customer_count || 0), target_week: 1 })))
const totalCustomers = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0), 0))
const weeklyServings = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0), 0))
const weeklyKg = computed(() => roundQuantity(form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0) * Number(row.serving_size_g || 0) / 1000, 0)))
const capacitySummary = computed(() => {
  const totals = scenarioForecast.value.reduce((summary, row) => ({
    requiredOutputQty: summary.requiredOutputQty + Number(row.required_output_qty || 0),
    plannedOutputQty: summary.plannedOutputQty + Number(row.planned_output_qty || 0),
    scheduledElapsedHours: summary.scheduledElapsedHours + Number(row.scheduled_elapsed_hours || 0),
    scheduledTeamHours: summary.scheduledTeamHours + Number(row.scheduled_team_hours || 0),
    requiredTeamHours: summary.requiredTeamHours + Number(row.required_team_hours || 0),
    runCount: summary.runCount + Number(row.run_count || 0),
    underCapacityWeeks: summary.underCapacityWeeks + (row.status === "Under capacity" ? 1 : 0),
  }), { requiredOutputQty: 0, plannedOutputQty: 0, scheduledElapsedHours: 0, scheduledTeamHours: 0, requiredTeamHours: 0, runCount: 0, underCapacityWeeks: 0 })
  const teamHourDifference = roundQuantity(totals.scheduledTeamHours - totals.requiredTeamHours)
  const outputDifference = roundQuantity(totals.plannedOutputQty - totals.requiredOutputQty)
  return {
    ...totals,
    weeks: scenarioForecast.value.length,
    teamHourDifference,
    outputDifference,
    status: outputDifference < 0 || teamHourDifference < 0 ? "Under capacity" : outputDifference > 0 || teamHourDifference > 0 ? "Over capacity" : "At capacity",
  }
})
const workforceRows = computed(() => (props.plan?.workforce?.rows || []).map(row => {
  const requiredCapacity = row.capacity_basis === "Meals per Production Run" ? weeklyServings.value : row.capacity_basis === "Kg per Production Run" ? weeklyKg.value : row.capacity_basis === "Customers Served" ? totalCustomers.value : row.required_capacity
  const minutesPerUnit = Number(row.capacity_per_worker) > 0 ? Number(row.expected_hours_per_run || 0) * 60 / Number(row.capacity_per_worker) : 0
  const requiredTeamHours = requiredCapacity * minutesPerUnit / 60
  const availableHours = Number(row.available_worker_hours || 0)
  const hourDifference = availableHours - requiredTeamHours
  const averageHours = Number(row.active_workers || 0) ? availableHours / Number(row.active_workers) : 0
  const requiredWorkers = requiredTeamHours && averageHours ? Math.ceil(requiredTeamHours / averageHours) : 0
  return { ...row, required_capacity: requiredCapacity, required_team_hours: requiredTeamHours, required_workers: requiredWorkers, hour_difference: hourDifference, status: hourDifference < 0 ? "Under capacity" : hourDifference > 0 ? "Over capacity" : "At capacity" }
}))
const workforceSummary = computed(() => {
  const activeWorkers = workforceRows.value.reduce((sum, row) => sum + Number(row.active_workers || 0), 0)
  const availableHours = workforceRows.value.reduce((sum, row) => sum + Number(row.available_worker_hours || 0), 0)
  const actualMinutesPerKg = Number(props.plan?.workforce?.actual?.labour_minutes_per_kg || 0)
  const theoreticalMinutesPerKg = weeklyKg.value ? workforceRows.value.reduce((sum, row) => sum + Number(row.required_team_hours || 0), 0) * 60 / weeklyKg.value : 0
  const planningMinutesPerKg = actualMinutesPerKg || theoreticalMinutesPerKg
  const requiredTeamHours = weeklyKg.value * planningMinutesPerKg / 60
  const hoursPerWorker = activeWorkers ? availableHours / activeWorkers : 0
  const requiredWorkers = requiredTeamHours && hoursPerWorker ? Math.ceil(requiredTeamHours / hoursPerWorker) : workforceRows.value.reduce((sum, row) => sum + Number(row.required_workers || 0), 0)
  const hourDifference = availableHours - requiredTeamHours
  return {
    activeWorkers, requiredWorkers, hoursPerWorker, availableHours, requiredTeamHours, hourDifference,
    taktMinutesPerKg: weeklyKg.value ? availableHours * 60 / weeklyKg.value : 0,
    planningMinutesPerKg, planningBasis: actualMinutesPerKg ? "Actual rate" : "Theoretical rate",
    status: hourDifference < 0 ? "Under capacity" : hourDifference > 0 ? "Over capacity" : "At capacity",
  }
})

watch(() => [props.plan, props.snapshot], hydrate, { immediate: true, deep: true })
watch(() => [form.customer_mix, form.forecast_weeks, form.default_team_template, form.forecast_customer_mix, form.capacity_runs, props.mode], queueScenarioCalculation, { deep: true })
watch(form, value => {
  if (props.mode !== "planning" || hydrating || draftLocked.value) return
  formDirty.value = true
  if (runtimeConfig.isNative) persistLocalPlanDraft().catch(() => {})
}, { deep: true })
watch(() => nativeState.connected, connected => {
  if (connected) window.setTimeout(() => reconcileQueuedPlan().catch(() => {}), 1500)
})
watch(() => offlineState.lastSyncedAt, () => reconcileQueuedPlan().catch(() => {}))

function hydrate() {
  hydrating = true
  Object.assign(form, {
    name: props.plan?.name || "",
    plan_title: props.plan?.plan_title || "Current meal direction",
    status: props.plan?.status || "Active",
    customer_mix: planTypes.value.map(type => {
      const current = props.plan?.customer_mix?.find(row => row.plan_type === type.name)
      return { ...type, plan_type: type.name, customer_count: Number(current?.customer_count || 0) }
    }),
    plan_rows: Array.from({ length: 4 }, (_, index) => {
      const current = props.plan?.rows?.find(row => Number(row.week_number) === index + 1)
      return { week_number: index + 1, recipe: current?.recipe || "", finished_item: current?.finished_item || "", customer_required_output_qty: Number(current?.customer_required_output_qty || weeklyKg.value), extra_output_qty: Number(current?.extra_output_qty || 0), extra_allocation_type: current?.extra_allocation_type || "Future Customers", extra_allocation_reference: current?.extra_allocation_reference || "", planned_output_qty: Number(current?.planned_output_qty || weeklyKg.value) }
    }),
    purchase_routes: (props.snapshot?.options?.item_categories || []).map(category => {
      const current = props.plan?.purchase_routes?.find(row => row.item_category === category.name)
      return { item_category: category.name, supplier: current?.supplier || category.default_supplier || "", use_discounted_price: Boolean(current?.use_discounted_price) }
    }),
    forecast_weeks: props.mode === "forecasting" ? 8 : 4,
    default_team_template: props.plan?.capacity_plan?.default_team_template || "",
    capacity_windows: Array.from({ length: 4 }, (_, index) => {
      const saved = props.plan?.capacity_plan?.windows?.find(row => Number(row.week_number) === index + 1)
      return { week_number: index + 1, scheduled_elapsed_hours: Number(saved?.scheduled_elapsed_hours || 4), runs_per_week: Number(saved?.runs_per_week || 1), team_template: saved?.team_template || props.plan?.capacity_plan?.default_team_template || "" }
    }),
    capacity_runs: props.plan?.capacity_plan?.runs?.length
      ? props.plan.capacity_plan.runs.map(row => ({ ...row, output_mode: row.output_mode || "Auto", planned_output_qty: Number(row.planned_output_qty || props.plan?.rows?.find(item => Number(item.week_number) === Number(row.week_number))?.planned_output_qty || weeklyKg.value) }))
      : Array.from({ length: 4 }, (_, index) => ({ week_number: index + 1, run_number: 1, day_of_week: "Saturday", output_mode: "Auto", planned_output_qty: Number(props.plan?.rows?.[index]?.planned_output_qty || weeklyKg.value), scheduled_elapsed_hours: Number(props.plan?.capacity_plan?.windows?.[index]?.scheduled_elapsed_hours || 5), team_template: props.plan?.capacity_plan?.windows?.[index]?.team_template || props.plan?.capacity_plan?.default_team_template || "", planned_people: Number(props.plan?.capacity_plan?.windows?.[index]?.team_size || 0) })),
    forecast_customer_mix: planTypes.value.map(type => {
      const base = props.plan?.customer_mix?.find(row => row.plan_type === type.name)
      return { plan_type: type.name, target_customers: Number(base?.customer_count || 0), target_week: 8 }
    }),
  })
  scenarioForecast.value = []
  formDirty.value = false
  if (runtimeConfig.isNative && props.mode === "planning") {
    restoreLocalPlanDraft().then(() => reconcileQueuedPlan()).catch(() => {})
  }
  nextTick(() => { hydrating = false })
  queueScenarioCalculation()
}

async function restoreLocalPlanDraft() {
  const draft = await loadFormDraft("production-plan").catch(() => null)
  const payload = draft?.payload || draft
  if (!payload || payload.name !== form.name) return
  Object.assign(form, payload)
  queuedMutationId.value = draft.queuedMutationId || ""
  queuedMutation.value = draft.queuedMutation || null
  formDirty.value = true
  offlineNotice.value = queuedMutationId.value ? "Direction is saved on this device and waiting to sync." : "A newer draft saved on this device was restored."
}

async function persistLocalPlanDraft(payload = structuredClone(form)) {
  if (!runtimeConfig.isNative) return
  await saveFormDraft("production-plan", {
    payload,
    queuedMutationId: queuedMutationId.value,
    queuedMutation: queuedMutation.value,
  })
}

async function reconcileQueuedPlan(attempt = 0) {
  if (!queuedMutationId.value || !nativeState.connected) return
  const queue = await listQueuedMutations().catch(() => [])
  if (queue.some(mutation => mutation.clientMutationId === queuedMutationId.value)) {
    if (attempt < 8) window.setTimeout(() => reconcileQueuedPlan(attempt + 1).catch(() => {}), 1500)
    return
  }
  const resolution = offlineState.lastResolution?.clientMutationId === queuedMutationId.value ? offlineState.lastResolution : null
  const completed = offlineState.completedResults[queuedMutationId.value]
  const persisted = await loadSyncOutcome(queuedMutationId.value).catch(() => null)
  const serverWon = resolution?.action === "server" || persisted?.action === "server"
  let synchronized = resolution?.result || persisted?.result || completed || null
  if (!serverWon && !synchronized && queuedMutation.value) {
    const response = await syncOfflineMutation(queuedMutation.value)
    synchronized = response?.result || null
  }
  delete offlineState.completedResults[queuedMutationId.value]
  await clearSyncOutcome(queuedMutationId.value).catch(() => {})
  await clearFormDraft("production-plan").catch(() => {})
  queuedMutationId.value = ""
  queuedMutation.value = null
  formDirty.value = false
  offlineNotice.value = serverWon ? "The server direction was kept. Local changes were discarded." : synchronized ? "Direction synchronized with BulkBite." : "Direction synchronization finished."
  emit("changed")
}

function queueScenarioCalculation() {
  if (!form.customer_mix.length) return
  window.clearTimeout(scenarioTimer)
  scenarioTimer = window.setTimeout(calculateScenario, 250)
}

async function calculateScenario() {
  try {
    const result = await calculateCapacityScenario({
      current_mix: form.customer_mix,
      target_mix: scenarioTargetMix.value,
      forecast_weeks: scenarioWeeks.value,
      capacity_windows: form.capacity_windows.map(row => ({ ...row, team_size: templateSize(row.team_template || form.default_team_template) })),
      capacity_runs: form.capacity_runs.map(row => ({ ...row, team_template: row.team_template || form.default_team_template, planned_people: Number(row.planned_people || templateSize(row.team_template || form.default_team_template)) })),
      required_output_by_week: form.plan_rows.map(row => ({ week_number: row.week_number, required_output_qty: roundQuantity(weeklyKg.value + Number(row.extra_output_qty || 0)) })),
      labour_minutes_per_kg: Number(props.plan?.workforce?.planning_labour_minutes_per_kg || 0),
    })
    scenarioForecast.value = result.forecast || []
  } catch (exception) { error.value = exception.message }
}

function templateSize(name) { return Number(teamTemplates.value.find(row => row.name === name)?.team_size || 0) }
function addCapacityRun(weekNumber = 1) {
  const sameWeek = form.capacity_runs.filter(row => Number(row.week_number) === Number(weekNumber))
  form.capacity_runs.push({ week_number: Number(weekNumber), run_number: sameWeek.length + 1, day_of_week: "Saturday", output_mode: "Auto", planned_output_qty: 0, scheduled_elapsed_hours: 5, team_template: form.default_team_template, planned_people: templateSize(form.default_team_template) })
}
function removeCapacityRun(index) { form.capacity_runs.splice(index, 1) }
function applyDefaultTeam(row) {
  row.team_template = form.default_team_template
  row.planned_people = templateSize(form.default_team_template)
}
function changeCapacityRunTeam(row, value) { row.team_template = value; row.planned_people = templateSize(value) }

function openLinked(mode, doctype) {
  router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } })
}

async function savePlan() {
  error.value = ""
  if (form.plan_rows.some(row => !row.recipe)) return (error.value = "Choose all four meals in the repeating cycle.")
  busy.value = true
  try {
    const payload = {
      ...form,
      forecast_weeks: 4,
      forecast_customer_mix: form.customer_mix.map(row => ({ plan_type: row.plan_type, target_customers: Number(row.customer_count || 0), target_week: 1 })),
      location: "Ingredients",
      plan_rows: form.plan_rows.map(row => ({
        ...row,
        customer_required_output_qty: roundQuantity(weeklyKg.value),
        planned_output_qty: roundQuantity(weeklyKg.value + Number(row.extra_output_qty || 0)),
      })),
    }
    if (runtimeConfig.isNative) {
      const synced = await syncDraftMutation(syncOfflineMutation, "save_production_plan", payload, props.plan?.modified || null)
      if (synced.queued) {
        queuedMutationId.value = synced.mutation.clientMutationId
        queuedMutation.value = synced.mutation
        await persistLocalPlanDraft(payload)
        offlineNotice.value = synced.conflict ? "The server direction changed. Choose which version to keep." : "Direction saved on this device. It will sync when BulkBite reconnects."
      } else {
        await clearFormDraft("production-plan").catch(() => {})
        formDirty.value = false
        offlineNotice.value = ""
        emit("changed")
      }
    } else await saveMonthlyProductionPlan(payload)
    if (!runtimeConfig.isNative) {
      await clearFormDraft("production-plan").catch(() => {})
      formDirty.value = false
      emit("changed")
    }
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function cancelDirection() {
  if (!form.name || !window.confirm("Cancel this meal direction? Unposted production drafts will be discarded. Posted history will remain.")) return
  busy.value = true
  error.value = ""
  try {
    await cancelProductionPlan(form.name)
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

function roundQuantity(value) { return Math.round(Number(value || 0) * 1000) / 1000 }
function number(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 1 }) }
</script>

<template>
  <section data-block="monthly-planning" class="workflow-block" :data-offline-draft-dirty="formDirty || undefined" :inert="draftLocked || undefined" :aria-busy="draftLocked || undefined">
    <header class="workflow-header"><div><p class="eyebrow">{{ mode === 'forecasting' ? 'Forecasting' : 'Planning' }}</p><h1>{{ mode === 'forecasting' ? 'Test future production capacity' : 'Set the current meal direction' }}</h1><p>{{ mode === 'forecasting' ? 'Try customer growth, cooking days, hours, and crew sizes before changing the active plan.' : 'Keep customer numbers current and choose the four meals that repeat. Future buying and production recalculate whenever this direction changes.' }}</p></div><SystemBadge>{{ mode === 'forecasting' ? 'SCENARIO' : form.name ? 'ACTIVE DIRECTION' : 'NEW DIRECTION' }}</SystemBadge></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="offlineNotice" class="state-message" role="status">{{ offlineNotice }}</div>

    <section v-if="mode === 'planning'" class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Customers</p><h2>Current customer mix</h2><p>Update these counts whenever customers change. Serving sizes and meal frequency come from customer plan records.</p></div><SystemBadge>{{ totalCustomers }} customers</SystemBadge></div>
      <div class="field-grid">
        <SystemFormControl v-model="form.plan_title" label="Direction name" size="lg" />
      </div>
      <div class="plan-mix">
        <article v-for="row in form.customer_mix" :key="row.plan_type" class="plan-mix__row">
          <div><strong>{{ row.plan_type }}</strong><small>{{ number(row.serving_size_g) }} g per meal · {{ row.meals_per_day }} meals/day</small></div>
          <SystemFormControl v-model="row.customer_count" type="number" label="Customers" min="0" step="1" size="lg" />
          <div class="calculated-value"><span>Food per week</span><strong>{{ number(Number(row.customer_count || 0) * row.meals_per_day * row.days_per_week * row.serving_size_g / 1000) }} kg</strong></div>
        </article>
      </div>
      <div class="metric-board"><div><strong>{{ totalCustomers }}</strong><span>customers</span></div><div><strong>{{ weeklyServings }}</strong><span>portions per week</span></div><div><strong>{{ number(weeklyKg) }} kg</strong><span>food per week</span></div><div><strong>{{ number(weeklyKg * 4) }} kg</strong><span>one full cycle</span></div></div>
    </section>

    <section v-if="mode === 'planning'" class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Meal cycle</p><h2>Choose the four repeating meals</h2><p>Production advances through these meals in order, then starts again at meal one.</p></div></div>
      <div class="week-grid">
        <article v-for="row in form.plan_rows" :key="row.week_number" class="week-card">
          <SystemBadge>MEAL {{ row.week_number }}</SystemBadge>
          <SystemLinkedRecordField v-model="row.recipe" label="Meal recipe" :options="recipeOptions" placeholder="Choose this meal" create-label="Add recipe" manage-label="Manage recipes" @create="openLinked('create', 'BulkBite Recipe')" @manage="openLinked('list', 'BulkBite Recipe')" />
          <div class="calculated-field"><span>Customer food required</span><strong>{{ number(weeklyKg) }} kg</strong></div>
          <SystemFormControl v-model="row.extra_output_qty" type="number" min="0" step="0.1" label="Extra food to make (kg)" />
          <SystemSelect v-model="row.extra_allocation_type" label="Extra food for" :options="allocationTypeOptions" />
          <SystemFormControl v-model="row.extra_allocation_reference" label="Week, person, or reason" />
          <p><strong>{{ number(weeklyKg + Number(row.extra_output_qty || 0)) }} kg</strong> total planned output</p>
        </article>
      </div>
    </section>

    <template v-if="mode === 'planning' || mode === 'forecasting'">
      <section class="form-section capacity-plan-section">
        <div class="section-heading"><div><p class="eyebrow">{{ mode === 'planning' ? 'Capacity baseline' : 'Hypothetical scenario' }}</p><h2>{{ mode === 'planning' ? 'Set the current production capacity' : 'Test a future production schedule' }}</h2><p>{{ mode === 'planning' ? 'Choose the real team and cooking sessions available for the current meal direction. These values are saved when you update the direction.' : 'Start from the saved Planning baseline, then change future customers, cooking days, hours, and people without changing the current direction.' }}</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="emit('open-employees', mode)">Manage employees</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="openLinked('create', 'BulkBite Team Template')">Create team</SystemOperationalButton></div></div>
        <div class="forecast-settings" :class="{ 'forecast-settings--single': mode === 'planning' }">
          <SystemFormControl v-if="mode === 'forecasting'" v-model="form.forecast_weeks" type="number" min="1" step="1" label="Weeks to forecast" />
          <SystemLinkedRecordField v-model="form.default_team_template" label="Default team template" :options="teamTemplateOptions" placeholder="Choose the usual team" create-label="Create team template" manage-label="Manage team templates" @create="openLinked('create', 'BulkBite Team Template')" @manage="openLinked('list', 'BulkBite Team Template')" />
        </div>
        <div v-if="mode === 'forecasting'" class="forecast-mix"><article v-for="row in form.forecast_customer_mix" :key="row.plan_type"><div><strong>{{ row.plan_type }}</strong><small>Customer count reached by the target week</small></div><SystemFormControl v-model="row.target_customers" type="number" min="0" step="1" label="Future customers" /><SystemFormControl v-model="row.target_week" type="number" min="1" step="1" label="Reach by week" /></article></div>
      </section>

      <section class="form-section">
        <div class="section-heading"><div><p class="eyebrow">Cooking schedule</p><h2>{{ mode === 'planning' ? 'Enter the runs currently available' : 'Change the runs for this scenario' }}</h2><p>Each row is one cooking session. A week can have one run or several runs with different hours and crew sizes.</p></div><SystemOperationalButton variant="solid" @click="addCapacityRun(1)">Add run</SystemOperationalButton></div>
        <div class="capacity-run-list">
          <article v-for="(row, index) in form.capacity_runs" :key="index">
            <SystemFormControl v-model="row.week_number" type="number" min="1" max="4" step="1" label="Cycle week" />
            <SystemSelect v-model="row.day_of_week" label="Day" :options="dayOptions" />
            <SystemSelect v-model="row.output_mode" label="Output allocation" :options="outputModeOptions" />
            <SystemFormControl v-model="row.planned_output_qty" type="number" min="0" step="0.1" :label="row.output_mode === 'Fixed' ? 'Fixed output (kg)' : 'Maximum output (kg)'" />
            <SystemFormControl v-model="row.scheduled_elapsed_hours" type="number" min="0.1" step="0.1" label="Cooking hours" />
            <SystemLinkedRecordField :model-value="row.team_template" label="Team template" :options="teamTemplateOptions" placeholder="Use default team" create-label="Create team template" manage-label="Manage team templates" @create="openLinked('create', 'BulkBite Team Template')" @manage="openLinked('list', 'BulkBite Team Template')" @update:model-value="changeCapacityRunTeam(row, $event)" />
            <SystemFormControl v-model="row.planned_people" type="number" min="1" step="1" label="People working" />
            <div class="run-actions"><SystemOperationalButton v-if="form.default_team_template" variant="ghost" @click="applyDefaultTeam(row)">Use default</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="removeCapacityRun(index)">Remove</SystemOperationalButton></div>
          </article>
        </div>
      </section>

      <section class="data-section workforce-section">
        <div class="section-heading"><div><p class="eyebrow">{{ mode === 'planning' ? 'Current theoretical capacity' : 'Hypothetical capacity' }}</p><h2>{{ mode === 'planning' ? 'Can the current plan make enough food?' : 'Would this future schedule make enough food?' }}</h2><p>The overall result compares all food and team-hours across the full period. The weekly breakdown then shows where the time is available or short.</p></div><SystemBadge :theme="capacitySummary.status === 'Under capacity' ? 'red' : 'green'">{{ capacitySummary.status === 'Under capacity' ? 'Overall capacity gap' : 'Overall capacity ready' }}</SystemBadge></div>
        <article class="capacity-period-summary" :class="capacitySummary.status === 'Under capacity' ? 'is-under' : 'is-ready'">
          <div class="forecast-week-heading"><div><span>{{ mode === 'planning' ? 'Full four-week cycle' : `${capacitySummary.weeks}-week scenario` }}</span><strong>{{ capacitySummary.status }}</strong></div><SystemBadge :theme="capacitySummary.status === 'Under capacity' ? 'red' : 'green'">{{ capacitySummary.weeks }} {{ capacitySummary.weeks === 1 ? 'week' : 'weeks' }}</SystemBadge></div>
          <div class="capacity-equation"><strong>{{ number(capacitySummary.plannedOutputQty) }} kg assigned</strong><span>−</span><strong>{{ number(capacitySummary.requiredOutputQty) }} kg needed</strong><span>=</span><strong>{{ number(Math.abs(capacitySummary.outputDifference)) }} kg {{ capacitySummary.outputDifference < 0 ? 'short' : capacitySummary.outputDifference > 0 ? 'spare' : 'balanced' }}</strong></div>
          <div class="metric-board"><div><strong>{{ number(capacitySummary.requiredOutputQty) }} kg</strong><span>total food needed</span></div><div><strong>{{ number(capacitySummary.plannedOutputQty) }} kg</strong><span>food assigned to runs</span></div><div><strong>{{ number(capacitySummary.scheduledElapsedHours) }} h</strong><span>planned cooking time</span></div><div><strong>{{ number(capacitySummary.scheduledTeamHours) }} h</strong><span>total team-hours planned</span></div><div><strong>{{ number(capacitySummary.requiredTeamHours) }} h</strong><span>total team-hours needed</span></div><div><strong>{{ capacitySummary.runCount }}</strong><span>production runs</span></div><div><strong>{{ capacitySummary.underCapacityWeeks }}</strong><span>weeks with a gap</span></div></div>
          <p v-if="capacitySummary.status === 'Under capacity'">The full period is {{ number(Math.abs(capacitySummary.teamHourDifference)) }} team-hours short. Use the weekly breakdown to see where more time or people are needed.</p><p v-else-if="capacitySummary.underCapacityWeeks">The full period has {{ number(capacitySummary.teamHourDifference) }} spare team-hours overall, but {{ capacitySummary.underCapacityWeeks }} {{ capacitySummary.underCapacityWeeks === 1 ? 'week is' : 'weeks are' }} still under capacity. Move or add time in the weekly schedule.</p><p v-else-if="capacitySummary.status === 'Over capacity'">The full period has {{ number(capacitySummary.teamHourDifference) }} spare team-hours and every displayed week is covered.</p><p v-else>The available team-hours match the total food requirement.</p>
        </article>
        <div class="capacity-breakdown-heading"><div><p class="eyebrow">Weekly breakdown</p><h3>Where the total comes from</h3></div><SystemBadge>{{ capacitySummary.weeks }} {{ capacitySummary.weeks === 1 ? 'week' : 'weeks' }}</SystemBadge></div>
        <div class="forecast-week-list">
          <article v-for="row in scenarioForecast" :key="row.week_number" :class="row.capacity_state === 'idle' ? 'is-idle' : row.capacity_state === 'under' ? 'is-under' : 'is-ready'">
            <div class="forecast-week-heading"><div><span>Week {{ row.week_number }}</span><strong>{{ row.status }}</strong></div><SystemBadge :theme="row.capacity_state === 'under' ? 'red' : row.capacity_state === 'ready' ? 'green' : undefined">{{ row.run_count ? `${row.run_count} ${row.run_count === 1 ? 'run' : 'runs'}` : 'No run needed' }}</SystemBadge></div>
            <div class="capacity-equation"><strong v-if="row.opening_output_balance_qty">Opening food balance {{ row.opening_output_balance_qty < 0 ? '−' : '+' }}{{ number(Math.abs(row.opening_output_balance_qty)) }} kg</strong><span v-if="row.opening_output_balance_qty">+</span><strong>{{ number(row.planned_output_qty) }} kg assigned</strong><span>−</span><strong>{{ number(row.required_output_qty) }} kg required</strong><span>=</span><strong>{{ number(Math.abs(row.closing_output_balance_qty)) }} kg {{ row.closing_output_balance_qty < 0 ? 'short' : row.closing_output_balance_qty > 0 ? 'spare' : 'balanced' }} after week</strong></div>
            <div class="metric-board"><div><strong>{{ number(row.required_output_qty) }} kg</strong><span>food required</span></div><div><strong>{{ number(row.planned_output_qty) }} kg</strong><span>food assigned</span></div><div><strong>{{ number(row.scheduled_elapsed_hours) }} h</strong><span>cooking time planned</span></div><div><strong>{{ number(row.scheduled_team_hours) }} h</strong><span>team-hours available</span></div><div><strong>{{ number(row.required_team_hours) }} h</strong><span>team-hours needed for assigned food</span></div><div><strong>{{ number(row.current_labour_minutes_per_kg) }} min/kg</strong><span>current demonstrated rate</span></div></div>
            <p v-if="row.capacity_state === 'under' && row.closing_output_balance_qty < 0">After using food carried from earlier weeks and all assigned runs this week, the plan is {{ number(Math.abs(row.closing_output_balance_qty)) }} kg short by the end of Week {{ row.week_number }}.</p><p v-else-if="row.capacity_state === 'under'">The assigned food is covered, but the team is {{ number(Math.abs(row.team_hour_difference)) }} team-hours short. Add {{ row.additional_people_needed }} {{ row.additional_people_needed === 1 ? 'person' : 'people' }} or extend the cooking time.</p><p v-else-if="row.capacity_state === 'idle'">Earlier production already covers Week {{ row.week_number }}, so no production run is needed. {{ number(row.closing_output_balance_qty) }} kg remains for the following week.</p><p v-else-if="row.status === 'Over capacity'">This week's schedule covers demand through Week {{ row.week_number }}. {{ number(row.closing_output_balance_qty) }} kg remains for the next week.</p><p v-else>This week's production exactly covers demand through Week {{ row.week_number }}.</p>
          </article>
        </div>
      </section>

      <footer v-if="mode === 'forecasting'" class="posting-bar"><div><SystemBadge>HYPOTHETICAL ONLY</SystemBadge><p>This scenario is not saved and cannot change the current direction. Return to Planning to change real customers, meals, or capacity.</p></div></footer>
    </template>

    <footer v-if="mode === 'planning'" class="posting-bar"><div><SystemBadge>{{ queuedMutationId ? "WAITING TO SYNC" : form.name ? "DIRECTION READY TO UPDATE" : "NEW DIRECTION" }}</SystemBadge><p>Saving recalculates future ingredient demand, shortages, supplier packs, and expected cost. Existing production drafts keep their saved theory.</p></div><div class="button-row"><SystemOperationalButton v-if="form.name" variant="ghost" size="lg" :disabled="busy || draftLocked" @click="cancelDirection">Cancel direction</SystemOperationalButton><SystemOperationalButton variant="solid" size="lg" :loading="busy" :disabled="draftLocked" @click="savePlan">{{ draftLocked ? "Waiting to sync" : form.name ? "Update direction" : "Save direction" }}</SystemOperationalButton></div></footer>
  </section>
</template>

<style scoped>
.capacity-window-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.capacity-window-grid article{display:grid;align-content:start;gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.forecast-mix{display:grid;gap:var(--spacing-xs);margin-top:var(--spacing-s)}.forecast-mix article{display:grid;grid-template-columns:minmax(12rem,1fr) repeat(2,minmax(8rem,.5fr));align-items:end;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.forecast-mix small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.forecast-table{margin-top:var(--spacing-s)}
.forecast-settings{display:grid;grid-template-columns:minmax(10rem,.35fr) minmax(18rem,1fr);align-items:end;gap:var(--spacing-s)}.forecast-settings--single{grid-template-columns:minmax(18rem,1fr)}.capacity-run-list,.forecast-week-list{display:grid;gap:var(--spacing-xs)}.capacity-run-list article{display:grid;grid-template-columns:minmax(6rem,.35fr) minmax(8rem,.55fr) minmax(8rem,.55fr) minmax(14rem,1fr) minmax(7rem,.4fr) auto;align-items:end;gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.run-actions{display:flex;align-items:flex-end;gap:var(--spacing-2xs)}.capacity-period-summary,.forecast-week-list>article{display:grid;gap:var(--spacing-s);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.capacity-period-summary{margin-bottom:var(--spacing-m);padding:var(--spacing-l)}.capacity-period-summary.is-under,.forecast-week-list>article.is-under{border-color:color-mix(in oklch,var(--theme-error) 52%,var(--theme-border));background:color-mix(in oklch,var(--theme-error) 7%,var(--theme-surface-raised))}.capacity-period-summary.is-ready,.forecast-week-list>article.is-ready{border-color:color-mix(in oklch,var(--theme-success) 30%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 2%,var(--theme-surface-raised));box-shadow:inset .25rem 0 0 color-mix(in oklch,var(--theme-success) 72%,var(--theme-border))}.capacity-period-summary.is-ready .forecast-week-heading strong,.forecast-week-list>article.is-ready .forecast-week-heading strong{color:color-mix(in oklch,var(--theme-success) 82%,var(--theme-text))}.capacity-period-summary.is-ready .capacity-equation,.forecast-week-list>article.is-ready .capacity-equation{background:color-mix(in oklch,var(--theme-success) 5%,var(--theme-secondary));box-shadow:inset 0 0 0 var(--border-width-1) color-mix(in oklch,var(--theme-success) 18%,var(--theme-border))}.capacity-period-summary p,.forecast-week-list p{margin:0;color:var(--theme-text-muted)}.capacity-breakdown-heading{display:flex;align-items:end;justify-content:space-between;gap:var(--spacing-s);margin-bottom:var(--spacing-xs)}.capacity-breakdown-heading h3{margin:0}.capacity-breakdown-heading .eyebrow{margin-bottom:var(--spacing-3xs)}.forecast-week-heading{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s)}.forecast-week-heading span{display:block;color:var(--theme-text-muted);font-size:var(--font-size--2)}.forecast-week-heading strong{font-size:var(--font-size-1)}.capacity-equation{display:flex;align-items:center;flex-wrap:wrap;gap:var(--spacing-xs);padding:var(--spacing-xs) var(--spacing-s);border-radius:var(--component-radius-field);background:var(--theme-secondary)}.capacity-equation span{color:var(--theme-text-muted)}
.forecast-week-list>article.is-idle{border-color:var(--theme-border);background:var(--theme-secondary);box-shadow:none}.forecast-week-list>article.is-idle .forecast-week-heading strong{color:var(--theme-text-muted)}.forecast-week-list>article.is-idle .capacity-equation{background:var(--theme-surface);box-shadow:none}
.capacity-period-summary :deep(.metric-board>div),.forecast-week-list :deep(.metric-board>div){min-width:0}.capacity-period-summary :deep(.metric-board strong),.capacity-period-summary :deep(.metric-board span),.forecast-week-list :deep(.metric-board strong),.forecast-week-list :deep(.metric-board span){overflow-wrap:anywhere}.forecast-week-list :deep(.metric-board strong){white-space:normal}.workforce-list{display:grid;gap:var(--spacing-xs)}.workforce-list article{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.workforce-list small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.workforce-metrics{margin-bottom:var(--spacing-s)}.workforce-basis{margin:0 0 var(--spacing-s);color:var(--theme-text-muted)}.capacity-status-card{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);margin-bottom:var(--spacing-s);padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card)}.capacity-status-card.is-under{border-color:color-mix(in oklch,var(--theme-error) 52%,var(--theme-border));background:color-mix(in oklch,var(--theme-error) 10%,var(--theme-surface-raised))}.capacity-status-card.is-ready{border-color:color-mix(in oklch,var(--theme-success) 52%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 10%,var(--theme-surface-raised))}.capacity-status-card span,.capacity-status-card p{color:var(--theme-text-muted)}.capacity-status-card strong{display:block;margin-top:var(--spacing-3xs);font-size:var(--font-size-2)}.capacity-status-card p{margin:var(--spacing-3xs) 0 0}
.plan-mix{display:grid;gap:var(--spacing-xs)}.plan-mix__row{display:grid;grid-template-columns:minmax(12rem,1fr) minmax(9rem,.5fr) minmax(10rem,.6fr);align-items:end;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.plan-mix__row>div:first-child{align-self:center;display:grid;gap:var(--spacing-3xs)}.plan-mix__row small,.week-card p{color:var(--theme-text-muted)}.calculated-value{align-self:center;display:grid;gap:var(--spacing-3xs)}.calculated-value span{color:var(--theme-text-muted);font-size:var(--font-size--2)}.week-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.week-card{display:grid;align-content:start;gap:var(--spacing-s);min-width:0;max-width:100%;overflow:visible;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.week-card :deep(*){min-width:0;max-width:100%}.week-card :deep(.system-linked-record-field__actions){flex-wrap:wrap}.week-card :deep(.system-linked-record-field__actions button){min-width:0;max-width:100%;white-space:normal}.week-card p{margin:0}@media(max-width:70rem){.week-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:44rem){.plan-mix__row,.week-grid{grid-template-columns:1fr}.workforce-list article,.capacity-status-card{align-items:flex-start;flex-direction:column}}
@media(max-width:70rem){.capacity-window-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.capacity-run-list article{grid-template-columns:repeat(3,minmax(0,1fr))}.run-actions{grid-column:1/-1}}@media(max-width:44rem){.capacity-window-grid,.forecast-mix article,.forecast-settings,.capacity-run-list article{grid-template-columns:minmax(0,1fr)}.capacity-run-list article>*{min-width:0}.capacity-run-list :deep(.system-linked-record-field__label),.capacity-run-list :deep(.system-linked-record-field>div){width:100%;min-width:0}.run-actions{grid-column:auto;flex-wrap:wrap}.capacity-period-summary{padding:var(--spacing-m)}.capacity-breakdown-heading,.forecast-week-heading{align-items:flex-start;flex-direction:column}}
.capacity-run-list,.capacity-run-list article{min-width:0}.capacity-run-list article{grid-template-columns:minmax(4.5rem,.32fr) minmax(6.5rem,.48fr) minmax(8.5rem,.72fr) minmax(8.5rem,.62fr) minmax(6.5rem,.45fr) minmax(11rem,1fr) minmax(6rem,.42fr) auto}.capacity-run-list article>*{min-width:0}
</style>
