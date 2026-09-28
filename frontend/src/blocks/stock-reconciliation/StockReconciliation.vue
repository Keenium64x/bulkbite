<script setup>
import { computed, reactive, ref, watch } from "vue"
import { SystemBadge, SystemDatePicker, SystemFormControl, SystemOperationalButton, SystemTextarea } from "@/desyium"
import { approveStockAudit, createStockCountDraft, setItemContainer } from "@/resources/api"

const props = defineProps({ inventory: { type: Object, default: null } })
const emit = defineEmits(["changed"])
const postingDate = ref(localToday())
const notes = ref("")
const counts = reactive([])
const draft = ref(null)
const busy = ref(false)
const error = ref("")
function localToday() { const value = new Date(); return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}` }
function isContainerItem(item) { return Number(item.stock_container_size_qty) > 0 }
watch(() => props.inventory?.items, items => { counts.splice(0); (items || []).forEach(item => counts.push({ ...item, counted_qty: item.actual_qty, counted_containers: isContainerItem(item) ? Math.round((item.actual_qty / item.stock_container_size_qty) * 100) / 100 : 0 })) }, { immediate: true })
function effectiveQty(item) { return isContainerItem(item) ? Number(item.counted_containers) * Number(item.stock_container_size_qty) : Number(item.counted_qty) }
const changedCounts = computed(() => counts.filter(item => effectiveQty(item) !== Number(item.actual_qty)))
async function saveCount() { error.value = ""; if (!postingDate.value) { error.value = "Choose the count date."; return } if (!counts.length) { error.value = "There is no stock to count."; return } if (counts.some((item) => effectiveQty(item) < 0 || !Number.isFinite(effectiveQty(item)))) { error.value = "Every counted quantity must be zero or more."; return } busy.value = true; try { draft.value = await createStockCountDraft({ posting_date: postingDate.value, notes: notes.value, items: counts.map(item => ({ item_code: item.item_code, location: props.inventory.location, qty: Number(item.counted_qty), containers: Number(item.counted_containers) })) }) } catch (exception) { error.value = exception.message } finally { busy.value = false } }
const packEdit = ref("")
const packSize = ref(null)
const packLabel = ref("")

function openPackEdit(item) {
  packEdit.value = item.item_code
  packSize.value = Number(item.stock_container_size_qty) || null
  packLabel.value = item.stock_container_uom || ""
}

async function savePack(item) {
  error.value = ""
  busy.value = true
  try {
    const saved = await setItemContainer(item.item_code, Number(packSize.value) || 0, packLabel.value)
    item.stock_container_size_qty = saved.stock_container_size_qty
    item.stock_container_uom = saved.stock_container_uom
    item.counted_containers = isContainerItem(item)
      ? Math.round((item.actual_qty / item.stock_container_size_qty) * 100) / 100
      : 0
    packEdit.value = ""
  } catch (exception) { error.value = exception.message } finally { busy.value = false }
}

async function approve() { busy.value = true; error.value = ""; try { draft.value = await approveStockAudit(draft.value.name); emit("changed") } catch (exception) { error.value = exception.message } finally { busy.value = false } }
</script>

<template>
  <section data-block="stock-reconciliation" class="workflow-block">
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Count details</p><h2>Match the system to physical stock</h2><p>Enter what is present, review the differences, then approve the correction.</p></div></div>
      <SystemDatePicker v-model="postingDate" label="Posting date" format="YYYY-MM-DD" :disabled="Boolean(draft)" :clearable="false" />
      <label class="field-shell"><span>Count notes</span><SystemTextarea v-model="notes" :rows="3" :disabled="Boolean(draft)" placeholder="Who counted, where, and any unusual conditions" /></label>
      <div class="stock-counts" data-stock-counts>
        <div class="section-heading"><div><p class="eyebrow">{{ inventory?.location || "Ingredients" }}</p><h2>Physical counts and differences</h2></div><SystemBadge>{{ changedCounts.length }} differences</SystemBadge></div>
        <div class="measurement-list">
          <article v-for="item in counts" :key="item.item_code" class="measurement-row measurement-row--count" :class="{ 'is-different': effectiveQty(item) !== Number(item.actual_qty) }">
            <div><strong>{{ item.item_name }}</strong><small>System says {{ Number(item.actual_qty).toFixed(2) }} {{ item.stock_uom }}</small></div>
            <SystemFormControl v-if="isContainerItem(item)" v-model="item.counted_containers" type="number" :label="`Containers (${item.stock_container_uom || item.stock_container_size_qty + ' ' + item.stock_uom})`" min="0" step="1" size="lg" :disabled="Boolean(draft)" />
            <SystemFormControl v-else v-model="item.counted_qty" type="number" label="Counted" min="0" step="0.1" size="lg" :disabled="Boolean(draft)" />
            <div class="difference"><span>Difference</span><strong>{{ (effectiveQty(item) - Number(item.actual_qty)).toFixed(2) }} {{ item.stock_uom }}</strong></div>
            <div v-if="packEdit === item.item_code" class="pack-edit">
              <SystemFormControl v-model="packSize" type="number" :label="`One container holds (${item.stock_uom})`" min="0" step="0.01" />
              <SystemFormControl v-model="packLabel" :label="`Container name`" placeholder="e.g. 10 kg bag" />
              <SystemOperationalButton variant="solid" :loading="busy" @click="savePack(item)">Save</SystemOperationalButton>
              <SystemOperationalButton variant="ghost" @click="packEdit = ''">Cancel</SystemOperationalButton>
            </div>
            <SystemOperationalButton v-else class="pack-trigger" variant="ghost" size="sm" :disabled="Boolean(draft)" @click="openPackEdit(item)">
              {{ isContainerItem(item) ? "Change container size" : "Count in containers" }}
            </SystemOperationalButton>
          </article>
        </div>
      </div>
    </section>
    <footer class="posting-bar"><div><SystemBadge>{{ draft ? (draft.docstatus ? "STOCK RECONCILED" : "READY FOR APPROVAL") : "COUNT NOT SAVED" }}</SystemBadge><p>{{ draft ? (draft.docstatus ? "The approved differences are now reflected in stock." : "A manager must check and approve these differences before stock changes.") : "Saving creates a review draft only. Stock will not change yet." }}</p></div><SystemOperationalButton v-if="!draft" variant="outline" size="lg" :loading="busy" @click="saveCount">Save count draft</SystemOperationalButton><SystemOperationalButton v-else-if="!draft.docstatus" variant="solid" size="lg" :loading="busy" @click="approve">Approve reconciliation</SystemOperationalButton></footer>
  </section>
</template>

<style scoped>
.stock-counts {
  margin-top: var(--spacing-l);
}

.pack-trigger {
  grid-column: 1 / -1;
  justify-self: start;
  font-size: var(--font-size--2);
}

.pack-edit {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto auto;
  align-items: end;
  gap: var(--spacing-xs);
  grid-column: 1 / -1;
  padding-top: var(--spacing-xs);
  border-top: var(--border-width-1) solid var(--theme-border);
}

@media (max-width: 48rem) {
  .pack-edit { grid-template-columns: 1fr; }
}
</style>
