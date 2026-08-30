<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { SystemBadge, SystemCheckboxShadcn, SystemLinkedRecordField, SystemOperationalButton, SystemSelect } from "@/desyium"
import { getBuyingRecommendation, saveMonthlyProductionPlan } from "@/resources/api"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["open-workflow", "changed"])
const router = useRouter()
const busy = ref(false)
const error = ref("")
const routes = reactive([])
const horizonWeeks = ref(4)
const recommendation = ref(null)
const buying = computed(() => recommendation.value || props.plan?.buying || { lines: [], suppliers: [], expected_cost: 0 })
const horizonOptions = [1, 2, 4, 8, 12].map(value => ({ label: `${value} ${value === 1 ? 'week' : 'weeks'}`, value }))
const supplierOptions = computed(() => (props.snapshot?.options?.suppliers || []).map(value => ({ label: value, value })))

watch(() => [props.plan, props.snapshot], hydrateRoutes, { immediate: true, deep: true })
watch(() => [props.plan?.name, horizonWeeks.value], loadRecommendation, { immediate: true })

function number(value, digits = 2) { return Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: digits, maximumFractionDigits: digits }) }
function dateLabel(value) { return value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "Set supplier lead time" }
function manageOffers() { router.push({ name: "BulkBiteSetupList", params: { doctype: "BulkBite Supplier Offer" } }) }
function openLinked(mode, doctype) { router.push(mode === "create" ? { name: "AuxiliaryRecordCreate", params: { doctype } } : { name: "BulkBiteSetupList", params: { doctype } }) }

function hydrateRoutes() {
  routes.splice(0, routes.length, ...(props.snapshot?.options?.item_categories || []).map(category => {
    const current = props.plan?.purchase_routes?.find(row => row.item_category === category.name)
    return { item_category: category.name, supplier: current?.supplier || category.default_supplier || "", use_discounted_price: Boolean(current?.use_discounted_price) }
  }))
}

