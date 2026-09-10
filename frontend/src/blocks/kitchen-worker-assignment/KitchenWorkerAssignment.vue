<script setup>
import { computed, onMounted, ref } from "vue"
import {
  SystemAccordion,
  SystemAccordionContent,
  SystemAccordionItem,
  SystemAccordionTrigger,
  SystemBadge,
  SystemLogo,
} from "@/desyium"
import bulkbiteWordmark from "@/assets/bulkbite-logo-wordmark-dark.svg"
import { resolveKitchenAssignment } from "@/resources/api"


// =============================================================================
// region WORKER ASSIGNMENT STATION
// =============================================================================

const props = defineProps({ token: { type: String, required: true } })
const assignment = ref(null)
const loading = ref(true)
const error = ref("")

const employee = computed(() => assignment.value?.employee || {})
const lane = computed(() => assignment.value?.lane || { steps: [] })
const instructions = computed(() => assignment.value?.instructions || { ingredients: [], equipment: [], steps: [] })
const run = computed(() => assignment.value?.run || {})

onMounted(loadAssignment)

async function loadAssignment() {
  loading.value = true
  error.value = ""
  try {
    assignment.value = await resolveKitchenAssignment(props.token)
  } catch (exception) {
    error.value = exception.message || "This kitchen link is invalid or no longer available."
  } finally {
    loading.value = false
  }
}

