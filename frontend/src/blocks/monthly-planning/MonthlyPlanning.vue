<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { SystemBadge, SystemCheckbox, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton } from "@/desyium"
import { cancelProductionPlan, saveMonthlyProductionPlan } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const form = reactive({ name: "", plan_title: "", status: "Active", customer_mix: [], plan_rows: [], purchase_routes: [] })
const planTypes = computed(() => props.snapshot?.options?.customer_plan_types || [])
const recipeOptions = computed(() => (props.snapshot?.options?.recipes || []).map(row => ({ label: row.recipe_name, value: row.name })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const totalCustomers = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0), 0))
const weeklyServings = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0), 0))
const weeklyKg = computed(() => roundQuantity(form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0) * Number(row.serving_size_g || 0) / 1000, 0)))
const workforceRows = computed(() => (props.plan?.workforce?.rows || []).map(row => {
  const requiredCapacity = row.capacity_basis === "Meals per Production Run" ? weeklyServings.value : row.capacity_basis === "Kg per Production Run" ? weeklyKg.value : row.capacity_basis === "Customers Served" ? totalCustomers.value : row.required_capacity
  const requiredWorkers = requiredCapacity && Number(row.capacity_per_worker) > 0 ? Math.ceil(requiredCapacity / Number(row.capacity_per_worker)) : 0
  const difference = Number(row.active_workers || 0) - requiredWorkers
  return { ...row, required_capacity: requiredCapacity, required_workers: requiredWorkers, worker_difference: difference, status: difference < 0 ? "Under capacity" : difference > 0 ? "Over capacity" : "At capacity" }
}))
const workforceSummary = computed(() => {
  const activeWorkers = workforceRows.value.reduce((sum, row) => sum + Number(row.active_workers || 0), 0)
  const requiredWorkers = workforceRows.value.reduce((sum, row) => sum + Number(row.required_workers || 0), 0)
  const plannedHours = workforceRows.value.filter(row => Number(row.expected_hours_per_run) > 0).map(row => Number(row.expected_hours_per_run))
  const hoursPerWorker = plannedHours.length ? plannedHours.reduce((sum, value) => sum + value, 0) / plannedHours.length : 0
  const actualMinutesPerKg = Number(props.plan?.workforce?.actual?.labour_minutes_per_kg || 0)
  const theoreticalMinutesPerKg = weeklyKg.value ? workforceRows.value.reduce((sum, row) => sum + Number(row.required_workers || 0) * Number(row.expected_hours_per_run || 0), 0) * 60 / weeklyKg.value : 0
  const planningMinutesPerKg = actualMinutesPerKg || theoreticalMinutesPerKg
  const requiredTeamHours = weeklyKg.value * planningMinutesPerKg / 60
  const demonstratedWorkers = requiredTeamHours && hoursPerWorker ? Math.ceil(requiredTeamHours / hoursPerWorker) : requiredWorkers
  const difference = activeWorkers - demonstratedWorkers
  return {
    activeWorkers, requiredWorkers: demonstratedWorkers, hoursPerWorker,
    availableHours: activeWorkers * hoursPerWorker, requiredTeamHours,
    taktMinutesPerKg: weeklyKg.value ? hoursPerWorker * 60 / weeklyKg.value : 0,
    planningMinutesPerKg, planningBasis: actualMinutesPerKg ? "Actual rate" : "Theoretical rate",
    status: difference < 0 ? "Under capacity" : difference > 0 ? "Buffer available" : "Capacity ready",
  }
})

watch(() => [props.plan, props.snapshot], hydrate, { immediate: true, deep: true })

function hydrate() {
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
      return { week_number: index + 1, recipe: current?.recipe || "", finished_item: current?.finished_item || "", planned_output_qty: weeklyKg.value }
    }),
    purchase_routes: (props.snapshot?.options?.item_categories || []).map(category => {
      const current = props.plan?.purchase_routes?.find(row => row.item_category === category.name)
      return { item_category: category.name, supplier: current?.supplier || category.default_supplier || "", use_discounted_price: Boolean(current?.use_discounted_price) }
    }),
  })
}

function openLinked(mode, doctype) {
  router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } })
}

