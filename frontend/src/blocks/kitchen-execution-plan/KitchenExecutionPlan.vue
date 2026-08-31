<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { Handle, MarkerType, Position } from "@vue-flow/core"
import bulkbiteWordmark from "@/assets/bulkbite-logo-wordmark-dark.svg"
import {
  SystemAccordion,
  SystemAccordionContent,
  SystemAccordionItem,
  SystemAccordionTrigger,
  SystemBadge,
  SystemFlow,
  SystemFormControl,
  SystemOperationalButton,
  SystemSelect,
} from "@/desyium"
import {
  generateKitchenAssignmentLink,
  getKitchenAssignmentLinks,
  getKitchenPlanSnapshot,
  getProductionInstructions,
  revokeKitchenAssignmentLink,
  saveKitchenPlanTeam,
} from "@/resources/api"

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
const employeeRows = reactive([])
const assignmentLinks = ref({ can_manage: false, links: [] })
const generatedLinks = reactive({})
const linkBusyEmployee = ref("")
const copiedEmployee = ref("")

const run = computed(() => workspace.value?.run || null)
const employeeOptions = computed(() => workspace.value?.employees || [])
const employeeByName = computed(() => new Map(employeeOptions.value.map((row) => [row.value, row])))
const teamTemplates = computed(() => workspace.value?.team_templates || [])
const teamTemplateOptions = computed(() => teamTemplates.value.map((row) => ({ label: row.template_name, value: row.name })))
const activeTeam = computed(() => employeeRows.filter((row) => row.employee))
const savedEmployeeIds = computed(() => new Set((run.value?.employees || []).map((row) => row.employee).filter(Boolean)))
const assignmentLinkByEmployee = computed(() => new Map((assignmentLinks.value.links || []).map((row) => [row.employee, row])))
const teamSize = computed(() => Math.max(activeTeam.value.length, 1))
const availableTeamHours = computed(() => activeTeam.value.reduce((sum, row) => sum + Number(row.available_hours || 0), 0))
const kitchenWindowMinutes = computed(() => Number(kitchenWindowHours.value || 0) * 60)
const outputQty = computed(() => Number(run.value?.planned_output_qty || instructions.value?.output_qty || 0))
const requiredTeamHours = computed(() => (instructions.value?.steps || []).reduce((total, step) => total + Number(step.estimated_minutes || 0) * Number(step.requires_active_worker === false ? 0 : step.minimum_workers || 1), 0) / 60)
const methodMinutes = computed(() => Number(instructions.value?.estimated_elapsed_minutes || 0))
const slowestAllowedPace = computed(() => outputQty.value && kitchenWindowMinutes.value ? kitchenWindowMinutes.value / outputQty.value : 0)
const expectedMethodPace = computed(() => outputQty.value ? methodMinutes.value / outputQty.value : 0)
const minimumTaskCrew = computed(() => Math.max(...(instructions.value?.steps || []).filter((step) => step.requires_active_worker !== false).map((step) => Number(step.minimum_workers || 1)), 0))
const requiredPeople = computed(() => kitchenWindowHours.value ? Math.max(Math.ceil(requiredTeamHours.value / Number(kitchenWindowHours.value)), minimumTaskCrew.value, 1) : 0)
const peopleGap = computed(() => Math.max(requiredPeople.value - activeTeam.value.length, 0))
const teamHourBalance = computed(() => availableTeamHours.value - requiredTeamHours.value)
const kitchenTimeBalanceHours = computed(() => Number(kitchenWindowHours.value || 0) - methodMinutes.value / 60)
const workerCapacityRows = computed(() => (instructions.value?.worker_lanes || []).map((lane) => {
  const employee = activeTeam.value[lane.lane - 1]
  const availableMinutes = Number(employee?.available_hours || 0) * 60
  return { lane: lane.lane, availableMinutes, shortfallMinutes: Math.max(Number(lane.available_at || 0) - availableMinutes, 0) }
}))
const capacityStatus = computed(() => {
  if (!instructions.value || !activeTeam.value.length || !kitchenWindowMinutes.value) return "Capacity not ready"
  const short = peopleGap.value > 0 || methodMinutes.value > kitchenWindowMinutes.value + 0.1 || requiredTeamHours.value > availableTeamHours.value + 0.001 || workerCapacityRows.value.some((row) => row.shortfallMinutes > 0.1)
  return short ? "Under capacity" : "Ready to cook"
})
watch(kitchenWindowHours, syncEmployeeAvailability)

onMounted(loadWorkspace)

