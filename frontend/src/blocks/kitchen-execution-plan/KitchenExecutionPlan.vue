<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { GraphChart } from "echarts/charts"
import { TooltipComponent } from "echarts/components"
import { use } from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import {
  SystemBadge,
  SystemCard,
  SystemChart,
  SystemCheckboxShadcn,
  SystemFormControl,
  SystemOperationalButton,
  SystemSelect,
} from "@/desyium"
import {
  getKitchenPlanSnapshot,
  getProductionInstructions,
  saveProductionEmployees,
} from "@/resources/api"

use([CanvasRenderer, GraphChart, TooltipComponent])

// =============================================================================
// region KITCHEN PLAN STATION
// =============================================================================

const props = defineProps({ runName: { type: String, required: true } })
const emit = defineEmits(["close", "open-employees", "changed"])
const workspace = ref(null)
const instructions = ref(null)
const busy = ref(false)
const error = ref("")
const saved = ref(false)
const teamTemplate = ref("")
const kitchenWindowHours = ref(0)
const actualElapsedHours = ref(0)
const employeeRows = reactive([])
const graphTheme = reactive({ surface: "transparent", criticalSurface: "transparent", text: "currentColor", border: "currentColor", critical: "currentColor" })

const run = computed(() => workspace.value?.run || null)
const employeeOptions = computed(() => workspace.value?.employees || [])
const employeeByName = computed(() => new Map(employeeOptions.value.map((row) => [row.value, row])))
const teamTemplates = computed(() => workspace.value?.team_templates || [])
const teamTemplateOptions = computed(() => teamTemplates.value.map((row) => ({ label: row.template_name, value: row.name })))
const attendanceOptions = ["Assigned", "Completed", "Absent", "Cancelled"].map((value) => ({ label: value, value }))
const activeTeam = computed(() => employeeRows.filter((row) => row.employee && !["Absent", "Cancelled"].includes(row.completion_status)))
const teamSize = computed(() => Math.max(activeTeam.value.length, 1))
const availableTeamHours = computed(() => activeTeam.value.reduce((sum, row) => sum + Number(row.available_hours || 0), 0))
const kitchenWindowMinutes = computed(() => Number(kitchenWindowHours.value || 0) * 60)
const outputQty = computed(() => Number(run.value?.planned_output_qty || instructions.value?.output_qty || 0))
const requiredTeamHours = computed(() => (instructions.value?.steps || []).reduce((total, step) => total + Number(step.estimated_minutes || 0) * Number(step.requires_active_worker === false ? 0 : step.minimum_workers || 1), 0) / 60)
const methodMinutes = computed(() => Number(instructions.value?.estimated_elapsed_minutes || 0))
const slowestAllowedPace = computed(() => outputQty.value && kitchenWindowMinutes.value ? kitchenWindowMinutes.value / outputQty.value : 0)
const expectedMethodPace = computed(() => outputQty.value ? methodMinutes.value / outputQty.value : 0)
const requiredPeople = computed(() => kitchenWindowHours.value ? Math.max(Math.ceil(requiredTeamHours.value / Number(kitchenWindowHours.value)), 1) : 0)
const peopleGap = computed(() => Math.max(requiredPeople.value - activeTeam.value.length, 0))
const workerCapacityRows = computed(() => (instructions.value?.worker_lanes || []).map((lane) => {
  const employee = activeTeam.value[lane.lane - 1]
  const availableMinutes = Number(employee?.available_hours || 0) * 60
  return { lane: lane.lane, availableMinutes, shortfallMinutes: Math.max(Number(lane.available_at || 0) - availableMinutes, 0) }
}))
const capacityStatus = computed(() => {
  if (!instructions.value || !activeTeam.value.length || !kitchenWindowMinutes.value) return "Capacity not ready"
  const short = methodMinutes.value > kitchenWindowMinutes.value + 0.1 || requiredTeamHours.value > availableTeamHours.value + 0.001 || workerCapacityRows.value.some((row) => row.shortfallMinutes > 0.1)
  return short ? "Under capacity" : "Ready to cook"
})
const capacityShortfallHours = computed(() => Math.max(
  methodMinutes.value - kitchenWindowMinutes.value,
  (requiredTeamHours.value - availableTeamHours.value) * 60,
  ...workerCapacityRows.value.map((row) => row.shortfallMinutes),
  0,
) / 60)
const actualPace = computed(() => outputQty.value && actualElapsedHours.value ? Number(actualElapsedHours.value) * 60 / outputQty.value : 0)
const paceStatus = computed(() => !actualPace.value || !slowestAllowedPace.value ? "Not measured" : actualPace.value <= slowestAllowedPace.value ? "Within takt" : "Slower than takt")

