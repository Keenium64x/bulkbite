<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { SystemBadge, SystemOperationalButton } from "@/desyium"

const props = defineProps({ snapshot: { type: Object, default: null }, plan: { type: Object, default: null } })
const emit = defineEmits(["open-workflow"])
const router = useRouter()
const buying = computed(() => props.plan?.buying || { lines: [], suppliers: [], expected_cost: 0 })
function number(value, digits = 2) { return Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: digits, maximumFractionDigits: digits }) }
function manageOffers() { router.push({ name: "BulkBiteSetupList", params: { doctype: "BulkBite Supplier Offer" } }) }
</script>

<template>
  <section data-block="buying-plan" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Buying</p><h1>What to buy next</h1><p>Shortages use the current customer direction and stock on hand. Quantities round up to the pack size sold by each chosen supplier.</p></div><SystemBadge>{{ plan?.plan_title || "NO ACTIVE DIRECTION" }}</SystemBadge></header>
    <div v-if="!plan" class="state-message"><p>Set the current customer direction before building a shopping list.</p><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Open planning</SystemOperationalButton></div>
    <template v-else>
      <div class="metric-board"><div><strong>{{ buying.shortage_count || 0 }}</strong><span>items short</span></div><div><strong>{{ buying.missing_offer_count || 0 }}</strong><span>prices missing</span></div><div><strong>R {{ number(buying.expected_cost) }}</strong><span>expected basket</span></div><div><strong>{{ buying.lines.filter(line => line.shortage_qty > 0).reduce((sum, line) => sum + Number(line.surplus_qty || 0), 0).toFixed(1) }}</strong><span>pack overflow units</span></div></div>
      <div class="buying-actions"><SystemOperationalButton variant="outline" @click="emit('open-workflow', 'planning')">Update customer direction</SystemOperationalButton><SystemOperationalButton variant="outline" @click="manageOffers">Manage supplier offers</SystemOperationalButton><SystemOperationalButton variant="solid" @click="emit('open-workflow', 'receipts')">Add purchase receipt</SystemOperationalButton></div>
      <section v-for="group in buying.suppliers" :key="group.supplier" class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Supplier order</p><h2>{{ group.supplier }}</h2></div><SystemBadge>R {{ number(group.expected_cost) }}</SystemBadge></div>
        <div class="table-wrap"><table><thead><tr><th>Ingredient</th><th>Need</th><th>Pack sold</th><th>Packs</th><th>Buy</th><th>Price</th></tr></thead><tbody>
          <tr v-for="line in group.items.filter(item => item.shortage_qty > 0)" :key="line.item_code">
            <td><strong>{{ line.item_name }}</strong><small>{{ line.item_category || "Uncategorised" }}</small></td><td class="number-cell">{{ number(line.shortage_qty, 1) }} {{ line.uom }}</td>
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
.buying-actions{display:flex;flex-wrap:wrap;gap:var(--spacing-xs);margin-block:var(--spacing-s)}.large-value{display:block;margin-block:var(--spacing-xs);font-size:var(--font-size-3)}td small{display:block;margin-top:var(--spacing-3xs);color:var(--theme-text-muted)}
</style>