async function loadWorkspace() {
  busy.value = true
  error.value = ""
  try {
    workspace.value = await getKitchenPlanSnapshot(props.runName)
    instructions.value = workspace.value.instructions
    hydrateRun(workspace.value.run)
    await loadAssignmentLinks()
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

async function loadAssignmentLinks() {
  try {
    assignmentLinks.value = await getKitchenAssignmentLinks(props.runName)
  } catch (exception) {
    assignmentLinks.value = { can_manage: false, links: [] }
    if (!error.value) error.value = exception.message
  }
}

function hydrateRun(value) {
  teamTemplate.value = value?.team_template || ""
  kitchenWindowHours.value = Number(value?.scheduled_elapsed_hours || 0)
  employeeRows.splice(0, employeeRows.length, ...(value?.employees || []).map((row) => ({
    ...row,
    available_hours: Number(row.custom_hours ? row.available_hours : value?.scheduled_elapsed_hours || 0),
    custom_hours: Boolean(row.custom_hours),
  })))
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
      available_hours: Number(kitchenWindowHours.value || 0),
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
  row.available_hours = Number(kitchenWindowHours.value || 0)
  row.custom_hours = false
  rebuildPlan()
}

function syncEmployeeAvailability(value) {
  const sharedHours = Math.max(Number(value || 0), 0)
  employeeRows.forEach((row) => {
    if (!row.custom_hours) row.available_hours = sharedHours
  })
}

function updateEmployeeAvailability(row, value) {
  row.available_hours = Math.max(Number(value || 0), 0)
  row.custom_hours = true
}

function restoreAutomaticAvailability(row) {
  row.custom_hours = false
  row.available_hours = Math.max(Number(kitchenWindowHours.value || 0), 0)
}

function removeEmployee(index) {
  employeeRows.splice(index, 1)
  rebuildPlan()
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
    const updated = await saveKitchenPlanTeam(
      run.value.name,
      employeeRows,
      teamTemplate.value,
      kitchenWindowHours.value,
    )
    workspace.value = { ...workspace.value, run: updated }
    hydrateRun(updated)
    await rebuildPlan()
    await loadAssignmentLinks()
    saved.value = true
    emit("changed")
  } catch (exception) {
    error.value = exception.message
  } finally {
    busy.value = false
  }
}

async function generateEmployeeLink(employee) {
  if (!employee || linkBusyEmployee.value) return
  linkBusyEmployee.value = employee
  error.value = ""
  copiedEmployee.value = ""
  try {
    const result = await generateKitchenAssignmentLink(run.value.name, employee)
    generatedLinks[employee] = new URL(result.path, window.location.origin).href
    await loadAssignmentLinks()
  } catch (exception) {
    error.value = exception.message
  } finally {
    linkBusyEmployee.value = ""
  }
}

async function copyEmployeeLink(employee) {
  const url = generatedLinks[employee]
  if (!url) return
  try {
    await navigator.clipboard.writeText(url)
    copiedEmployee.value = employee
  } catch {
    copiedEmployee.value = ""
  }
}

async function revokeEmployeeLink(employee) {
  if (!employee || linkBusyEmployee.value) return
  linkBusyEmployee.value = employee
  error.value = ""
  try {
    await revokeKitchenAssignmentLink(run.value.name, employee)
    delete generatedLinks[employee]
    copiedEmployee.value = ""
    await loadAssignmentLinks()
  } catch (exception) {
    error.value = exception.message
  } finally {
    linkBusyEmployee.value = ""
  }
}

function assignmentLink(employee) {
  return assignmentLinkByEmployee.value.get(employee) || null
}

function linkStatusTheme(status) {
  if (status === "Active") return "green"
  if (status === "Revoked") return "red"
  return "gray"
}

// endregion KITCHEN PLAN STATION

// =============================================================================
// region CPM FLOW ADAPTER
// =============================================================================

const FLOW_NODE_WIDTH = 236
const FLOW_NODE_HEIGHT = 132
const FLOW_JUNCTION_SIZE = 24
const FLOW_COLUMN_GAP = 54
const FLOW_ROW_GAP = 112
const FLOW_TIME_LABEL_WIDTH = 148
const FLOW_TIME_GUTTER = 52

const flowElements = computed(() => {
  const steps = instructions.value?.steps || []
  const dependencyGroups = buildDependencyGroups(steps)
  const layout = buildConcurrentFlowLayout(steps, dependencyGroups.junctions)
  const stepById = new Map(steps.map((step) => [step.task_id, step]))
  const taskNodes = steps.map((step) => {
    return {
      id: step.task_id,
      type: "cpm-task",
      position: layout.taskPositions.get(step.task_id),
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      draggable: false,
      selectable: true,
      data: { step },
    }
  })
  const junctionNodes = dependencyGroups.junctions.map((junction) => {
    return {
      id: junction.id,
      type: "cpm-junction",
      position: layout.junctionPositions.get(junction.id),
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      draggable: false,
      selectable: false,
      data: { critical: junction.critical },
    }
  })
  const timeNodes = layout.columns.map((column) => ({
    id: `time-${column.startMinute}`,
    type: "cpm-time",
    position: { x: 0, y: column.y + (FLOW_NODE_HEIGHT - 48) / 2 },
    draggable: false,
    selectable: false,
    data: {
      startMinute: column.startMinute,
      concurrentCount: column.steps.length,
    },
  }))
  const edges = dependencyGroups.edges.map((edge) => {
    const sourceCritical = stepById.get(edge.source)?.is_critical ?? dependencyGroups.junctionById.get(edge.source)?.critical
    const targetCritical = stepById.get(edge.target)?.is_critical ?? dependencyGroups.junctionById.get(edge.target)?.critical
    const critical = Boolean(sourceCritical && targetCritical)
    return {
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
      class: critical ? "cpm-edge cpm-edge--critical" : "cpm-edge",
      style: { strokeWidth: critical ? 2.5 : 1.5 },
    }
  })
  return { nodes: [...timeNodes, ...taskNodes, ...junctionNodes], edges, taskNodeCount: taskNodes.length }
})

function buildConcurrentFlowLayout(steps, junctions) {
  const columns = buildTimeColumns(steps)
  const maximumConcurrentTasks = Math.max(...columns.map((column) => column.steps.length), 1)
  const maximumRowWidth = maximumConcurrentTasks * FLOW_NODE_WIDTH + (maximumConcurrentTasks - 1) * FLOW_COLUMN_GAP
  const taskPositions = new Map()

  columns.forEach((column, rowIndex) => {
    column.y = rowIndex * (FLOW_NODE_HEIGHT + FLOW_ROW_GAP)
    const rowWidth = column.steps.length * FLOW_NODE_WIDTH + (column.steps.length - 1) * FLOW_COLUMN_GAP
    const rowOffset = (maximumRowWidth - rowWidth) / 2
    column.steps.forEach((step, columnIndex) => {
      taskPositions.set(step.task_id, {
        x: FLOW_TIME_LABEL_WIDTH + FLOW_TIME_GUTTER + rowOffset + columnIndex * (FLOW_NODE_WIDTH + FLOW_COLUMN_GAP),
        y: column.y,
      })
    })
  })

  const junctionPositions = new Map()
  junctions.forEach((junction) => {
    const sourcePositions = junction.sources.map((id) => taskPositions.get(id)).filter(Boolean)
    const targetPositions = junction.targets.map((id) => taskPositions.get(id)).filter(Boolean)
    const sourceBottom = Math.max(...sourcePositions.map((position) => position.y + FLOW_NODE_HEIGHT))
    const targetTop = Math.min(...targetPositions.map((position) => position.y))
    const connectedCenters = [...sourcePositions, ...targetPositions].map((position) => position.x + FLOW_NODE_WIDTH / 2)
    junctionPositions.set(junction.id, {
      x: connectedCenters.reduce((sum, value) => sum + value, 0) / connectedCenters.length - FLOW_JUNCTION_SIZE / 2,
      y: sourceBottom + (targetTop - sourceBottom - FLOW_JUNCTION_SIZE) / 2,
    })
  })

  return { columns, taskPositions, junctionPositions }
}

function buildTimeColumns(steps) {
  const columnsByStart = new Map()
  steps.forEach((step) => {
    const startMinute = Math.round(Number(step.scheduled_start || 0))
    if (!columnsByStart.has(startMinute)) columnsByStart.set(startMinute, [])
    columnsByStart.get(startMinute).push(step)
  })
  return [...columnsByStart.entries()]
    .sort(([left], [right]) => left - right)
    .map(([startMinute, columnSteps]) => ({
      startMinute,
      steps: columnSteps.sort(compareConcurrentTasks),
      x: 0,
    }))
}

function compareConcurrentTasks(left, right) {
  const leftWorker = Number(left.assigned_workers?.[0] || Number.MAX_SAFE_INTEGER)
  const rightWorker = Number(right.assigned_workers?.[0] || Number.MAX_SAFE_INTEGER)
  return leftWorker - rightWorker || Number(left.step_number || 0) - Number(right.step_number || 0)
}

function buildDependencyGroups(steps) {
  const groups = new Map()
  steps.forEach((step) => {
    const sources = [...(step.depends_on_task_ids || [])].sort()
    if (!sources.length) return
    const key = sources.join("|")
    if (!groups.has(key)) groups.set(key, { sources, targets: [] })
    groups.get(key).targets.push(step.task_id)
  })

  const edges = []
  const junctions = []
  groups.forEach((group, key) => {
    if (group.sources.length > 1 && group.targets.length > 1) {
      const id = `junction-${junctions.length + 1}`
      const connectedSteps = steps.filter((step) => group.sources.includes(step.task_id) || group.targets.includes(step.task_id))
      const junction = {
        id,
        sources: group.sources,
        targets: group.targets,
        critical: connectedSteps.length > 0 && connectedSteps.every((step) => step.is_critical),
      }
      junctions.push(junction)
      group.sources.forEach((source) => edges.push({ source, target: id }))
      group.targets.forEach((target) => edges.push({ source: id, target }))
      return
    }
    group.targets.forEach((target) => group.sources.forEach((source) => edges.push({ source, target })))
  })
  return { edges, junctions, junctionById: new Map(junctions.map((junction) => [junction.id, junction])) }
}

function fitFlow(instance) {
  window.requestAnimationFrame(() => instance.fitView({ padding: 0.12, minZoom: 0.35, maxZoom: 1 }))
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

function printKitchenPack() {
  window.print()
}

// endregion CPM FLOW ADAPTER
</script>

<template>
  <section data-block="kitchen-execution-plan" class="kitchen-plan workflow-block">
    <div class="kitchen-plan__screen">
    <header class="workflow-header">
      <div>
        <p class="eyebrow">Cooking plan</p>
        <h1>{{ instructions?.recipe_name || run?.recipe || "Kitchen plan" }}</h1>
        <p v-if="run">Run {{ run.name }} · {{ quantity(run.planned_output_qty) }} kg target · {{ run.production_date }}</p>
        <p v-else>Loading the saved production run and cooking method.</p>
      </div>
      <div class="button-row">
        <SystemOperationalButton variant="outline" @click="emit('close')">Back to production</SystemOperationalButton>
        <SystemOperationalButton variant="outline" :loading="busy" @click="rebuildPlan">Rebuild plan</SystemOperationalButton>
        <SystemOperationalButton variant="outline" :disabled="!instructions || !activeTeam.length" @click="printKitchenPack">Print kitchen pack</SystemOperationalButton>
        <SystemOperationalButton v-if="!run?.docstatus" variant="solid" :loading="busy" @click="saveKitchenPlan">Save cooking plan</SystemOperationalButton>
      </div>
    </header>

    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <div v-if="saved" class="state-message state-message--success" role="status">The planned team and kitchen window are saved on this production run.</div>
    <div v-if="busy && !workspace" class="state-message" role="status">Building the equipment-aware cooking plan.</div>

    <template v-if="workspace && instructions">
      <section class="data-section capacity-card" :class="capacityStatus === 'Under capacity' ? 'is-under' : capacityStatus === 'Ready to cook' ? 'is-ready' : 'is-neutral'">
        <div class="capacity-card__decision">
          <p class="eyebrow">Practical capacity</p>
          <h2>{{ capacityStatus }}</h2>
          <p v-if="capacityStatus === 'Capacity not ready'">Assign the team and enter the kitchen window before starting.</p>
          <p v-else-if="capacityStatus === 'Under capacity'">The method needs {{ requiredPeople }} people, {{ quantity(requiredTeamHours) }} team-hours, and {{ quantity(methodMinutes / 60) }} kitchen hours. The current setup provides {{ activeTeam.length }} people, {{ quantity(availableTeamHours) }} team-hours, and {{ quantity(kitchenWindowHours) }} kitchen hours.</p>
          <p v-else>The selected team, equipment, and kitchen window can complete this cooking plan.</p>
          <SystemBadge v-if="capacityStatus === 'Under capacity' && peopleGap" theme="red">Add at least {{ peopleGap }} {{ peopleGap === 1 ? "person" : "people" }} by team-hours</SystemBadge>
        </div>
        <div class="capacity-card__evidence">
          <div><strong>{{ time(methodMinutes) }}</strong><span>expected cooking time</span></div>
          <div><strong>{{ time(kitchenWindowMinutes) }}</strong><span>time available</span></div>
          <div><strong>{{ quantity(requiredTeamHours) }} h</strong><span>team-hours needed</span></div>
          <div><strong>{{ quantity(availableTeamHours) }} h</strong><span>team-hours available</span></div>
          <div><strong>{{ quantity(Math.abs(teamHourBalance)) }} h</strong><span>{{ teamHourBalance < 0 ? "team-hours missing" : "team-hours spare" }}</span></div>
          <div><strong>{{ quantity(Math.abs(kitchenTimeBalanceHours)) }} h</strong><span>{{ kitchenTimeBalanceHours < 0 ? "kitchen time missing" : "kitchen time spare" }}</span></div>
          <div><strong>{{ quantity(expectedMethodPace) }} min/kg</strong><span>expected method pace</span></div>
          <div><strong>{{ quantity(slowestAllowedPace) }} min/kg</strong><span>slowest allowable pace</span></div>
          <div><strong>{{ requiredPeople }}</strong><span>minimum people required</span></div>
          <div><strong>{{ activeTeam.length }}</strong><span>people assigned</span></div>
        </div>
      </section>

      <SystemAccordion type="multiple" :default-value="['team', 'critical-path', 'ingredients', 'worker-lanes', 'method']" class="plan-sections">
        <SystemAccordionItem value="team" class="plan-section team-section">
          <SystemAccordionTrigger class="section-trigger">
            <div class="section-heading"><div><p class="eyebrow">Team and time</p><h2>Assign the people doing this cook</h2><p>Apply a normal team and set the kitchen window. Employee availability follows it unless you enter a different value.</p></div><SystemBadge>{{ activeTeam.length }} PEOPLE</SystemBadge></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="section-content">
            <div class="section-actions"><div class="button-row"><SystemOperationalButton variant="ghost" @click="emit('open-employees')">Manage employees</SystemOperationalButton><SystemOperationalButton v-if="!run.docstatus" variant="outline" @click="addEmployee">Add employee</SystemOperationalButton></div></div>
            <div class="team-controls">
              <SystemSelect v-model="teamTemplate" label="Team template" :options="teamTemplateOptions" placeholder="Choose a saved team" :disabled="Boolean(run.docstatus)" />
              <SystemOperationalButton variant="outline" :disabled="Boolean(run.docstatus) || !teamTemplate" @click="applyTeamTemplate">Apply template</SystemOperationalButton>
              <SystemFormControl v-model="kitchenWindowHours" label="Kitchen time available (hours)" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" />
            </div>
            <div class="employee-list">
              <article v-for="(row, index) in employeeRows" :key="`${index}-${row.employee}`">
                <div class="employee-list__fields">
                  <SystemSelect :model-value="row.employee" label="Employee" :options="employeeOptions" :disabled="Boolean(run.docstatus)" @update:model-value="changeEmployee(row, $event)" />
                  <div class="employee-availability">
                    <SystemFormControl :model-value="row.available_hours" label="Hours available" type="number" min="0" step="0.1" :disabled="Boolean(run.docstatus)" @update:model-value="updateEmployeeAvailability(row, $event)" />
                    <SystemOperationalButton v-if="row.custom_hours && !run.docstatus" variant="ghost" @click="restoreAutomaticAvailability(row)">Use kitchen time</SystemOperationalButton>
                  </div>
                  <SystemFormControl v-model="row.notes" label="Notes" :disabled="Boolean(run.docstatus)" />
                  <SystemOperationalButton v-if="!run.docstatus" variant="ghost" @click="removeEmployee(index)">Remove</SystemOperationalButton>
                </div>
                <div v-if="assignmentLinks.can_manage && row.employee" class="assignment-link">
                  <div>
                    <span>Employee cooking link</span>
                    <small v-if="!savedEmployeeIds.has(row.employee)">Save the cooking plan before generating this link.</small>
                    <small v-else-if="generatedLinks[row.employee]">Anyone holding this link can read the assignment. Copy it now and share it only with this employee.</small>
                    <small v-else-if="assignmentLink(row.employee)?.status === 'Active'">An active link exists. Regenerate it if you need a new copy.</small>
                    <small v-else>Generate a private link that opens only this employee's work and the complete method.</small>
                  </div>
                  <SystemBadge v-if="assignmentLink(row.employee)" :theme="linkStatusTheme(assignmentLink(row.employee).status)">{{ assignmentLink(row.employee).status }}</SystemBadge>
                  <SystemFormControl v-if="generatedLinks[row.employee]" :model-value="generatedLinks[row.employee]" label="Private link" readonly :aria-label="`Private cooking link for ${row.employee_name}`" />
                  <div class="button-row">
                    <SystemOperationalButton variant="outline" :loading="linkBusyEmployee === row.employee" :disabled="!savedEmployeeIds.has(row.employee) || Boolean(linkBusyEmployee)" @click="generateEmployeeLink(row.employee)">{{ assignmentLink(row.employee)?.status === 'Active' ? 'Regenerate link' : 'Generate link' }}</SystemOperationalButton>
                    <SystemOperationalButton v-if="generatedLinks[row.employee]" variant="ghost" @click="copyEmployeeLink(row.employee)">{{ copiedEmployee === row.employee ? "Copied" : "Copy link" }}</SystemOperationalButton>
                    <SystemOperationalButton v-if="assignmentLink(row.employee)?.status === 'Active'" variant="ghost" :disabled="Boolean(linkBusyEmployee)" @click="revokeEmployeeLink(row.employee)">Revoke</SystemOperationalButton>
                  </div>
                </div>
              </article>
            </div>
          </SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="critical-path" class="plan-section cpm-section">
          <SystemAccordionTrigger class="section-trigger">
            <div class="section-heading"><div><p class="eyebrow">Critical path</p><h2>Cooking dependency diagram</h2><p>Time moves down the plan. Actions on the same row happen concurrently, and arrows show what must finish before the next row can begin.</p></div><SystemBadge>{{ quantity(instructions.critical_path_minutes) }} min CPM</SystemBadge></div>
          </SystemAccordionTrigger>
          <SystemAccordionContent class="section-content">
            <div class="cpm-canvas" :aria-label="`Cooking plan dependency graph with ${instructions.steps.length} tasks and ${instructions.critical_path_minutes} critical-path minutes`">
              <SystemFlow
                :nodes="flowElements.nodes"
                :edges="flowElements.edges"
                :nodes-draggable="false"
                :nodes-connectable="false"
                :edges-updatable="false"
                :elements-selectable="true"
                :fit-view-on-init="true"
                :min-zoom="0.25"
                :max-zoom="1.5"
                :default-edge-options="{ type: 'smoothstep' }"
                @init="fitFlow"
              >
                <template #node-cpm-task="{ data }">
                  <article class="cpm-node" :class="{ 'is-critical': data.step.is_critical }">
                    <Handle type="target" :position="Position.Top" :connectable="false" />
                    <div class="cpm-node__top"><span>Step {{ data.step.step_number }}</span><SystemBadge v-if="data.step.is_critical" theme="red">Critical</SystemBadge></div>
                    <strong>{{ data.step.step_name }}</strong>
                    <small>{{ time(data.step.scheduled_start) }} to {{ time(data.step.scheduled_end) }}</small>
                    <small>{{ workerNames(data.step) }}</small>
                    <small v-if="data.step.equipment_name">{{ data.step.equipment_name }}</small>
                    <b>{{ startWindow(data.step) }}</b>
                    <Handle type="source" :position="Position.Bottom" :connectable="false" />
                  </article>
                </template>
                <template #node-cpm-junction="{ data }">
                  <span class="cpm-junction" :class="{ 'is-critical': data.critical }" aria-hidden="true">
                    <Handle type="target" :position="Position.Top" :connectable="false" />
                    <i></i>
                    <Handle type="source" :position="Position.Bottom" :connectable="false" />
                  </span>
                </template>
                <template #node-cpm-time="{ data }">
                  <div class="cpm-time" aria-hidden="true">
                    <strong>{{ time(data.startMinute) }}</strong>
                    <span>{{ data.concurrentCount > 1 ? `${data.concurrentCount} actions together` : "1 action" }}</span>
                  </div>
                </template>
              </SystemFlow>
            </div>
            <div class="cpm-legend" aria-hidden="true"><span><i class="is-critical"></i>Critical, start on time</span><span><i></i>Buffered task</span><span>Scroll to zoom · drag the background to pan</span></div>
            <ol class="accessible-task-list">
              <li v-for="step in instructions.steps" :key="step.task_id"><strong>{{ step.step_number }}. {{ step.step_name }}</strong><span>{{ startWindow(step) }}. Scheduled {{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }}. {{ workerNames(step) }}<template v-if="step.equipment_name"> using {{ step.equipment_name }}</template>.</span></li>
            </ol>
          </SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="ingredients" class="plan-section">
          <SystemAccordionTrigger class="section-trigger"><div class="section-heading"><div><p class="eyebrow">Ingredients</p><h2>Weigh before cooking</h2><p>These are raw recipe quantities. Equipment batching uses configured capacity.</p></div><SystemBadge>{{ instructions.ingredients.length }} ITEMS</SystemBadge></div></SystemAccordionTrigger>
          <SystemAccordionContent class="section-content"><div class="ingredient-list"><article v-for="item in instructions.ingredients" :key="item.item_code"><div><strong>{{ item.item_name }}</strong><small>Weigh before cooking</small></div><span><b>{{ quantity(item.quantity) }} {{ item.uom }}</b><template v-if="item.piece_count_estimate"> · about {{ item.piece_count_estimate }} {{ item.piece_count_label }}</template></span></article></div></SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="worker-lanes" class="plan-section">
          <SystemAccordionTrigger class="section-trigger"><div class="section-heading"><div><p class="eyebrow">Worker lanes</p><h2>Who does what, and when</h2><p>Assist handoffs fill safe idle gaps without shortening the official task estimate.</p></div><SystemBadge>{{ instructions.worker_lanes.length }} LANES</SystemBadge></div></SystemAccordionTrigger>
          <SystemAccordionContent class="section-content"><div class="worker-lanes"><article v-for="lane in instructions.worker_lanes" :key="lane.lane"><header><div><span>Worker {{ lane.lane }}</span><strong>{{ workerName(lane.lane) }}</strong><small>Scheduled until {{ time(lane.available_at) }} · available until {{ time(workerCapacity(lane.lane).availableMinutes) }}</small></div><SystemBadge v-if="workerCapacity(lane.lane).shortfallMinutes > 0" theme="red">{{ quantity(workerCapacity(lane.lane).shortfallMinutes) }} min late</SystemBadge></header><ol><li v-for="step in lane.steps" :key="`${lane.lane}-${step.kind || 'primary'}-${step.task_id}-${step.start_minute}`" :class="{ 'is-assist': step.kind === 'assist' }"><span>{{ time(step.start_minute) }} to {{ time(step.end_minute) }}</span><strong>{{ step.kind === "assist" ? assistInstruction(step) : `${step.step_number}. ${step.step_name}` }}</strong><small>{{ quantity(step.duration_minutes) }} min<template v-if="step.equipment_type"> · {{ step.equipment_type }}</template></small><SystemBadge v-if="step.kind === 'assist'" theme="green">Assist</SystemBadge><SystemBadge v-else-if="step.is_critical" theme="red">Critical</SystemBadge></li></ol></article></div></SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="method" class="plan-section method-section">
          <SystemAccordionTrigger class="section-trigger"><div class="section-heading"><div><p class="eyebrow">Method</p><h2>Step-by-step cooking instructions</h2><p>Open this section, then open any task for its detailed method and checks.</p></div><SystemBadge>{{ instructions.steps.length }} TASKS</SystemBadge></div></SystemAccordionTrigger>
          <SystemAccordionContent class="section-content"><div class="method-list"><details v-for="step in instructions.steps" :key="step.task_id"><summary><span>{{ step.step_number }}</span><div><strong>{{ step.step_name }}</strong><small>{{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }} · {{ workerNames(step) }}<template v-if="step.equipment_name"> · {{ step.equipment_name }}</template></small></div><SystemBadge v-if="step.is_critical" theme="red">Critical</SystemBadge><b>Open method</b></summary><div class="method-body"><p>{{ step.objective || step.instruction }}</p><ol><li v-for="substep in step.substeps" :key="substep.order"><span>{{ substep.order }}</span><div><p>{{ substep.instruction }}</p><small v-if="substep.check">Check: {{ substep.check }}</small></div></li></ol><div class="method-facts"><span>{{ startWindow(step) }}</span><span>{{ quantity(step.estimated_minutes) }} min estimated</span><span v-if="step.equipment_name">{{ step.equipment_name }}</span><span v-if="step.batch_count > 1">Batch {{ step.batch_index }} of {{ step.batch_count }} · {{ quantity(step.batch_load_qty) }} {{ step.batch_capacity_uom }} load</span><span>{{ step.requires_active_worker === false ? "Equipment runs unattended" : `${step.minimum_workers} active ${step.minimum_workers === 1 ? "worker" : "workers"}` }}</span></div><p v-if="step.quality_checkpoint" class="quality-check"><strong>Check:</strong> {{ step.quality_checkpoint }}</p></div></details></div></SystemAccordionContent>
        </SystemAccordionItem>

        <SystemAccordionItem value="equipment" class="plan-section equipment-section">
          <SystemAccordionTrigger class="section-trigger"><div class="section-heading"><div><p class="eyebrow">Equipment</p><h2>Configured cooking capacity</h2><p>Batch nodes use the recorded capacity, quantity, and simultaneous-batch limit.</p></div><SystemBadge>{{ instructions.equipment.length }} TYPES</SystemBadge></div></SystemAccordionTrigger>
          <SystemAccordionContent class="section-content"><div class="equipment-grid"><article v-for="item in instructions.equipment" :key="item.name"><strong>{{ item.equipment_type_name }}</strong><span>{{ quantity(item.capacity_qty) }} {{ item.capacity_uom }} per batch</span><small>{{ item.quantity_available }} available · {{ item.concurrent_batch_limit }} simultaneous {{ Number(item.concurrent_batch_limit) === 1 ? "batch" : "batches" }} each</small><b>{{ quantity(item.total_concurrent_capacity) }} {{ item.capacity_uom }} at once</b></article></div></SystemAccordionContent>
        </SystemAccordionItem>

      </SystemAccordion>
    </template>
    </div>

    <div v-if="workspace && instructions" class="print-kitchen-pack">
      <section v-for="lane in instructions.worker_lanes" :key="`print-worker-${lane.lane}`" class="print-page print-worker-page">
        <header class="print-page__header"><img :src="bulkbiteWordmark" alt="BulkBite" /><span>Kitchen worker sheet</span></header>
        <div class="print-page__title"><p>Worker {{ lane.lane }}</p><h1>{{ workerName(lane.lane) }}</h1><span>{{ instructions.recipe_name }} · Run {{ run.name }} · {{ quantity(run.planned_output_qty) }} kg · {{ run.production_date }}</span></div>
        <div class="print-summary"><div><strong>{{ time(lane.available_at) }}</strong><span>lane finish</span></div><div><strong>{{ quantity(activeTeam[lane.lane - 1]?.available_hours) }} h</strong><span>available</span></div><div><strong>{{ lane.steps.length }}</strong><span>actions</span></div></div>
        <ol class="print-task-list">
          <li v-for="step in lane.steps" :key="`print-${lane.lane}-${step.kind || 'primary'}-${step.task_id}-${step.start_minute}`" :class="{ 'is-assist': step.kind === 'assist' }">
            <div class="print-task-list__time">{{ time(step.start_minute) }}<span>to {{ time(step.end_minute) }}</span></div>
            <div><strong>{{ step.kind === "assist" ? assistInstruction(step) : `${step.step_number}. ${step.step_name}` }}</strong><p>{{ quantity(step.duration_minutes) }} min<template v-if="step.equipment_type"> · {{ step.equipment_type }}</template></p></div>
            <b>{{ step.kind === "assist" ? "Assist" : step.is_critical ? "Critical" : "Task" }}</b>
          </li>
        </ol>
      </section>

      <section class="print-page print-shared-page print-method-page">
        <header class="print-page__header"><img :src="bulkbiteWordmark" alt="BulkBite" /><span>Complete cooking method</span></header>
        <div class="print-page__title"><p>Shared method</p><h1>{{ instructions.recipe_name }}</h1><span>Run {{ run.name }} · {{ quantity(run.planned_output_qty) }} kg · expected {{ time(instructions.estimated_elapsed_minutes) }}</span></div>
        <ol class="print-method-list">
          <li v-for="step in instructions.steps" :key="`print-method-${step.task_id}`">
            <span>{{ step.step_number }}</span>
            <div><h2>{{ step.step_name }}</h2><p>{{ time(step.scheduled_start) }} to {{ time(step.scheduled_end) }} · {{ workerNames(step) }}<template v-if="step.equipment_name"> · {{ step.equipment_name }}</template></p><p>{{ step.objective || step.instruction }}</p><ol><li v-for="substep in step.substeps" :key="`print-substep-${step.task_id}-${substep.order}`"><strong>{{ substep.order }}.</strong> {{ substep.instruction }}<small v-if="substep.check">Check: {{ substep.check }}</small></li></ol><p v-if="step.quality_checkpoint"><strong>Final check:</strong> {{ step.quality_checkpoint }}</p></div>
          </li>
        </ol>
      </section>

      <section class="print-page print-shared-page">
        <header class="print-page__header"><img :src="bulkbiteWordmark" alt="BulkBite" /><span>Ingredients</span></header>
        <div class="print-page__title"><p>Weigh before cooking</p><h1>{{ instructions.recipe_name }}</h1><span>{{ instructions.ingredients.length }} ingredients · {{ quantity(run.planned_output_qty) }} kg target</span></div>
        <table><thead><tr><th>Ingredient</th><th>Quantity to weigh</th><th>Practical estimate</th></tr></thead><tbody><tr v-for="item in instructions.ingredients" :key="`print-ingredient-${item.item_code}`"><td>{{ item.item_name }}</td><td>{{ quantity(item.quantity) }} {{ item.uom }}</td><td>{{ item.piece_count_estimate ? `About ${item.piece_count_estimate} ${item.piece_count_label}` : "Weigh on scale" }}</td></tr></tbody></table>
      </section>

      <section class="print-page print-shared-page print-equipment-page">
        <header class="print-page__header"><img :src="bulkbiteWordmark" alt="BulkBite" /><span>Equipment</span></header>
        <div class="print-page__title"><p>Kitchen setup</p><h1>Equipment required</h1><span>{{ instructions.equipment.length }} configured equipment types</span></div>
        <table><thead><tr><th>Equipment</th><th>Available</th><th>Capacity</th><th>Can run together</th></tr></thead><tbody><tr v-for="item in instructions.equipment" :key="`print-equipment-${item.name}`"><td>{{ item.equipment_type_name }}</td><td>{{ item.quantity_available }}</td><td>{{ quantity(item.capacity_qty) }} {{ item.capacity_uom }} per batch</td><td>{{ item.concurrent_batch_limit }} per item · {{ quantity(item.total_concurrent_capacity) }} {{ item.capacity_uom }} total</td></tr></tbody></table>
      </section>
    </div>
  </section>
</template>

<style scoped>
.kitchen-plan {
  display: grid;
  gap: var(--spacing-m);
  min-width: 0;
  color: var(--theme-text);
}

.kitchen-plan__screen {
  display: contents;
}

.print-kitchen-pack {
  display: none;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-m);
  min-width: 0;
}

.section-heading h2,
.capacity-card h2 {
  margin: 0;
  color: var(--theme-text);
}

.section-heading p,
.capacity-card p {
  margin: var(--spacing-3xs) 0 0;
  color: var(--theme-text-muted);
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.state-message {
  padding: var(--spacing-m);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-card);
  background: var(--theme-surface-raised);
  box-shadow: var(--shadow-1);
}

.state-message--error {
  border-color: color-mix(in oklch, var(--theme-error) 52%, var(--theme-border));
  color: var(--theme-error);
}

.state-message--success {
  border-color: color-mix(in oklch, var(--theme-success) 52%, var(--theme-border));
  color: var(--theme-success);
}

.capacity-card {
  position: relative;
  display: grid;
  grid-template-columns: minmax(16rem, 0.7fr) minmax(0, 1.3fr);
  gap: var(--spacing-m);
  overflow: hidden;
  padding: var(--spacing-m);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-card);
  background: var(--theme-surface-raised);
  box-shadow: var(--shadow-1);
}