onMounted(() => {
  const styles = window.getComputedStyle(document.documentElement)
  graphTheme.surface = styles.getPropertyValue("--theme-surface-raised").trim() || "transparent"
  graphTheme.criticalSurface = styles.getPropertyValue("--theme-secondary").trim() || graphTheme.surface
  graphTheme.text = styles.getPropertyValue("--theme-text").trim() || "currentColor"
  graphTheme.border = styles.getPropertyValue("--theme-border").trim() || "currentColor"
  graphTheme.critical = styles.getPropertyValue("--theme-primary").trim() || graphTheme.border
  loadWorkspace()
})

async function loadWorkspace() {
  busy.value = true
  error.value = ""
  try {
    workspace.value = await getKitchenPlanSnapshot(props.runName)
    instructions.value = workspace.value.instructions
    hydrateRun(workspace.value.run)
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

function hydrateRun(value) {
  teamTemplate.value = value?.team_template || ""
  kitchenWindowHours.value = Number(value?.scheduled_elapsed_hours || 0)
  actualElapsedHours.value = Number(value?.actual_elapsed_hours || 0)
  employeeRows.splice(0, employeeRows.length, ...(value?.employees || []).map((row) => ({ ...row })))
  if (!employeeRows.length && teamTemplate.value) applyTeamTemplate()
}

function applyTeamTemplate() {
  const template = teamTemplates.value.find((row) => row.name === teamTemplate.value)
  if (!template) return
  if (!kitchenWindowHours.value) kitchenWindowHours.value = Number(template.default_elapsed_hours || 0)
  employeeRows.splice(0, employeeRows.length, ...(template.members || []).map((member) => {
    const employee = employeeByName.value.get(member.employee)
    return {
      employee: member.employee,
      employee_name: member.employee_name || employee?.label,
      employee_type: member.employee_type || employee?.employee_type,
      available_hours: Number(member.default_hours_override || employee?.available_hours_per_run || template.default_elapsed_hours || 0),
      custom_hours: false,
      hours_worked: 0,
      completion_status: "Assigned",
      notes: "",
    }
  }))
  rebuildPlan()
}

function addEmployee() {
  employeeRows.push({ employee: "", available_hours: Number(kitchenWindowHours.value || 0), custom_hours: false, hours_worked: 0, completion_status: "Assigned", notes: "" })
}

function changeEmployee(row, value) {
  row.employee = value
  const employee = employeeByName.value.get(value)
  row.employee_name = employee?.label || ""
  row.employee_type = employee?.employee_type || ""
  if (!Number(row.available_hours)) row.available_hours = Number(employee?.available_hours_per_run || kitchenWindowHours.value || 0)
}

function removeEmployee(index) {
  employeeRows.splice(index, 1)
}

async function rebuildPlan() {
  if (!run.value?.recipe || !outputQty.value) return
  busy.value = true
  error.value = ""
  try {
    instructions.value = await getProductionInstructions(run.value.recipe, outputQty.value, teamSize.value)
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

async function saveKitchenPlan() {
  if (run.value?.docstatus) return
  if (!employeeRows.some((row) => row.employee)) {
    error.value = "Assign at least one employee before saving the cooking plan."
    return
  }
  busy.value = true
  error.value = ""
  saved.value = false
  try {
    const updated = await saveProductionEmployees(
      run.value.name,
      employeeRows,
      teamTemplate.value,
      actualElapsedHours.value,
      kitchenWindowHours.value,
    )
    workspace.value = { ...workspace.value, run: updated }
    hydrateRun(updated)
    await rebuildPlan()
    saved.value = true
    emit("changed")
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

// endregion KITCHEN PLAN STATION

// =============================================================================
// region CPM DIAGRAM ADAPTER
// =============================================================================

const graphOption = computed(() => {
  const steps = instructions.value?.steps || []
  const finish = Math.max(Number(instructions.value?.estimated_elapsed_minutes || 0), 1)
  const lanes = Math.max(Number(instructions.value?.worker_lanes?.length || 1), 1)
  const nodes = steps.map((step, index) => {
    const lane = Number(step.assigned_workers?.[0] || (index % lanes) + 1)
    return {
      id: step.task_id,
      name: step.step_name,
      x: 90 + Number(step.scheduled_start || 0) / finish * 1000,
      y: 70 + (lane - 1) * 150 + (index % 2) * 18,
      symbol: "roundRect",
      symbolSize: [190, 94],
      itemStyle: {
        color: step.is_critical ? graphTheme.criticalSurface : graphTheme.surface,
        borderColor: step.is_critical ? graphTheme.critical : graphTheme.border,
        borderWidth: step.is_critical ? 2.5 : 1.5,
      },
      label: { formatter: `${step.step_number}. ${truncate(step.step_name, 24)}\n${time(step.scheduled_start)} to ${time(step.scheduled_end)}\n${startWindow(step)}` },
      step,
    }
  })
  const edges = steps.flatMap((step) => (step.depends_on_task_ids || []).map((source) => ({ source, target: step.task_id, lineStyle: { width: step.is_critical ? 2.5 : 1.4, color: step.is_critical ? graphTheme.critical : graphTheme.border } })))
  return {
    animation: false,
    tooltip: { trigger: "item", confine: true, formatter: graphTooltip },
    series: [{
      type: "graph",
      layout: "none",
      roam: true,
      draggable: false,
      data: nodes,
      edges,
      edgeSymbol: ["none", "arrow"],
      edgeSymbolSize: [0, 10],
      lineStyle: { opacity: 0.9, curveness: 0.06 },
      label: { show: true, color: graphTheme.text, fontSize: 11, lineHeight: 17, align: "center", verticalAlign: "middle" },
      emphasis: { focus: "adjacency", scale: 1.04 },
    }],
  }
})

function graphTooltip(params) {
  const step = params?.data?.step
  if (!step) return "Dependency"
  return `<strong>${escapeHtml(step.step_name)}</strong><br>${time(step.scheduled_start)} to ${time(step.scheduled_end)}<br>${escapeHtml(startWindow(step))}<br>${escapeHtml(workerNames(step))}${step.equipment_name ? `<br>${escapeHtml(step.equipment_name)}` : ""}`
}

function startWindow(step) {
  if (Number(step.slack_minutes || 0) <= 0.01) return `Start at ${time(step.early_start)}, no buffer`
  return `Start ${time(step.early_start)} to ${time(step.late_start)}, ${quantity(step.slack_minutes)} min buffer`
}

function workerNames(step) {
  if (step.requires_active_worker === false) return "Equipment running unattended"
  return (step.assigned_workers || []).map((lane) => workerName(lane)).join(" + ") || "Worker assignment pending"
}

function workerName(lane) {
  return activeTeam.value[lane - 1]?.employee_name || employeeByName.value.get(activeTeam.value[lane - 1]?.employee)?.label || `Worker ${lane}`
}

function workerCapacity(lane) {
  return workerCapacityRows.value.find((row) => row.lane === lane) || {}
}

function assistInstruction(step) {
  return `Help ${workerNames({ assigned_workers: step.assisting_workers })} with ${step.step_name}`
}

function time(minutes) {
  const total = Math.max(Math.round(Number(minutes || 0)), 0)
  return `${Math.floor(total / 60)}h ${String(total % 60).padStart(2, "0")}m`
}

function quantity(value) {
  return (Math.round(Number(value || 0) * 1000) / 1000).toLocaleString("en-ZA", { maximumFractionDigits: 3 })
}

function truncate(value, length) {
  const text = String(value || "")
  return text.length > length ? `${text.slice(0, length - 1)}…` : text
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character])
}

// endregion CPM DIAGRAM ADAPTER
</script>

<template>
  <section data-block="kitchen-execution-plan" class="kitchen-plan">
    <header class="kitchen-plan__header">
      <div>
        <p class="eyebrow">Cooking plan</p>
        <h1>{{ instructions?.recipe_name || run?.recipe || "Kitchen plan" }}</h1>
        <p v-if="run">Run {{ run.name }} · {{ quantity(run.planned_output_qty) }} kg target · {{ run.production_date }}</p>
        <p v-else>Loading the saved production run and cooking method.</p>
      </div>
      <div class="button-row">
        <SystemOperationalButton variant="outline" @click="emit('close')">Back to production</SystemOperationalButton>
        <SystemOperationalButton variant="outline" :loading="busy" @click="rebuildPlan">Rebuild plan</SystemOperationalButton>
        <SystemOperationalButton v-if="!run?.docstatus" variant="solid" :loading="busy" @click="saveKitchenPlan">Save cooking plan</SystemOperationalButton>
      </div>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="saved" class="state-message state-message--success" role="status">The team, kitchen window, and actual elapsed time are saved on this production run.</div>
    <div v-if="busy && !workspace" class="state-message" role="status">Building the equipment-aware cooking plan.</div>

    <template v-if="workspace && instructions">
      <SystemCard class="capacity-card" :class="capacityStatus === 'Under capacity' ? 'is-under' : capacityStatus === 'Ready to cook' ? 'is-ready' : 'is-neutral'">
        <div class="capacity-card__decision">
          <p class="eyebrow">Practical capacity</p>
          <h2>{{ capacityStatus }}</h2>
          <p v-if="capacityStatus === 'Capacity not ready'">Assign the team and enter the kitchen window before starting.</p>
          <p v-else-if="capacityStatus === 'Under capacity'">This method exceeds the present team, individual availability, or kitchen window by about {{ quantity(capacityShortfallHours) }} hours. Change the setup and rebuild the plan before cooking.</p>
          <p v-else>The selected team, equipment, and kitchen window can complete this cooking plan.</p>
          <SystemBadge v-if="capacityStatus === 'Under capacity' && peopleGap" theme="red">Add at least {{ peopleGap }} {{ peopleGap === 1 ? "person" : "people" }} by team-hours</SystemBadge>
        </div>
        <div class="capacity-card__evidence">
          <div><strong>{{ time(methodMinutes) }}</strong><span>expected cooking time</span></div>
          <div><strong>{{ time(kitchenWindowMinutes) }}</strong><span>time available</span></div>
          <div><strong>{{ quantity(requiredTeamHours) }} h</strong><span>team-hours needed</span></div>
          <div><strong>{{ quantity(availableTeamHours) }} h</strong><span>team-hours available</span></div>
          <div><strong>{{ quantity(expectedMethodPace) }} min/kg</strong><span>expected method pace</span></div>
          <div><strong>{{ quantity(slowestAllowedPace) }} min/kg</strong><span>slowest allowable pace</span></div>
          <div><strong>{{ requiredPeople }}</strong><span>people required by team-hours</span></div>
          <div><strong>{{ activeTeam.length }}</strong><span>people assigned</span></div>
        </div>
      </SystemCard>

      <section class="plan-section team-section">
        <div class="section-heading">
          <div><p class="eyebrow">Team and time</p><h2>Assign the people doing this cook</h2><p>Apply a normal team, adjust each person’s availability, and set the total kitchen window.</p></div>
          <div class="button-row"><SystemOperationalButton variant="ghost" @click="emit('open-employees')">Manage employees</SystemOperationalButton><SystemOperationalButton v-if="!run.docstatus" variant="outline" @click="addEmployee">Add employee</SystemOperationalButton></div>
        </div>
        <div class="team-controls">
          <SystemSelect v-model="teamTemplate" label="Team template" :options="teamTemplateOptions" placeholder="Choose a saved team" :disabled="Boolean(run.docstatus)" />
          <SystemOperationalButton variant="outline" :disabled="Boolean(run.docstatus) || !teamTemplate" @click="applyTeamTemplate">Apply template</SystemOperationalButton>
          <SystemFormControl v-model="kitchenWindowHours" label="Kitchen time available (hours)" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" />
        </div>
        <div class="employee-list">
          <article v-for="(row, index) in employeeRows" :key="`${index}-${row.employee}`">
            <SystemSelect :model-value="row.employee" label="Employee" :options="employeeOptions" :disabled="Boolean(run.docstatus)" @update:model-value="changeEmployee(row, $event)" />
            <SystemSelect v-model="row.completion_status" label="Work status" :options="attendanceOptions" :disabled="Boolean(run.docstatus)" />
            <SystemFormControl v-model="row.available_hours" label="Hours available" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" />
            <SystemCheckboxShadcn v-model="row.custom_hours" label="Custom actual hours" :disabled="Boolean(run.docstatus)" />
            <SystemFormControl v-if="row.custom_hours" v-model="row.hours_worked" label="Hours worked" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" />
            <SystemFormControl v-model="row.notes" label="Notes" :disabled="Boolean(run.docstatus)" />
            <SystemOperationalButton v-if="!run.docstatus" variant="ghost" @click="removeEmployee(index)">Remove</SystemOperationalButton>
          </article>
        </div>
      </section>

      <section class="plan-section cpm-section">
        <div class="section-heading">
          <div><p class="eyebrow">Critical path</p><h2>Cooking dependency diagram</h2><p>Follow the arrows. Orange nodes have no safe delay. Drag or zoom the diagram to inspect a larger plan.</p></div>
          <SystemBadge>{{ quantity(instructions.critical_path_minutes) }} min CPM path</SystemBadge>
        </div>
        <div class="cpm-canvas" role="img" :aria-label="`Cooking plan dependency graph with ${instructions.steps.length} tasks and ${instructions.critical_path_minutes} critical-path minutes`">
          <SystemChart autoresize :option="graphOption" />
        </div>
        <div class="cpm-legend" aria-hidden="true"><span><i class="is-critical"></i>Critical, start on time</span><span><i></i>Buffered task</span><span>Scroll to zoom · drag to pan</span></div>
        <ol class="accessible-task-list">
          <li v-for="step in instructions.steps" :key="step.task_id">
            <strong>{{ step.step_number }}. {{ step.step_name }}</strong>
            <span>{{ startWindow(step) }}. Scheduled {{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }}. {{ workerNames(step) }}<template v-if="step.equipment_name"> using {{ step.equipment_name }}</template>.</span>
          </li>
        </ol>
      </section>

      <section class="plan-section">
        <div class="section-heading"><div><p class="eyebrow">Ingredients</p><h2>Weigh before cooking</h2><p>These are raw recipe quantities. Equipment batching is calculated separately from configured capacity.</p></div><SystemBadge>{{ instructions.ingredients.length }} ITEMS</SystemBadge></div>
        <div class="ingredient-list">
          <article v-for="item in instructions.ingredients" :key="item.item_code"><div><strong>{{ item.item_name }}</strong><small>Weigh before cooking</small></div><span><b>{{ quantity(item.quantity) }} {{ item.uom }}</b><template v-if="item.piece_count_estimate"> · about {{ item.piece_count_estimate }} {{ item.piece_count_label }}</template></span></article>
        </div>
      </section>

      <section class="plan-section">
        <div class="section-heading"><div><p class="eyebrow">Worker lanes</p><h2>Who does what, and when</h2><p>Assist handoffs fill safe idle gaps without shortening the official task estimate.</p></div><SystemBadge>{{ instructions.worker_lanes.length }} LANES</SystemBadge></div>
        <div class="worker-lanes">
          <article v-for="lane in instructions.worker_lanes" :key="lane.lane">
            <header><div><span>Worker {{ lane.lane }}</span><strong>{{ workerName(lane.lane) }}</strong><small>Scheduled until {{ time(lane.available_at) }} · available until {{ time(workerCapacity(lane.lane).availableMinutes) }}</small></div><SystemBadge v-if="workerCapacity(lane.lane).shortfallMinutes > 0" theme="red">{{ quantity(workerCapacity(lane.lane).shortfallMinutes) }} min late</SystemBadge></header>
            <ol><li v-for="step in lane.steps" :key="`${lane.lane}-${step.kind || 'primary'}-${step.task_id}-${step.start_minute}`" :class="{ 'is-assist': step.kind === 'assist' }"><span>{{ time(step.start_minute) }} to {{ time(step.end_minute) }}</span><strong>{{ step.kind === "assist" ? assistInstruction(step) : `${step.step_number}. ${step.step_name}` }}</strong><small>{{ quantity(step.duration_minutes) }} min<template v-if="step.equipment_type"> · {{ step.equipment_type }}</template></small><SystemBadge v-if="step.kind === 'assist'" theme="green">Assist</SystemBadge><SystemBadge v-else-if="step.is_critical" theme="red">Critical</SystemBadge></li></ol>
          </article>
        </div>
      </section>

      <section class="plan-section method-section">
        <div class="section-heading"><div><p class="eyebrow">Method</p><h2>Step-by-step cooking instructions</h2><p>Open a task for the detailed method, checks, equipment, batch load, and safe start window.</p></div><SystemBadge>{{ instructions.steps.length }} TASKS</SystemBadge></div>
        <div class="method-list">
          <details v-for="step in instructions.steps" :key="step.task_id">
            <summary><span>{{ step.step_number }}</span><div><strong>{{ step.step_name }}</strong><small>{{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }} · {{ workerNames(step) }}<template v-if="step.equipment_name"> · {{ step.equipment_name }}</template></small></div><SystemBadge v-if="step.is_critical" theme="red">Critical</SystemBadge><b>Open method</b></summary>
            <div class="method-body">
              <p>{{ step.objective || step.instruction }}</p>
              <ol><li v-for="substep in step.substeps" :key="substep.order"><span>{{ substep.order }}</span><div><p>{{ substep.instruction }}</p><small v-if="substep.check">Check: {{ substep.check }}</small></div></li></ol>
              <div class="method-facts">
                <span>{{ startWindow(step) }}</span><span>{{ quantity(step.estimated_minutes) }} min estimated</span><span v-if="step.equipment_name">{{ step.equipment_name }}</span><span v-if="step.batch_count > 1">Batch {{ step.batch_index }} of {{ step.batch_count }} · {{ quantity(step.batch_load_qty) }} {{ step.batch_capacity_uom }} load</span><span>{{ step.requires_active_worker === false ? "Equipment runs unattended" : `${step.minimum_workers} active ${step.minimum_workers === 1 ? "worker" : "workers"}` }}</span>
              </div>
              <p v-if="step.quality_checkpoint" class="quality-check"><strong>Check:</strong> {{ step.quality_checkpoint }}</p>
            </div>
          </details>
        </div>
      </section>

      <section class="plan-section equipment-section">
        <div class="section-heading"><div><p class="eyebrow">Equipment</p><h2>Configured cooking capacity</h2><p>Batch nodes above use the capacity, quantity, and simultaneous-batch limit recorded for each equipment type.</p></div></div>
        <div class="equipment-grid"><article v-for="item in instructions.equipment" :key="item.name"><strong>{{ item.equipment_type_name }}</strong><span>{{ quantity(item.capacity_qty) }} {{ item.capacity_uom }} per batch</span><small>{{ item.quantity_available }} available · {{ item.concurrent_batch_limit }} simultaneous {{ Number(item.concurrent_batch_limit) === 1 ? "batch" : "batches" }} each</small><b>{{ quantity(item.total_concurrent_capacity) }} {{ item.capacity_uom }} at once</b></article></div>
      </section>

      <section class="plan-section actual-time-section">
        <div><p class="eyebrow">Actual timing</p><h2>How long did the complete cook take?</h2><p>This evidence is stored on the production run and may inform future AI duration proposals. It does not silently replace the approved method.</p></div>
        <SystemFormControl v-model="actualElapsedHours" label="Actual elapsed time (hours)" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" />
        <div class="actual-time-result" :class="paceStatus === 'Slower than takt' ? 'is-under' : 'is-ready'"><strong>{{ paceStatus }}</strong><span>{{ quantity(actualPace) }} min/kg actual · {{ quantity(slowestAllowedPace) }} min/kg slowest allowable</span></div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.kitchen-plan{display:grid;gap:var(--spacing-m);width:100%;min-width:0;padding:var(--spacing-l) 0}.kitchen-plan__header,.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--spacing-m)}.kitchen-plan__header h1,.section-heading h2,.capacity-card h2{margin:0;color:var(--theme-text)}.kitchen-plan__header p,.section-heading p,.capacity-card p{margin:var(--spacing-3xs) 0 0;color:var(--theme-text-muted)}.eyebrow{margin:0!important;color:var(--theme-primary)!important;font-size:.75rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.button-row{display:flex;flex-wrap:wrap;gap:var(--spacing-xs)}.state-message,.plan-section{padding:var(--spacing-m);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.state-message--error{border-color:var(--theme-danger);color:var(--theme-danger)}.state-message--success{border-color:var(--theme-success);color:var(--theme-success)}.capacity-card{display:grid;grid-template-columns:minmax(16rem,.7fr) minmax(0,1.3fr);gap:var(--spacing-m);padding:var(--spacing-m);border:2px solid var(--theme-border);background:var(--theme-surface-raised)}.capacity-card.is-under{border-color:color-mix(in oklch,var(--theme-danger) 55%,var(--theme-border));background:color-mix(in oklch,var(--theme-danger) 7%,var(--theme-surface-raised))}.capacity-card.is-ready{border-color:color-mix(in oklch,var(--theme-success) 50%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface-raised))}.capacity-card__decision{display:grid;align-content:start;gap:var(--spacing-xs)}.capacity-card__evidence{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--spacing-xs)}.capacity-card__evidence div{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-xs);border:var(--border-width-1) solid color-mix(in oklch,var(--theme-border) 75%,transparent);border-radius:var(--component-radius-control);background:color-mix(in oklch,var(--theme-surface-raised) 75%,transparent)}.capacity-card__evidence strong{font-size:1.15rem;font-variant-numeric:tabular-nums}.capacity-card__evidence span,.employee-list small,.worker-lanes small,.equipment-grid small{color:var(--theme-text-muted);font-size:.78rem}.plan-section{display:grid;gap:var(--spacing-s)}.team-controls{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(12rem,.5fr);align-items:end;gap:var(--spacing-xs)}.employee-list{display:grid;gap:var(--spacing-xs)}.employee-list article{display:grid;grid-template-columns:1.2fr .8fr .65fr .8fr .8fr 1fr auto;align-items:end;gap:var(--spacing-xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-control);background:var(--theme-surface)}.cpm-canvas{width:100%;height:clamp(30rem,68vh,52rem);min-width:0;overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.cpm-canvas :deep(.system-chart){width:100%;height:100%;min-height:30rem}.cpm-legend{display:flex;flex-wrap:wrap;gap:var(--spacing-s);color:var(--theme-text-muted);font-size:.8rem}.cpm-legend span{display:inline-flex;align-items:center;gap:var(--spacing-3xs)}.cpm-legend i{width:1rem;height:1rem;border:1px solid var(--theme-border);border-radius:.3rem;background:var(--theme-surface-raised)}.cpm-legend i.is-critical{border:2px solid var(--theme-primary);background:color-mix(in oklch,var(--theme-primary) 10%,var(--theme-surface-raised))}.accessible-task-list{position:fixed!important;inset:0 auto auto 0!important;width:1px!important;height:1px!important;margin:0!important;padding:0!important;overflow:hidden!important;clip-path:inset(50%)!important;white-space:nowrap!important}.ingredient-list{display:grid}.ingredient-list article{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding:var(--spacing-xs) 0;border-bottom:var(--border-width-1) solid var(--theme-border)}.ingredient-list article:last-child{border-bottom:0}.ingredient-list article>div{display:grid;gap:var(--spacing-3xs)}.ingredient-list small,.ingredient-list article>span{color:var(--theme-text-muted)}.ingredient-list b{color:var(--theme-text);font-variant-numeric:tabular-nums}.worker-lanes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--spacing-xs)}.worker-lanes>article{overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface)}.worker-lanes header{display:flex;justify-content:space-between;gap:var(--spacing-xs);padding:var(--spacing-xs);border-bottom:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.worker-lanes header div{display:grid;gap:var(--spacing-3xs)}.worker-lanes ol{display:grid;gap:var(--spacing-2xs);margin:0;padding:var(--spacing-xs);list-style:none}.worker-lanes li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:var(--spacing-3xs) var(--spacing-xs);padding:var(--spacing-xs);border-left:3px solid var(--theme-border);border-radius:0 var(--component-radius-control) var(--component-radius-control) 0;background:var(--theme-surface-raised)}.worker-lanes li.is-assist{border-left-color:var(--theme-success);background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface-raised))}.worker-lanes li>span,.worker-lanes li>small{grid-column:1/-1}.method-list{display:grid;gap:var(--spacing-xs)}.method-list details{overflow:hidden;border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-control);background:var(--theme-surface)}.method-list summary{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:var(--spacing-xs);padding:var(--spacing-xs);cursor:pointer;list-style:none}.method-list summary>span:first-child{display:grid;place-items:center;width:2rem;height:2rem;border-radius:50%;background:var(--theme-secondary);font-weight:800}.method-list summary div{display:grid;gap:var(--spacing-3xs)}.method-list summary small,.method-list summary>b{color:var(--theme-text-muted);font-size:.78rem}.method-body{display:grid;gap:var(--spacing-s);padding:var(--spacing-s);border-top:var(--border-width-1) solid var(--theme-border);background:var(--theme-surface-raised)}.method-body>ol{display:grid;gap:var(--spacing-xs);margin:0;padding:0;list-style:none}.method-body>ol>li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--spacing-xs)}.method-body>ol>li>span{display:grid;place-items:center;width:1.75rem;height:1.75rem;border-radius:50%;background:var(--theme-secondary);font-weight:800}.method-body p{margin:0}.method-facts{display:flex;flex-wrap:wrap;gap:var(--spacing-2xs)}.method-facts span{padding:.35rem .55rem;border-radius:999px;background:var(--theme-secondary);color:var(--theme-text-muted);font-size:.78rem}.quality-check{padding:var(--spacing-xs);border-left:3px solid var(--theme-success);background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface-raised))}.equipment-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--spacing-xs)}.equipment-grid article{display:grid;gap:var(--spacing-3xs);padding:var(--spacing-xs);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-control);background:var(--theme-surface)}.actual-time-section{grid-template-columns:minmax(0,1fr) minmax(14rem,.45fr);align-items:end}.actual-time-result{grid-column:1/-1;display:flex;justify-content:space-between;gap:var(--spacing-xs);padding:var(--spacing-xs);border-left:3px solid var(--theme-success);background:color-mix(in oklch,var(--theme-success) 6%,var(--theme-surface-raised))}.actual-time-result.is-under{border-left-color:var(--theme-danger);background:color-mix(in oklch,var(--theme-danger) 7%,var(--theme-surface-raised))}@media(max-width:75rem){.capacity-card{grid-template-columns:1fr}.capacity-card__evidence{grid-template-columns:repeat(2,minmax(0,1fr))}.employee-list article{grid-template-columns:repeat(3,minmax(0,1fr))}.worker-lanes{grid-template-columns:1fr}}@media(max-width:48rem){.kitchen-plan{padding:var(--spacing-s) 0}.kitchen-plan__header,.section-heading{display:grid}.button-row{width:100%}.button-row :deep(button){flex:1 1 auto}.capacity-card__evidence{grid-template-columns:1fr 1fr}.team-controls,.employee-list article,.actual-time-section,.equipment-grid{grid-template-columns:1fr}.cpm-canvas{height:34rem}.method-list summary{grid-template-columns:auto minmax(0,1fr) auto}.method-list summary>b{grid-column:2/-1}.ingredient-list article{align-items:flex-start;flex-direction:column}.actual-time-result{display:grid}}
</style>