function time(minutes) {
  const total = Math.max(Math.round(Number(minutes || 0)), 0)
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m`
}

function quantity(value) {
  return (Math.round(Number(value || 0) * 1000) / 1000).toLocaleString("en-ZA", { maximumFractionDigits: 3 })
}

function laneInstruction(step) {
  if (step.kind !== "assist") return `${step.step_number}. ${step.step_name}`
  const people = (step.assist_with || []).join(" and ") || "the assigned worker"
  return `Help ${people} with ${step.step_name}`
}

function startWindow(step) {
  if (Number(step.slack_minutes || 0) <= 0.01) return `Start at ${time(step.early_start)}, no buffer`
  return `Start ${time(step.early_start)} to ${time(step.late_start)}, ${quantity(step.slack_minutes)} min buffer`
}

function ingredientDetail(row) {
  const details = []
  if (row.piece_count_estimate) details.push(`about ${quantity(row.piece_count_estimate)} ${row.piece_count_label || "pieces"}`)
  if (row.preparation_yield_note) details.push(row.preparation_yield_note)
  return details.join(" · ")
}


// endregion WORKER ASSIGNMENT STATION
</script>

<template>
  <main data-block="kitchen-worker-assignment" class="worker-assignment">
    <header class="worker-assignment__brand">
      <SystemLogo name="BulkBite" :src="bulkbiteWordmark" href="#" compact @click.prevent />
      <SystemBadge v-if="assignment" theme="green">Private work link</SystemBadge>
    </header>

    <section v-if="loading" class="worker-state" role="status" aria-live="polite">
      <span class="worker-state__mark" aria-hidden="true"></span>
      <div><p class="eyebrow">Kitchen assignment</p><h1>Loading your work</h1><p>BulkBite is preparing the current cooking instructions.</p></div>
    </section>

    <section v-else-if="error" class="worker-state worker-state--error" role="alert">
      <div><p class="eyebrow">Kitchen link unavailable</p><h1>Ask your manager for a new link</h1><p>{{ error }}</p></div>
    </section>

    <template v-else-if="assignment">
      <header class="worker-hero">
        <div>
          <p class="eyebrow">Your cooking assignment</p>
          <h1>{{ employee.full_name }}</h1>
          <p>{{ run.recipe_name }} · Run {{ run.name }} · {{ run.production_date }}</p>
        </div>
        <div class="worker-hero__facts">
          <div><strong>Worker {{ employee.lane }}</strong><span>your lane</span></div>
          <div><strong>{{ quantity(run.output_qty) }} {{ run.output_uom }}</strong><span>total meal target</span></div>
          <div><strong>{{ time(lane.available_at) }}</strong><span>your scheduled work</span></div>
          <div><strong>{{ time(instructions.estimated_elapsed_minutes) }}</strong><span>expected kitchen time</span></div>
        </div>
      </header>

      <section class="worker-card worker-card--priority" aria-labelledby="your-work-title">
        <div class="section-heading">
          <div><p class="eyebrow">Your work</p><h2 id="your-work-title">Follow this lane in order</h2><p>Assist cards show where you can help while your own task is waiting.</p></div>
          <SystemBadge>{{ lane.steps.length }} ACTIONS</SystemBadge>
        </div>
        <ol class="lane-list">
          <li v-for="step in lane.steps" :key="`${step.kind || 'primary'}-${step.task_id}-${step.start_minute}`" :class="{ 'is-assist': step.kind === 'assist' }">
            <div class="lane-list__time"><strong>{{ time(step.start_minute) }}</strong><span>to {{ time(step.end_minute) }}</span></div>
            <div><strong>{{ laneInstruction(step) }}</strong><small>{{ quantity(step.duration_minutes) }} min<template v-if="step.equipment_type"> · {{ step.equipment_type }}</template></small></div>
            <SystemBadge v-if="step.kind === 'assist'" theme="green">Assist</SystemBadge>
            <SystemBadge v-else-if="step.is_critical" theme="red">Critical</SystemBadge>
          </li>
        </ol>
      </section>

      <SystemAccordion type="multiple" :default-value="['method']" class="worker-sections">
        <SystemAccordionItem value="method" class="worker-card worker-section">
          <SystemAccordionTrigger class="worker-section__trigger">
            <div class="section-heading"><div><p class="eyebrow">Complete method</p><h2>All cooking instructions</h2><p>Use this when you need to understand the whole cook or help another worker.</p></div><SystemBadge>{{ instructions.steps.length }} TASKS</SystemBadge></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="worker-section__content">
            <div class="method-list">
              <details v-for="step in instructions.steps" :key="step.task_id">
                <summary>
                  <span>{{ step.step_number }}</span>
                  <div><strong>{{ step.step_name }}</strong><small>{{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }}<template v-if="step.equipment_name"> · {{ step.equipment_name }}</template></small></div>
                  <SystemBadge v-if="step.is_critical" theme="red">Critical</SystemBadge>
                  <b>Open method</b>
                </summary>
                <div class="method-body">
                  <p>{{ step.objective || step.instruction }}</p>
                  <ol><li v-for="substep in step.substeps || []" :key="substep.order"><span>{{ substep.order }}</span><div><p>{{ substep.instruction }}</p><small v-if="substep.check">Check: {{ substep.check }}</small></div></li></ol>
                  <div class="method-facts"><span>{{ startWindow(step) }}</span><span>{{ quantity(step.estimated_minutes) }} min estimated</span><span v-if="step.equipment_name">{{ step.equipment_name }}</span><span v-if="step.batch_count > 1">Batch {{ step.batch_index }} of {{ step.batch_count }} · {{ quantity(step.batch_load_qty) }} {{ step.batch_capacity_uom }}</span><span>{{ step.requires_active_worker === false ? "Equipment runs unattended" : `${step.minimum_workers} active ${step.minimum_workers === 1 ? "worker" : "workers"}` }}</span></div>
                  <p v-if="step.quality_checkpoint" class="quality-check"><strong>Check:</strong> {{ step.quality_checkpoint }}</p>
                </div>
              </details>
            </div>
          </SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="ingredients" class="worker-card worker-section">
          <SystemAccordionTrigger class="worker-section__trigger">
            <div class="section-heading"><div><p class="eyebrow">Ingredients</p><h2>Weigh before cooking</h2><p>These are the raw quantities for the complete cook.</p></div><SystemBadge>{{ instructions.ingredients.length }} ITEMS</SystemBadge></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="worker-section__content">
            <div class="ingredient-list"><article v-for="row in instructions.ingredients" :key="row.item_code"><div><strong>{{ row.item_name }}</strong><small v-if="ingredientDetail(row)">{{ ingredientDetail(row) }}</small></div><b>{{ quantity(row.quantity) }} {{ row.uom }}</b></article></div>
          </SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="equipment" class="worker-card worker-section">
          <SystemAccordionTrigger class="worker-section__trigger">
            <div class="section-heading"><div><p class="eyebrow">Equipment</p><h2>Equipment needed</h2><p>Use the recorded capacity and batching limits shown here.</p></div><SystemBadge>{{ instructions.equipment.length }} TYPES</SystemBadge></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="worker-section__content">
            <div class="equipment-grid"><article v-for="row in instructions.equipment" :key="row.name"><strong>{{ row.equipment_type_name }}</strong><span>{{ row.quantity_available }} available · {{ row.capacity_qty }} {{ row.capacity_uom }} each</span><small>{{ row.concurrent_batch_limit }} simultaneous {{ row.concurrent_batch_limit === 1 ? "batch" : "batches" }} per item</small></article></div>
          </SystemAccordionContent>
        </SystemAccordionItem>
      </SystemAccordion>
    </template>
  </main>
</template>

<style scoped>
.worker-assignment{width:100%;max-width:76rem;min-height:100dvh;margin:0 auto;padding:clamp(var(--spacing-m),4vw,var(--spacing-xl-2xl));color:var(--theme-text)}
.worker-assignment__brand{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);margin-bottom:var(--spacing-m)}
.worker-assignment__brand :deep(.system-logo){width:min(10rem,45vw);min-height:0}.worker-assignment__brand :deep(.system-logo__mark){width:100%;height:auto}
.worker-state,.worker-hero,.worker-card{border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-block);background:var(--theme-surface);box-shadow:0 1px 2px color-mix(in oklch,var(--theme-text) 5%,transparent)}
.worker-state{display:flex;align-items:center;gap:var(--spacing-m);padding:var(--spacing-l);min-height:14rem}.worker-state--error{border-color:color-mix(in oklch,var(--theme-error) 45%,var(--theme-border));background:color-mix(in oklch,var(--theme-error) 7%,var(--theme-surface-raised))}.worker-state__mark{width:1.25rem;height:1.25rem;border:.18rem solid var(--theme-border);border-top-color:var(--theme-primary);border-radius:50%;animation:worker-spin .8s linear infinite}
.worker-hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(22rem,1.15fr);gap:var(--spacing-m);padding:var(--spacing-l);margin-bottom:var(--spacing-m);background:color-mix(in oklch,var(--theme-primary) 6%,var(--theme-surface-raised))}.worker-hero h1{margin:var(--spacing-3xs) 0;font-size:clamp(1.75rem,5vw,2.75rem);line-height:1.05}.worker-hero__facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-xs)}.worker-hero__facts div{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface)}.worker-hero__facts span,.section-heading p,.lane-list small,.method-list small,.ingredient-list small,.equipment-grid span,.equipment-grid small{color:var(--theme-text-muted)}
.worker-card{min-width:0;overflow:hidden}.worker-card--priority{padding:var(--spacing-m);margin-bottom:var(--spacing-m)}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-s)}.section-heading h2{margin:var(--spacing-3xs) 0}.section-heading p{margin:0}.eyebrow{margin:0;color:var(--theme-primary)!important;font-size:var(--font-size--2);font-weight:var(--font-weight-700);letter-spacing:.08em;text-transform:uppercase}
.lane-list{display:grid;gap:var(--spacing-xs);padding:0;margin:var(--spacing-m) 0 0;list-style:none}.lane-list li{display:grid;grid-template-columns:7rem minmax(0,1fr) auto;align-items:center;gap:var(--spacing-xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface)}.lane-list li.is-assist{border-color:color-mix(in oklch,var(--theme-success) 38%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 7%,var(--theme-surface))}.lane-list li>div{display:grid;gap:var(--spacing-3xs)}.lane-list__time{font-variant-numeric:tabular-nums}
.worker-sections{display:grid;gap:var(--spacing-s)}:deep(.worker-section__trigger){width:100%;border:0!important;color:var(--theme-text);text-align:left;text-decoration:none!important}:deep(.worker-section__trigger:hover){text-decoration:none!important}:deep(.worker-section__trigger:hover *){text-decoration:none!important}:deep(.worker-section__content){border:0!important}.worker-section__trigger .section-heading{width:100%;padding-right:var(--spacing-xs)}
.method-list,.ingredient-list,.equipment-grid{display:grid;gap:var(--spacing-xs)}.method-list details{overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface-raised)}.method-list summary{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:var(--spacing-xs);padding:var(--spacing-s);cursor:pointer;list-style:none}.method-list summary::-webkit-details-marker{display:none}.method-list summary>span:first-child,.method-body>ol>li>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:50%;background:var(--theme-primary);color:var(--theme-primary-foreground);font-weight:var(--font-weight-700)}.method-list summary div{display:grid;gap:var(--spacing-3xs)}.method-list summary>b{font-size:var(--font-size--2)}.method-body{display:grid;gap:var(--spacing-s);padding:var(--spacing-s);border-top:var(--border-width-1) solid var(--theme-border)}.method-body>ol{display:grid;gap:var(--spacing-xs);padding:0;margin:0;list-style:none}.method-body>ol>li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--spacing-xs)}.method-body p{margin:0}.method-facts{display:flex;flex-wrap:wrap;gap:var(--spacing-2xs)}.method-facts span{padding:var(--spacing-3xs) var(--spacing-2xs);border-radius:999px;background:var(--theme-field);font-size:var(--font-size--2)}.quality-check{padding:var(--spacing-xs);border-left:.25rem solid var(--theme-primary);background:color-mix(in oklch,var(--theme-primary) 7%,var(--theme-surface))}
.ingredient-list article{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding:var(--spacing-xs);border-bottom:var(--border-width-1) solid var(--theme-border)}.ingredient-list article:last-child{border-bottom:0}.ingredient-list article>div{display:grid;gap:var(--spacing-3xs)}.ingredient-list b{white-space:nowrap}.equipment-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.equipment-grid article{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-field);background:var(--theme-surface-raised)}
@keyframes worker-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.worker-state__mark{animation:none}}
@media(max-width:48rem){.worker-assignment{padding:var(--spacing-s)}.worker-hero{grid-template-columns:1fr;padding:var(--spacing-m)}.section-heading{display:grid}.lane-list li{grid-template-columns:5.6rem minmax(0,1fr)}.lane-list li :deep(.system-badge){grid-column:2}.equipment-grid{grid-template-columns:1fr}.method-list summary{grid-template-columns:auto minmax(0,1fr) auto}.method-list summary>b{grid-column:2/-1}.worker-section__trigger .section-heading{display:grid}}
@media(max-width:30rem){.worker-assignment{padding:var(--spacing-xs)}.worker-assignment__brand{padding:var(--spacing-2xs)}.worker-hero__facts{grid-template-columns:1fr}.worker-card--priority,:deep(.worker-section__trigger),:deep(.worker-section__content){padding:var(--spacing-s)!important}.lane-list li{grid-template-columns:1fr}.lane-list li :deep(.system-badge){grid-column:auto}.lane-list__time{display:flex!important;gap:var(--spacing-3xs)!important}.ingredient-list article{align-items:flex-start;flex-direction:column}.method-list summary{grid-template-columns:auto minmax(0,1fr)}.method-list summary :deep(.system-badge),.method-list summary>b{grid-column:2}}
</style>