.capacity-card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 0.3rem;
  background: var(--theme-border);
  content: "";
}

.capacity-card.is-under {
  border-color: color-mix(in oklch, var(--theme-error) 38%, var(--theme-border));
  background: color-mix(in oklch, var(--theme-error) 8%, var(--theme-surface-raised));
}

.capacity-card.is-under::before {
  background: var(--theme-error);
}

.capacity-card.is-ready {
  border-color: color-mix(in oklch, var(--theme-success) 38%, var(--theme-border));
  background: color-mix(in oklch, var(--theme-success) 8%, var(--theme-surface-raised));
}

.capacity-card.is-ready::before {
  background: var(--theme-success);
}

.capacity-card__decision {
  display: grid;
  align-content: start;
  gap: var(--spacing-xs);
  padding-left: var(--spacing-2xs);
}

.capacity-card__evidence {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--spacing-xs);
}

.capacity-card__evidence div {
  display: grid;
  align-content: start;
  gap: var(--spacing-3xs);
  min-width: 0;
  padding: var(--spacing-xs);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-field);
  background: var(--theme-surface);
}

.capacity-card__evidence strong {
  font-size: 1.15rem;
  font-variant-numeric: tabular-nums;
}

.capacity-card__evidence span,
.employee-list small,
.worker-lanes small,
.equipment-grid small {
  color: var(--theme-text-muted);
  font-size: 0.78rem;
}

