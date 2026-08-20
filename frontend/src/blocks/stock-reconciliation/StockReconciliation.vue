<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemFormControl, SystemOperationalButton, SystemTextarea } from "@/desyium"
import { approveStockAudit, createStockCountDraft } from "@/resources/api"

const props = defineProps({ inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const postingDate = ref(new Date().toISOString().slice(0, 10))
const notes = ref("")
const counts = reactive([])
const draft = ref(null)
const busy = ref(false)
const error = ref("")
watch(() => props.inventory?.items, items => { counts.splice(0); (items || []).forEach(item => counts.push({ ...item, counted_qty: item.actual_qty })) }, { immediate: true })
const changedCounts = computed(() => counts.filter(item => Number(item.counted_qty) !== Number(item.actual_qty)))
async function saveCount() { busy.value = true; error.value = ""; try { draft.value = await createStockCountDraft({ posting_date: postingDate.value, notes: notes.value, items: counts.map(item => ({ item_code: item.item_code, location: props.inventory.location, qty: item.counted_qty })) }) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
async function approve() { busy.value = true; error.value = ""; try { draft.value = await approveStockAudit(draft.value.name); emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false } }
</script>

<template>
  <section data-block="stock-reconciliation" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">PHYSICAL COUNT</p><h1>COUNT IT.<br />THEN CORRECT IT.</h1><p>Enter what is physically present. Saving creates a draft only. A manager approves the differences before stock is reconciled.</p></div><div class="step-rail"><span class="is-current">1 Count</span><span>2 Review</span><span>3 Approve</span></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section"><SystemFormControl v-model="postingDate" type="date" label="Count date" size="lg" /><label class="field-shell"><span>Count notes</span><SystemTextarea v-model="notes" rows="3" placeholder="Who counted, where, and any unusual conditions" /></label></section>
    <section class="data-section">
      <div class="section-heading"><div><p class="eyebrow">{{ inventory?.location || "Ingredients" }}</p><h2>COUNTED STOCK</h2></div><SystemBadge>{{ changedCounts.length }} DIFFERENCES</SystemBadge></div>
      <div class="measurement-list">
        <article v-for="item in counts" :key="item.item_code" class="measurement-row measurement-row--count" :class="{ 'is-different': Number(item.counted_qty) !== Number(item.actual_qty) }">
          <div><strong>{{ item.item_name }}</strong><small>System says {{ Number(item.actual_qty).toFixed(3) }} {{ item.stock_uom }}</small></div>
          <SystemFormControl v-model="item.counted_qty" type="number" label="Counted" min="0" step="0.001" size="lg" />
          <div class="difference"><span>Difference</span><strong>{{ (Number(item.counted_qty) - Number(item.actual_qty)).toFixed(3) }} {{ item.stock_uom }}</strong></div>
        </article>
      </div>
    </section>
    <footer class="posting-bar"><div><SystemBadge>{{ draft ? (draft.docstatus ? "APPROVED" : "DRAFT SAVED") : "NOT SAVED" }}</SystemBadge><p>Approval appends reconciliation events. It does not rewrite previous events.</p></div><SystemOperationalButton v-if="!draft" variant="outline" size="lg" :loading="busy" @click="saveCount">Save count draft</SystemOperationalButton><SystemOperationalButton v-else-if="!draft.docstatus" theme="blue" variant="solid" size="lg" :loading="busy" @click="approve">Approve reconciliation</SystemOperationalButton></footer>
  </section>
</template>