async function savePlan() {
  error.value = ""
  if (form.plan_rows.some(row => !row.recipe)) return (error.value = "Choose all four meals in the repeating cycle.")
  busy.value = true
  try {
    await saveMonthlyProductionPlan({ ...form, location: "Ingredients", plan_rows: form.plan_rows.map(row => ({ ...row, planned_output_qty: weeklyKg.value })) })
    emit("changed")
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
  <section data-block="monthly-planning" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Planning</p><h1>Set the current meal direction</h1><p>Keep customer numbers current and choose the four meals that repeat. Future buying and production recalculate whenever this direction changes.</p></div><SystemBadge>{{ form.name ? "ACTIVE DIRECTION" : "NEW DIRECTION" }}</SystemBadge></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>

    <section class="form-section">
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

    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Meal cycle</p><h2>Choose the four repeating meals</h2><p>Production advances through these meals in order, then starts again at meal one.</p></div></div>
      <div class="week-grid">
        <article v-for="row in form.plan_rows" :key="row.week_number" class="week-card">
          <SystemBadge>MEAL {{ row.week_number }}</SystemBadge>
          <SystemLinkedRecordField v-model="row.recipe" label="Meal recipe" :options="recipeOptions" placeholder="Choose this meal" create-label="Add recipe" manage-label="Manage recipes" @create="openLinked('create', 'BulkBite Recipe')" @manage="openLinked('list', 'BulkBite Recipe')" />
          <p><strong>{{ weeklyServings }}</strong> meals · <strong>{{ number(weeklyKg) }} kg</strong> planned output</p>
        </article>
      </div>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Buying routes</p><h2>Choose where each category is bought</h2><p>Every enabled food category appears here. Add categories in setup, assign them to items, then choose the usual supplier.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="openLinked('create', 'BulkBite Item Category')">Add category</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="openLinked('list', 'BulkBite Item Category')">Manage categories</SystemOperationalButton></div></div>
      <div v-if="!form.purchase_routes.length" class="state-message">Add at least one enabled food category before saving the plan.</div>
      <div class="route-grid">
        <article v-for="row in form.purchase_routes" :key="row.item_category" class="route-row">
          <strong>{{ row.item_category }}</strong>
          <SystemLinkedRecordField v-model="row.supplier" label="Buy from" :options="supplierOptions" placeholder="Choose supplier" create-label="Add supplier" manage-label="Manage suppliers" @create="openLinked('create', 'BulkBite Supplier')" @manage="openLinked('list', 'BulkBite Supplier')" />
          <SystemCheckbox v-model="row.use_discounted_price" label="Use active discounted price" />
        </article>
      </div>
    </section>

    <section class="data-section workforce-section"><div class="section-heading"><div><p class="eyebrow">Lean workforce capacity</p><h2>Can the current team make this plan?</h2><p>Customer changes update demand, takt time, team-hours, and workers needed. Actual production hours become the planning rate after the first posted run.</p></div><SystemBadge :theme="workforceSummary.status === 'Under capacity' ? 'orange' : 'green'">{{ workforceSummary.status }}</SystemBadge></div><div class="metric-board workforce-metrics"><div><strong>{{ number(workforceSummary.taktMinutesPerKg) }} min/kg</strong><span>required takt time</span></div><div><strong>{{ number(workforceSummary.requiredTeamHours) }} hours</strong><span>team-hours needed</span></div><div><strong>{{ workforceSummary.requiredWorkers }}</strong><span>workers needed</span></div><div><strong>{{ workforceSummary.activeWorkers }}</strong><span>workers available</span></div></div><p class="workforce-basis">Planning with the {{ workforceSummary.planningBasis.toLowerCase() }} of {{ number(workforceSummary.planningMinutesPerKg) }} labour-minutes per kg. The current team has {{ number(workforceSummary.availableHours) }} worker-hours available per run.</p><div class="workforce-list"><article v-for="row in workforceRows" :key="row.name"><div><strong>{{ row.employee_type_name }}</strong><small>{{ row.required_workers }} needed · {{ row.active_workers }} active · {{ number(row.capacity_per_worker) }} kg per worker</small></div><SystemBadge :theme="row.status === 'Under capacity' ? 'orange' : row.status === 'At capacity' ? 'green' : undefined">{{ row.status }}</SystemBadge></article><p v-if="!workforceRows.length" class="state-message">No employee types are configured yet. Add them from Production, Employees.</p></div></section>

    <footer class="posting-bar"><div><SystemBadge>{{ form.name ? "DIRECTION READY TO UPDATE" : "NEW DIRECTION" }}</SystemBadge><p>Saving recalculates future ingredient demand, shortages, supplier packs, and expected cost. Existing production drafts keep their saved theory.</p></div><div class="button-row"><SystemOperationalButton v-if="form.name" variant="ghost" size="lg" :disabled="busy" @click="cancelDirection">Cancel direction</SystemOperationalButton><SystemOperationalButton variant="solid" size="lg" :loading="busy" @click="savePlan">{{ form.name ? "Update direction" : "Save direction" }}</SystemOperationalButton></div></footer>
  </section>
</template>

<style scoped>
.workforce-list{display:grid;gap:var(--spacing-xs)}.workforce-list article{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.workforce-list small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}.workforce-metrics{margin-bottom:var(--spacing-s)}.workforce-basis{margin:0 0 var(--spacing-s);color:var(--theme-text-muted)}
.plan-mix,.route-grid{display:grid;gap:var(--spacing-xs)}.plan-mix__row,.route-row{display:grid;grid-template-columns:minmax(12rem,1fr) minmax(9rem,.5fr) minmax(10rem,.6fr);align-items:end;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.plan-mix__row>div:first-child{align-self:center;display:grid;gap:var(--spacing-3xs)}.plan-mix__row small,.week-card p{color:var(--theme-text-muted)}.calculated-value{align-self:center;display:grid;gap:var(--spacing-3xs)}.calculated-value span{color:var(--theme-text-muted);font-size:var(--font-size--2)}.week-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.week-card{display:grid;align-content:start;gap:var(--spacing-s);min-width:0;max-width:100%;overflow:visible;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.week-card :deep(*){min-width:0;max-width:100%}.week-card :deep(.system-linked-record-field__actions){flex-wrap:wrap}.week-card :deep(.system-linked-record-field__actions button){min-width:0;max-width:100%;white-space:normal}.week-card p{margin:0}.route-row{grid-template-columns:minmax(10rem,.45fr) minmax(15rem,1fr) minmax(12rem,.65fr)}.route-row>strong{align-self:center}@media(max-width:70rem){.week-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:44rem){.plan-mix__row,.route-row,.week-grid{grid-template-columns:1fr}}
</style>