.plan-sections {
  display: grid;
  gap: var(--spacing-s);
  min-width: 0;
}

:deep(.plan-section) {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
  border: var(--border-width-1) solid var(--theme-border) !important;
  border-radius: var(--component-radius-card);
  background: var(--theme-surface-raised);
  box-shadow: var(--shadow-1);
}

:deep(.section-trigger) {
  width: 100%;
  min-height: 4.5rem;
  padding: var(--spacing-m) !important;
  border: 0 !important;
  color: var(--theme-text);
  text-align: left;
  text-decoration: none !important;
  text-decoration-line: none !important;
}

:deep(.section-trigger:hover) {
  background: color-mix(in oklch, var(--theme-surface) 62%, var(--theme-surface-raised));
  text-decoration: none !important;
  text-decoration-line: none !important;
}

:deep(.section-trigger:hover *) {
  text-decoration: none !important;
  text-decoration-line: none !important;
}

:deep(.section-trigger:focus-visible) {
  outline: 2px solid var(--theme-primary);
  outline-offset: -3px;
}

.section-trigger .section-heading {
  flex: 1 1 auto;
  margin: 0;
  padding: 0 var(--spacing-xs) 0 0;
  border: 0;
}

:deep(.section-content) {
  display: grid;
  gap: var(--spacing-s);
  min-width: 0;
  padding: var(--spacing-m) !important;
  border: 0 !important;
  background: var(--theme-surface);
}

