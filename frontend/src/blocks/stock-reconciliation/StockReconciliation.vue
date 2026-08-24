<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemDatePicker, SystemFormControl, SystemOperationalButton, SystemTextarea } from "@/desyium"
import { approveStockAudit, createStockCountDraft } from "@/resources/api"

const props = defineProps({ inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const postingDate = ref(localToday())
const notes = ref("")
const counts = reactive([])
const draft = ref(null)
const busy = ref(false)
const error = ref("")
function localToday() { const value = new Date(); return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}` }
watch(() => props.inventory?.items, items => { counts.splice(0); (items || []).forEach(item => counts.push({ ...item, counted_qty: item.actual_qty })) }, { immediate: true })
const changedCounts = computed(() => counts.filter(item => Number(item.counted_qty) !== Number(item.actual_qty)))
async function saveCount() { error.value = ""; if (!postingDate.value) { error.value = "Choose the count date."; return } if (!counts.length) { error.value = "There is no stock to count."; return } if (counts.some((item) => Number(item.counted_qty) < 0 || !Number.isFinite(Number(item.counted_qty)))) { error.value = "Every counted quantity must be zero or more."; return } busy.value = true; try { draft.value = await createStockCountDraft({ posting_date: postingDate.value, notes: notes.value, items: counts.map(item => ({ item_code: item.item_code, location: props.inventory.location, qty: Number(item.counted_qty) })) }) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
async function approve() { busy.value = true; error.value = ""; try { draft.value = await approveStockAudit(draft.value.name); emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false } }
</script>

<template>
  <section data-block="stock-reconciliation" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Stock count</p><h1>Match the system to physical stock</h1><p>Enter what is actually present, review every difference, then let a manager approve the correction.</p></div></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section"><div class="section-heading"><div><p class="eyebrow">Physical count</p><h2>Enter the counted stock</h2><p>Record when and how this count was completed.</p></div></div><SystemDatePicker v-model="postingDate" label="Count date" format="YYYY-MM-DD" :disabled="Boolean(draft)" :clearable="false" /><label class="field-shell"><span>Count notes</span><SystemTextarea v-model="notes" :rows="3" :disabled="Boolean(draft)" placeholder="Who counted, where, and any unusual conditions" /></label></section>
    <section class="data-section">
      <div class="section-heading"><div><p class="eyebrow">{{ inventory?.location || "Ingredients" }}</p><h2>Counted stock</h2></div><SystemBadge>{{ changedCounts.length }} differences</SystemBadge></div>
      <div class="measurement-list">
        <article v-for="item in counts" :key="item.item_code" class="measurement-row measurement-row--count" :class="{ 'is-different': Number(item.counted_qty) !== Number(item.actual_qty) }">
          <div><strong>{{ item.item_name }}</strong><small>System says {{ Number(item.actual_qty).toFixed(2) }} {{ item.stock_uom }}</small></div>
          <SystemFormControl v-model="item.counted_qty" type="number" label="Counted" min="0" step="0.1" size="lg" :disabled="Boolean(draft)" />
          <div class="difference"><span>Difference</span><strong>{{ (Number(item.counted_qty) - Number(item.actual_qty)).toFixed(2) }} {{ item.stock_uom }}</strong></div>
        </article>
      </div>
    </section>
    <footer class="posting-bar"><div><SystemBadge>{{ draft ? (draft.docstatus ? "STOCK RECONCILED" : "READY FOR APPROVAL") : "COUNT NOT SAVED" }}</SystemBadge><p>{{ draft ? (draft.docstatus ? "The approved differences are now reflected in stock." : "A manager must check and approve these differences before stock changes.") : "Saving creates a review draft only. Stock will not change yet." }}</p></div><SystemOperationalButton v-if="!draft" variant="outline" size="lg" :loading="busy" @click="saveCount">Save count draft</SystemOperationalButton><SystemOperationalButton v-else-if="!draft.docstatus" variant="solid" size="lg" :loading="busy" @click="approve">Approve reconciliation</SystemOperationalButton></footer>
  </section>
</template>
