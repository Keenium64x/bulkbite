<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { SystemBadge, SystemCheckbox, SystemDatePicker, SystemFormControl, SystemLinkedRecordField, SystemOperationalButton } from "@/desyium"
import { saveMonthlyProductionPlan } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const form = reactive({ name: "", plan_title: "", status: "Active", period_start: "", period_end: "", customer_mix: [], plan_rows: [], purchase_routes: [] })
const planTypes = computed(() => props.snapshot?.options?.customer_plan_types || [])
const recipeOptions = computed(() => (props.snapshot?.options?.recipes || []).map(row => ({ label: row.recipe_name, value: row.name })))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))
const totalCustomers = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0), 0))
const weeklyServings = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0), 0))
const weeklyKg = computed(() => form.customer_mix.reduce((sum, row) => sum + Number(row.customer_count || 0) * Number(row.meals_per_day || 0) * Number(row.days_per_week || 0) * Number(row.serving_size_g || 0) / 1000, 0))

watch(() => [props.plan, props.snapshot], hydrate, { immediate: true, deep: true })

function hydrate() {
  const start = props.plan?.period_start || localToday()
  const end = props.plan?.period_end || addDays(start, 27)
  Object.assign(form, {
    name: props.plan?.name || "",
    plan_title: props.plan?.plan_title || `Production plan from ${start}`,
    status: props.plan?.status || "Active",
    period_start: start,
    period_end: end,
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

function addDays(value, days) {
  const date = new Date(`${value}T00:00:00`)
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

function localToday() {
  const value = new Date()
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`
}

function openLinked(mode, doctype) {
  router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } })
}

function startNextPlan() {
  const start = addDays(form.period_end || localToday(), 1)
  form.name = ""
  form.plan_title = `Production plan from ${start}`
  form.period_start = start
  form.period_end = addDays(start, 27)
  form.plan_rows.forEach(row => { row.recipe = ""; row.finished_item = "" })
  error.value = ""
}

async function savePlan() {
  error.value = ""
  if (!form.period_start || !form.period_end) return (error.value = "Choose the four-week period.")
  if (form.plan_rows.some(row => !row.recipe)) return (error.value = "Choose one meal for each of the four weeks.")
  busy.value = true
  try {
    await saveMonthlyProductionPlan({ ...form, location: "Ingredients", plan_rows: form.plan_rows.map(row => ({ ...row, planned_output_qty: weeklyKg.value })) })
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

function number(value) { return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 1 }) }
</script>

<template>
  <section data-block="monthly-planning" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Planning</p><h1>Plan the next four weeks</h1><p>Enter how many customers are on each plan, then choose one meal for each week. BulkBite calculates the food required.</p></div><SystemOperationalButton v-if="form.name" variant="outline" @click="startNextPlan">Start next month</SystemOperationalButton></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>

    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 1</p><h2>Set the period and customer mix</h2><p>Serving sizes and weekly meal frequency come from the customer plan records.</p></div><SystemBadge>{{ totalCustomers }} customers</SystemBadge></div>
      <div class="field-grid">
        <SystemFormControl v-model="form.plan_title" label="Plan name" size="lg" />
        <SystemDatePicker v-model="form.period_start" label="Period start" format="YYYY-MM-DD" :clearable="false" />
        <SystemDatePicker v-model="form.period_end" label="Period end" format="YYYY-MM-DD" :clearable="false" />
      </div>
      <div class="plan-mix">
        <article v-for="row in form.customer_mix" :key="row.plan_type" class="plan-mix__row">
          <div><strong>{{ row.plan_type }}</strong><small>{{ number(row.serving_size_g) }} g per meal · {{ row.meals_per_day }} meals/day</small></div>
          <SystemFormControl v-model="row.customer_count" type="number" label="Customers" min="0" step="1" size="lg" />
          <div class="calculated-value"><span>Food per week</span><strong>{{ number(Number(row.customer_count || 0) * row.meals_per_day * row.days_per_week * row.serving_size_g / 1000) }} kg</strong></div>
        </article>
      </div>
      <div class="metric-board"><div><strong>{{ totalCustomers }}</strong><span>customers</span></div><div><strong>{{ weeklyServings }}</strong><span>meals per week</span></div><div><strong>{{ number(weeklyKg) }} kg</strong><span>food per week</span></div><div><strong>{{ number(weeklyKg * 4) }} kg</strong><span>four-week output</span></div></div>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 2</p><h2>Choose the four weekly meals</h2><p>Each meal uses the same customer demand for its week.</p></div></div>
      <div class="week-grid">
        <article v-for="row in form.plan_rows" :key="row.week_number" class="week-card">
          <SystemBadge>WEEK {{ row.week_number }}</SystemBadge>
          <SystemLinkedRecordField v-model="row.recipe" label="Meal recipe" :options="recipeOptions" placeholder="Choose this week’s meal" create-label="Add recipe" manage-label="Manage recipes" @create="openLinked('create', 'BulkBite Recipe')" @manage="openLinked('list', 'BulkBite Recipe')" />
          <p><strong>{{ weeklyServings }}</strong> meals · <strong>{{ number(weeklyKg) }} kg</strong> planned output</p>
        </article>
      </div>
    </section>

    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Step 3</p><h2>Choose where each category is bought</h2><p>Every enabled food category appears here. Add categories in setup, assign them to items, then choose the supplier for this period.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="openLinked('create', 'BulkBite Item Category')">Add category</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="openLinked('list', 'BulkBite Item Category')">Manage categories</SystemOperationalButton></div></div>
      <div v-if="!form.purchase_routes.length" class="state-message">Add at least one enabled food category before saving the plan.</div>
      <div class="route-grid">
        <article v-for="row in form.purchase_routes" :key="row.item_category" class="route-row">
          <strong>{{ row.item_category }}</strong>
          <SystemLinkedRecordField v-model="row.supplier" label="Buy from" :options="supplierOptions" placeholder="Choose supplier" create-label="Add supplier" manage-label="Manage suppliers" @create="openLinked('create', 'BulkBite Supplier')" @manage="openLinked('list', 'BulkBite Supplier')" />
          <SystemCheckbox v-model="row.use_discounted_price" label="Use active discounted price" />
        </article>
      </div>
    </section>

    <footer class="posting-bar"><div><SystemBadge>{{ form.name ? "PLAN READY TO UPDATE" : "NEW PLAN" }}</SystemBadge><p>Saving recalculates ingredient demand, stock shortages, supplier packs, and expected cost.</p></div><SystemOperationalButton variant="solid" size="lg" :loading="busy" @click="savePlan">Save and calculate plan</SystemOperationalButton></footer>
  </section>
</template>

<style scoped>
.plan-mix,.route-grid{display:grid;gap:var(--spacing-xs)}.plan-mix__row,.route-row{display:grid;grid-template-columns:minmax(12rem,1fr) minmax(9rem,.5fr) minmax(10rem,.6fr);align-items:end;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.plan-mix__row>div:first-child{align-self:center;display:grid;gap:var(--spacing-3xs)}.plan-mix__row small,.week-card p{color:var(--theme-text-muted)}.calculated-value{align-self:center;display:grid;gap:var(--spacing-3xs)}.calculated-value span{color:var(--theme-text-muted);font-size:var(--font-size--2)}.week-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-s)}.week-card{display:grid;align-content:start;gap:var(--spacing-s);min-width:0;max-width:100%;overflow:visible;padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.week-card :deep(*){min-width:0;max-width:100%}.week-card :deep(.system-linked-record-field__actions){flex-wrap:wrap}.week-card :deep(.system-linked-record-field__actions button){min-width:0;max-width:100%;white-space:normal}.week-card p{margin:0}.route-row{grid-template-columns:minmax(10rem,.45fr) minmax(15rem,1fr) minmax(12rem,.65fr)}.route-row>strong{align-self:center}@media(max-width:70rem){.week-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:44rem){.plan-mix__row,.route-row,.week-grid{grid-template-columns:1fr}}
</style>