.section-actions {
  display: flex;
  justify-content: flex-end;
}

.team-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(12rem, 0.5fr);
  align-items: end;
  gap: var(--spacing-xs);
}

.employee-list {
  display: grid;
  gap: var(--spacing-xs);
}

.employee-list article {
  display: grid;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-field);
  background: var(--theme-surface);
}

.employee-list__fields {
  display: grid;
  grid-template-columns: minmax(12rem, 1.2fr) minmax(9rem, 0.8fr) minmax(10rem, 1fr) auto;
  align-items: end;
  gap: var(--spacing-xs);
}

.assignment-link {
  display: grid;
  grid-template-columns: minmax(13rem, 1fr) auto minmax(14rem, 1.25fr) auto;
  align-items: center;
  gap: var(--spacing-xs);
  min-width: 0;
  padding-top: var(--spacing-xs);
  border-top: var(--border-width-1) solid var(--theme-border);
}

.assignment-link > div:first-child {
  display: grid;
  gap: var(--spacing-3xs);
}

.assignment-link span {
  font-weight: var(--font-weight-700);
}

.assignment-link small {
  color: var(--theme-text-muted);
}

.cpm-canvas {
  width: 100%;
  height: clamp(30rem, 68vh, 52rem);
  min-width: 0;
  overflow: hidden;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-card);
  background: var(--theme-canvas);
}