async function loadRecommendation() {
  if (!props.plan?.name) return
  busy.value = true
  error.value = ""
  try { recommendation.value = await getBuyingRecommendation(props.plan.name, props.plan.location || "Ingredients", horizonWeeks.value) }
  catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function saveRoutes() {
  error.value = ""
  if (!props.plan) return
  const missing = routes.filter(row => !row.supplier).map(row => row.item_category)
  if (missing.length) return (error.value = `Choose a supplier for: ${missing.join(", ")}.`)
  busy.value = true
  try {
    const capacity = props.plan.capacity_plan || {}
    await saveMonthlyProductionPlan({
      name: props.plan.name,
      plan_title: props.plan.plan_title,
      customer_mix: props.plan.customer_mix,
      purchase_routes: routes,
      plan_rows: (props.plan.rows || []).map(row => ({ ...row })),
      forecast_weeks: 4,
      forecast_customer_mix: (props.plan.customer_mix || []).map(row => ({ plan_type: row.plan_type, target_customers: Number(row.customer_count || 0), target_week: 1 })),
      default_team_template: capacity.default_team_template || "",
      capacity_windows: capacity.windows || [],
      capacity_runs: capacity.runs || [],
      location: props.plan.location || "Ingredients",
    })
    emit("changed")
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}
</script>

<template>
  <section data-block="buying-plan" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Buying</p><h1>What to buy next</h1><p>This is an advisory shopping list for the selected future period. Receipts remain the only proof that anything was bought.</p></div><SystemBadge>{{ plan?.plan_title || "NO ACTIVE DIRECTION" }}</SystemBadge></header>
    <div v-if="!plan" class="state-message"><p>Set the current customer direction before building a shopping list.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Open planning</SystemOperationalButton></div>
    <template v-else>
      <section class="form-section buying-horizon"><div class="section-heading"><div><p class="eyebrow">Buying period</p><h2>Choose how far ahead to cover</h2><p>The basket repeats the saved meal cycle for this horizon, subtracts current ingredient stock, and rounds shortages to supplier packs.</p></div><SystemBadge>ADVISORY ONLY</SystemBadge></div><div class="horizon-control"><SystemSelect v-model="horizonWeeks" label="Plan buying for" :options="horizonOptions" /><SystemOperationalButton variant="outline" :loading="busy" @click="loadRecommendation">Recalculate</SystemOperationalButton></div></section>
      <section class="form-section">
        <div class="section-heading"><div><p class="eyebrow">Buying routes</p><h2>Choose where each category is bought</h2><p>Set the usual supplier for every enabled food category. Saving the routes recalculates this shopping list and its expected cost.</p></div><div class="button-row"><SystemOperationalButton variant="outline" @click="openLinked('create', 'BulkBite Item Category')">Add category</SystemOperationalButton><SystemOperationalButton variant="ghost" @click="openLinked('list', 'BulkBite Item Category')">Manage categories</SystemOperationalButton></div></div>
        <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
        <div v-if="!routes.length" class="state-message">Add at least one enabled food category before setting buying routes.</div>
        <div class="route-grid">
          <article v-for="row in routes" :key="row.item_category" class="route-row">
            <strong>{{ row.item_category }}</strong>
            <SystemLinkedRecordField v-model="row.supplier" label="Buy from" :options="supplierOptions" placeholder="Choose supplier" create-label="Add supplier" manage-label="Manage suppliers" @create="openLinked('create', 'BulkBite Supplier')" @manage="openLinked('list', 'BulkBite Supplier')" />
            <SystemCheckboxShadcn v-model="row.use_discounted_price" label="Use active discounted price" />
          </article>
        </div>
        <div class="route-actions"><SystemOperationalButton variant="solid" :loading="busy" @click="saveRoutes">Save buying routes</SystemOperationalButton></div>
      </section>
      <div class="metric-board"><div><strong>{{ buying.horizon_weeks || horizonWeeks }}</strong><span>weeks covered</span></div><div><strong>{{ buying.shortage_count || 0 }}</strong><span>items short</span></div><div><strong>{{ buying.missing_offer_count || 0 }}</strong><span>prices missing</span></div><div><strong>R {{ number(buying.expected_cost) }}</strong><span>expected basket</span></div><div><strong>{{ buying.lines.filter(line => line.shortage_qty > 0).reduce((sum, line) => sum + Number(line.surplus_qty || 0), 0).toFixed(1) }}</strong><span>pack overflow units</span></div></div>
      <section v-if="buying.all_stock_covered" class="buying-covered" role="status"><div><p class="eyebrow">Ready to cook</p><h2>Everything in this buying period is covered</h2><p>Receipt-posted ingredient stock and available finished food cover the selected horizon. There is nothing left on the shopping list.</p></div><SystemBadge theme="green">ALL COVERED</SystemBadge></section>
      <div class="buying-actions"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Update customer direction</SystemOperationalButton><SystemOperationalButton variant="outline" @click="manageOffers">Manage supplier offers</SystemOperationalButton><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'receipts')">Add purchase receipt</SystemOperationalButton></div>
      <section v-for="group in buying.suppliers" :key="group.supplier" class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Supplier order</p><h2>{{ group.supplier }}</h2><p>{{ group.pull_forward_recommendation }}</p></div><SystemBadge>R {{ number(group.expected_cost) }}</SystemBadge></div>
        <div class="order-timeline"><div><span>Order by</span><strong>{{ dateLabel(group.order_by_date) }}</strong><small>{{ group.lead_time_days || 0 }} delivery days<span v-if="group.safety_days"> + {{ group.safety_days }} safety</span></small></div><div><span>Cook</span><strong>{{ dateLabel(group.production_date) }}</strong><small>Next saved cooking session</small></div><div><span>Customer handoff</span><strong>{{ dateLabel(group.customer_delivery_date) }}</strong><small>Sunday delivery</small></div><SystemOperationalButton variant="ghost" @click="openLinked('list', 'BulkBite Supplier')">Edit lead times</SystemOperationalButton></div>
        <div v-if="group.delivery_threshold || group.supplier_order_minimum" class="delivery-position" :class="(group.threshold_status === 'reached' || !group.delivery_threshold) && (group.supplier_order_minimum_met || !group.supplier_order_minimum) ? 'is-ready' : 'is-under'"><div v-if="group.delivery_threshold"><span>Free-delivery threshold</span><strong>R {{ number(group.delivery_threshold) }}</strong></div><div v-if="group.supplier_order_minimum"><span>Supplier order minimum</span><strong>R {{ number(group.supplier_order_minimum) }}</strong></div><div><span>Current base basket</span><strong>R {{ number(group.base_cost) }}</strong></div><div v-if="group.delivery_threshold"><span>{{ group.threshold_status === 'reached' ? 'Delivery threshold' : 'Gap to free delivery' }}</span><strong>{{ group.threshold_status === 'reached' ? 'Covered' : `R ${number(group.threshold_gap)}` }}</strong></div><div v-if="group.supplier_order_minimum"><span>{{ group.supplier_order_minimum_met ? 'Order minimum' : 'Gap to order minimum' }}</span><strong>{{ group.supplier_order_minimum_met ? 'Covered' : `R ${number(group.supplier_order_minimum_gap)}` }}</strong></div><div v-if="group.delivery_threshold"><span>Delivery below threshold</span><strong>R {{ number(group.delivery_fee_below_threshold) }}</strong></div></div>
        <div class="table-wrap"><table><thead><tr><th>Ingredient</th><th>Need</th><th>Pack sold</th><th>Packs</th><th>Buy</th><th>Price</th></tr></thead><tbody>
          <tr v-for="line in group.items.filter(item => item.shortage_qty > 0)" :key="line.item_code">
            <td><strong>{{ line.item_name }}</strong><small>{{ line.item_category || "Uncategorised" }} · raw purchase quantity</small></td><td class="number-cell">{{ number(line.shortage_qty, 1) }} {{ line.uom }}</td>
            <td><span v-if="line.offer">{{ number(line.offer.units_per_pack, 1) }} × {{ number(line.offer.unit_size, 1) }} {{ line.offer.purchase_uom }}</span><SystemBadge v-else theme="orange">PRICE NEEDED</SystemBadge></td>
            <td class="number-cell">{{ line.packs_to_buy || 0 }}</td><td class="number-cell">{{ number(line.purchase_qty, 1) }} {{ line.uom }}</td><td class="money-cell"><span v-if="line.offer">R {{ number(line.expected_cost) }}</span><small v-if="line.offer?.discount_active">Discount used</small></td>
          </tr><tr v-if="!group.items.some(item => item.shortage_qty > 0)"><td colspan="6">Nothing needs to be bought from this supplier.</td></tr>
        </tbody></table></div>
      </section>
      <div class="safety-note"><strong>Buying is the forward basket.</strong><p>Whole packs can leave useful overflow in stock. Use Reports for monthly theoretical versus actual expenditure.</p></div>
    </template>
  </section>
</template>

<style scoped>
.buying-covered{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-m);margin-block:var(--spacing-s);padding:var(--spacing-m);border:var(--border-width-1) solid color-mix(in oklch,var(--theme-success) 42%,var(--theme-border));border-radius:var(--component-radius-block);background:color-mix(in oklch,var(--theme-success) 7%,var(--theme-surface-raised))}.buying-covered h2,.buying-covered p{margin:var(--spacing-3xs) 0 0}.buying-covered p:not(.eyebrow){color:var(--theme-text-muted)}
.buying-actions{display:flex;flex-wrap:wrap;gap:var(--spacing-xs);margin-block:var(--spacing-s)}.horizon-control{display:grid;grid-template-columns:minmax(12rem,20rem) auto;align-items:end;gap:var(--spacing-xs)}.route-grid{display:grid;gap:var(--spacing-xs)}.route-row{display:grid;grid-template-columns:minmax(10rem,.45fr) minmax(15rem,1fr) minmax(12rem,.65fr);align-items:end;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.route-row>strong{align-self:center}.route-actions{display:flex;justify-content:flex-end;margin-top:var(--spacing-s)}.order-timeline{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) auto;align-items:end;gap:var(--spacing-xs);margin-bottom:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.order-timeline>div{display:grid;gap:var(--spacing-3xs)}.order-timeline span,.order-timeline small{color:var(--theme-text-muted)}.order-timeline span{font-size:var(--font-size--2)}.delivery-position{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-xs);margin-bottom:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-secondary)}.delivery-position.is-ready{border-color:color-mix(in oklch,var(--theme-success) 40%,var(--theme-border))}.delivery-position.is-under{border-color:color-mix(in oklch,var(--theme-warning) 48%,var(--theme-border))}.delivery-position div{display:grid;gap:var(--spacing-3xs)}.delivery-position span{color:var(--theme-text-muted);font-size:var(--font-size--2)}.large-value{display:block;margin-block:var(--spacing-xs);font-size:var(--font-size-3)}td small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}@media(max-width:52rem){.delivery-position,.order-timeline{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:44rem){.route-row,.horizon-control,.delivery-position,.order-timeline{grid-template-columns:1fr}.route-actions{justify-content:stretch}.route-actions>*{width:100%}}
</style>