.cpm-canvas :deep(.system-flow) {
  width: 100%;
  height: 100%;
  min-height: 30rem;
}

.cpm-canvas :deep(.vue-flow__pane) {
  cursor: grab;
}

.cpm-canvas :deep(.vue-flow__pane:active) {
  cursor: grabbing;
}

.cpm-canvas :deep(.vue-flow__node) {
  width: 236px;
  min-width: 236px;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.cpm-canvas :deep(.vue-flow__node-cpm-junction) {
  width: 24px;
  min-width: 24px;
}

.cpm-canvas :deep(.vue-flow__node-cpm-time) {
  z-index: 0 !important;
  width: 148px;
  min-width: 148px;
  pointer-events: none;
}

.cpm-node {
  position: relative;
  display: grid;
  gap: 0.3rem;
  width: 236px;
  min-height: 132px;
  padding: var(--spacing-xs);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-field);
  background: var(--theme-surface-raised);
  color: var(--theme-text);
  box-shadow: var(--shadow-1);
}

.cpm-node.is-critical {
  border-color: var(--theme-primary);
  background: color-mix(in oklch, var(--theme-primary) 8%, var(--theme-surface-raised));
}

.cpm-junction {
  position: relative;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
}

.cpm-junction i {
  width: 0.7rem;
  height: 0.7rem;
  border: 2px solid var(--theme-surface-raised);
  border-radius: 50%;
  background: var(--theme-border);
  box-shadow: 0 0 0 1px var(--theme-border);
}

.cpm-junction.is-critical i {
  background: var(--theme-primary);
  box-shadow: 0 0 0 1px var(--theme-primary);
}

.cpm-time {
  display: grid;
  justify-items: center;
  gap: 0.15rem;
  width: 148px;
  padding: 0.35rem 0.55rem;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: 999px;
  background: var(--theme-surface-raised);
  color: var(--theme-text);
  box-shadow: var(--shadow-1);
  text-align: center;
}

.cpm-time strong {
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
}

.cpm-time span {
  color: var(--theme-text-muted);
  font-size: 0.68rem;
}

.cpm-node__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2xs);
  color: var(--theme-text-muted);
  font-size: 0.72rem;
  font-weight: 750;
  text-transform: uppercase;
}

.cpm-node > strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cpm-node > small {
  overflow: hidden;
  color: var(--theme-text-muted);
  font-size: 0.72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cpm-node > b {
  margin-top: auto;
  color: var(--theme-text);
  font-size: 0.72rem;
  font-weight: 700;
}

.cpm-canvas :deep(.vue-flow__handle) {
  width: 0.55rem;
  height: 0.55rem;
  border: 2px solid var(--theme-surface-raised);
  background: var(--theme-border);
  pointer-events: none;
}

.cpm-canvas :deep(.cpm-edge path) {
  stroke: var(--theme-border);
}

.cpm-canvas :deep(.cpm-edge--critical path) {
  stroke: var(--theme-primary);
}

.cpm-canvas :deep(.vue-flow__arrowhead polyline) {
  stroke: var(--theme-border);
  fill: var(--theme-border);
}

.cpm-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-s);
  color: var(--theme-text-muted);
  font-size: 0.8rem;
}

.cpm-legend span {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-3xs);
}

.cpm-legend i {
  width: 1rem;
  height: 1rem;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: 0.3rem;
  background: var(--theme-surface-raised);
}

.cpm-legend i.is-critical {
  border: 2px solid var(--theme-primary);
  background: color-mix(in oklch, var(--theme-primary) 10%, var(--theme-surface-raised));
}

.accessible-task-list {
  position: fixed !important;
  inset: 0 auto auto 0 !important;
  width: 1px !important;
  height: 1px !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  clip-path: inset(50%) !important;
  white-space: nowrap !important;
}

.ingredient-list {
  display: grid;
}

.ingredient-list article {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-s);
  padding: var(--spacing-xs) 0;
  border-bottom: var(--border-width-1) solid var(--theme-border);
}

.ingredient-list article:last-child {
  border-bottom: 0;
}

.ingredient-list article > div {
  display: grid;
  gap: var(--spacing-3xs);
}

.ingredient-list small,
.ingredient-list article > span {
  color: var(--theme-text-muted);
}

.ingredient-list b {
  color: var(--theme-text);
  font-variant-numeric: tabular-nums;
}

.worker-lanes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-xs);
}

.worker-lanes > article {
  overflow: hidden;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-card);
  background: var(--theme-surface);
}

.worker-lanes header {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs);
  border-bottom: var(--border-width-1) solid var(--theme-border);
  background: var(--theme-surface-raised);
}

.worker-lanes header div {
  display: grid;
  gap: var(--spacing-3xs);
}

.worker-lanes ol {
  display: grid;
  gap: var(--spacing-2xs);
  margin: 0;
  padding: var(--spacing-xs);
  list-style: none;
}

.worker-lanes li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--spacing-3xs) var(--spacing-xs);
  padding: var(--spacing-xs);
  border-left: 3px solid var(--theme-border);
  border-radius: 0 var(--component-radius-field) var(--component-radius-field) 0;
  background: var(--theme-surface-raised);
}

.worker-lanes li.is-assist {
  border-left-color: var(--theme-success);
  background: color-mix(in oklch, var(--theme-success) 6%, var(--theme-surface-raised));
}

.worker-lanes li > span,
.worker-lanes li > small {
  grid-column: 1 / -1;
}

.method-list {
  display: grid;
  gap: var(--spacing-xs);
}

.method-list details {
  overflow: hidden;
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-field);
  background: var(--theme-surface);
}

.method-list summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: var(--spacing-xs);
  min-height: 3.25rem;
  padding: var(--spacing-xs);
  cursor: pointer;
  list-style: none;
}

.method-list summary > span:first-child {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: var(--theme-secondary);
  font-weight: 800;
}

.method-list summary div {
  display: grid;
  gap: var(--spacing-3xs);
}

.method-list summary small,
.method-list summary > b {
  color: var(--theme-text-muted);
  font-size: 0.78rem;
}

.method-body {
  display: grid;
  gap: var(--spacing-s);
  padding: var(--spacing-s);
  border-top: var(--border-width-1) solid var(--theme-border);
  background: var(--theme-surface-raised);
}

.method-body > ol {
  display: grid;
  gap: var(--spacing-xs);
  margin: 0;
  padding: 0;
  list-style: none;
}

.method-body > ol > li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--spacing-xs);
}

.method-body > ol > li > span {
  display: grid;
  place-items: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 50%;
  background: var(--theme-secondary);
  font-weight: 800;
}

.method-body p {
  margin: 0;
}

.method-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2xs);
}

.method-facts span {
  padding: 0.35rem 0.55rem;
  border-radius: 999px;
  background: var(--theme-secondary);
  color: var(--theme-text-muted);
  font-size: 0.78rem;
}

.quality-check {
  padding: var(--spacing-xs);
  border-left: 3px solid var(--theme-success);
  background: color-mix(in oklch, var(--theme-success) 6%, var(--theme-surface-raised));
}

.equipment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--spacing-xs);
}

.equipment-grid article {
  display: grid;
  gap: var(--spacing-3xs);
  padding: var(--spacing-xs);
  border: var(--border-width-1) solid var(--theme-border);
  border-radius: var(--component-radius-field);
  background: var(--theme-surface);
}

.employee-availability {
  display: grid;
  gap: var(--spacing-3xs);
}

.employee-availability :deep(button) {
  justify-self: start;
  padding-inline: var(--spacing-2xs);
  font-size: var(--font-size--2);
}

@media print {
  @page {
    size: A4 portrait;
    margin: 12mm;
  }

  :global(body) {
    background: var(--theme-surface-raised) !important;
  }

  :global(.app-shell__sidebar),
  :global(.app-shell__top-area),
  :global(.app-shell__mobile-nav) {
    display: none !important;
  }

  :global(.app-shell),
  :global(.app-shell__main),
  :global(.app-shell__work),
  :global(.app-workspace) {
    display: block !important;
    width: 100% !important;
    max-width: none !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
    background: var(--theme-surface-raised) !important;
  }

  .kitchen-plan {
    display: block;
    color: var(--theme-text);
  }

  .kitchen-plan__screen {
    display: none !important;
  }

  .print-kitchen-pack {
    display: block;
  }

  .print-page {
    box-sizing: border-box;
    min-height: 265mm;
    break-after: page;
    page-break-after: always;
    color: var(--theme-text);
  }

  .print-page:last-child {
    min-height: auto;
    break-after: auto;
    page-break-after: auto;
  }

  .print-page__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8mm;
    padding-bottom: 5mm;
    border-bottom: 1px solid var(--theme-border);
    color: var(--theme-text-muted);
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
  }

  .print-page__header img {
    display: block;
    width: 36mm;
    height: auto;
  }

  .print-page__title {
    padding: 8mm 0 6mm;
  }

  .print-page__title p,
  .print-page__title h1,
  .print-page__title span {
    margin: 0;
  }

  .print-page__title p {
    color: var(--theme-primary);
    font-size: 9pt;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .print-page__title h1 {
    margin: 1.5mm 0;
    font-size: 24pt;
    line-height: 1.1;
  }

  .print-page__title span {
    color: var(--theme-text-muted);
    font-size: 10pt;
  }

  .print-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    margin-bottom: 7mm;
    border: 1px solid var(--theme-border);
    border-radius: 3mm;
  }

  .print-summary > div {
    display: grid;
    gap: 1mm;
    padding: 4mm;
    border-right: 1px solid var(--theme-border);
  }

  .print-summary > div:last-child {
    border-right: 0;
  }

  .print-summary strong {
    font-size: 15pt;
  }

  .print-summary span,
  .print-task-list p,
  .print-method-list p {
    margin: 0;
    color: var(--theme-text-muted);
    font-size: 9pt;
  }

  .print-task-list,
  .print-method-list {
    display: grid;
    gap: 3mm;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .print-task-list > li {
    display: grid;
    grid-template-columns: 25mm minmax(0, 1fr) auto;
    align-items: center;
    gap: 4mm;
    padding: 4mm;
    border: 1px solid var(--theme-border);
    border-left: 3px solid var(--theme-text-muted);
    border-radius: 2mm;
    break-inside: avoid;
  }

  .print-task-list > li.is-assist {
    border-left-color: var(--theme-success);
    background: color-mix(in oklch, var(--theme-success) 7%, var(--theme-surface-raised));
  }

  .print-task-list__time {
    display: grid;
    font-size: 11pt;
    font-weight: 800;
  }

  .print-task-list__time span {
    color: var(--theme-text-muted);
    font-size: 8pt;
    font-weight: 500;
  }

  .print-task-list > li > b {
    padding: 1.5mm 2.5mm;
    border: 1px solid var(--theme-border);
    border-radius: 99mm;
    font-size: 8pt;
  }

  .print-method-list > li {
    display: grid;
    grid-template-columns: 10mm minmax(0, 1fr);
    gap: 4mm;
    padding-bottom: 5mm;
    border-bottom: 1px solid var(--theme-border);
    break-inside: avoid;
  }

  .print-method-list > li > span {
    display: grid;
    place-items: center;
    width: 9mm;
    height: 9mm;
    border-radius: 50%;
    background: var(--theme-secondary);
    font-weight: 800;
  }

  .print-method-list h2 {
    margin: 0 0 1mm;
    font-size: 13pt;
  }

  .print-method-list ol {
    display: grid;
    gap: 1.5mm;
    margin: 3mm 0;
    padding-left: 5mm;
  }

  .print-method-list ol li {
    font-size: 9pt;
  }

  .print-method-list ol small {
    display: block;
    color: var(--theme-text-muted);
  }

  .print-page table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
  }

  .print-page th,
  .print-page td {
    padding: 3.5mm;
    border-bottom: 1px solid var(--theme-border);
    text-align: left;
    vertical-align: top;
  }

  .print-page th {
    background: var(--theme-secondary);
    font-size: 8pt;
    text-transform: uppercase;
  }
}

@media (max-width: 75rem) {
  .capacity-card {
    grid-template-columns: 1fr;
  }

  .capacity-card__evidence {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .employee-list__fields,
  .assignment-link {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .worker-lanes {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 48rem) {
  .section-heading {
    display: grid;
  }

  .button-row {
    width: 100%;
  }

  .button-row :deep(button) {
    flex: 1 1 auto;
  }

  .capacity-card__evidence {
    grid-template-columns: 1fr 1fr;
  }

  :deep(.section-trigger) {
    padding: var(--spacing-s) !important;
  }

  :deep(.section-content) {
    padding: var(--spacing-s) !important;
  }

  .team-controls,
  .employee-list__fields,
  .assignment-link,
  .equipment-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .cpm-canvas {
    height: 34rem;
  }

  .method-list summary {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .method-list summary > b {
    grid-column: 2 / -1;
  }

  .ingredient-list article {
    align-items: flex-start;
    flex-direction: column;
  }

}

@media (max-width: 30rem) {
  .capacity-card__evidence {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
