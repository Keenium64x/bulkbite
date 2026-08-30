<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
	SystemBadge,
	SystemCheckboxShadcn,
	SystemDatePicker,
	SystemFormControl,
	SystemLinkedRecordField,
	SystemOperationalButton,
	SystemSelect,
	SystemTextarea,
} from "@/desyium";
import {
	allocateFinishedFood,
	createAdHocProductionRun,
	createRunFromPlan,
	discardProductionRun,
	getFinishedFoodPosition,
	getContainerSuggestion,
	getProductionHistorySnapshot,
	getProductionInstructions,
	getRecipeExpectation,
	saveProductionEmployees,
	submitProductionRun,
	updateProductionActuals,
} from "@/resources/api";
import { syncOfflineMutation } from "@/resources/api";
import {
	clearFormDraft,
	clearSyncOutcome,
	listQueuedMutations,
	loadFormDraft,
	loadSyncOutcome,
	offlineState,
	saveFormDraft,
} from "@/native/offlineStore";
import { syncDraftMutation } from "@/native/offlineSync";
import { runtimeConfig } from "@/config/runtime";
import { nativeState } from "@/native/lifecycle";

// =============================================================================
// region PLANNED PRODUCTION STATION
// =============================================================================

const props = defineProps({
	snapshot: { type: Object, default: null },
	plan: { type: Object, default: null },
	mode: { type: String, default: "production" },
});
const emit = defineEmits(["changed", "open-worker-sheets", "open-employees", "open-history", "close"]);
const router = useRouter();
const localToday = () => {
	const value = new Date();
	return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
};
const productionDate = ref(localToday());
const actualOutput = ref(0);
const finishedContainerCount = ref(0);
const containerSuggestion = ref(null);
const containerCountManuallySet = ref(false);
const notes = ref("");
const measurements = reactive([]);
const employeeRows = reactive([]);
const teamTemplate = ref("");
const actualElapsedHours = ref(0);
const selectedRecipe = ref("");
const plannedOutput = ref(0);
const directionAction = ref("Advance Direction");
const run = ref(null);
const busy = ref(false);
const error = ref("");
const offlineNotice = ref("");
const dirtySinceSave = ref(false);
const adHocMode = ref(false);
const finishedFood = ref(null);
const instructionPlan = ref(null);
const history = ref(null);
const manuallyOverriddenUsage = new Set();
const allocation = reactive({
	allocation_type: "Current Customers",
	source_reservation: "",
	demand_period: "",
	quantity: 0,
	notes: "",
});
const queuedMutationId = ref("");
const queuedMutation = ref(null);
const draftLocked = computed(() => Boolean(queuedMutationId.value));
let hydrating = false;
let expectationTimer;
let expectationRequest = 0;
const station = computed(
	() => props.plan?.next_production || { state: "complete", row: null, run: null },
);
const selectedRow = computed(() => station.value.row);
const selectedCapacityWindow = computed(
	() =>
		props.plan?.capacity_plan?.windows?.find(
			(row) => Number(row.week_number) === Number(selectedRow.value?.week_number),
		) || null,
);
const allocationTypeOptions = [
	"Current Customers",
	"Future Customers",
	"Future Customer Fulfilment",
	"Internal Consumption",
	"Waste or Spoilage",
].map((value) => ({ label: value, value }));
const finishedPosition = computed(() => finishedFood.value?.items?.[0] || null);
const reservationOptions = computed(() =>
	(finishedFood.value?.recent_allocations || [])
		.filter(
			(row) =>
				row.allocation_type === "Future Customers" &&
				Number(row.remaining_qty || row.quantity) > 0,
		)
		.map((row) => ({
			label: `${row.demand_period || row.name} · ${quantity(row.remaining_qty || row.quantity)} ${row.uom}`,
			value: row.name,
		})),
);

watch(() => props.plan?.next_production, hydrateStation, { immediate: true, deep: true });
watch(
	[
		actualOutput,
		finishedContainerCount,
		notes,
		() =>
			measurements.map((item) => [
				item.measurement_method,
				item.actual_qty,
				item.remaining_qty,
			]),
	],
	() => {
		if (run.value && !draftLocked.value) dirtySinceSave.value = true;
	},
	{ deep: true },
);
watch(
	employeeRows,
	() => {
		if (run.value && !draftLocked.value) dirtySinceSave.value = true;
	},
	{ deep: true },
);
watch([teamTemplate, actualElapsedHours], () => {
	if (run.value && !draftLocked.value) dirtySinceSave.value = true;
});
watch(
	[
		productionDate,
		selectedRecipe,
		plannedOutput,
		actualOutput,
		finishedContainerCount,
		notes,
		measurements,
		employeeRows,
		teamTemplate,
		actualElapsedHours,
	],
	() => {
		if (
			!runtimeConfig.isNative ||
			(!selectedRow.value && !adHocMode.value) ||
			hydrating ||
			draftLocked.value
		)
			return;
		dirtySinceSave.value = true;
		persistLocalProductionDraft().catch(() => {});
	},
	{ deep: true },
);
watch(
	() => nativeState.connected,
	(connected) => {
		if (connected) window.setTimeout(() => reconcileQueuedProduction().catch(() => {}), 1500);
	},
);
watch(
	() => offlineState.lastSyncedAt,
	() => reconcileQueuedProduction().catch(() => {}),
);
watch([actualOutput, selectedRecipe], () => queueExpectationScale());
watch(actualOutput, () => queueContainerSuggestion());
watch(() => props.mode, loadHistory, { immediate: true });

async function loadHistory() {
	if (props.mode !== "history") return;
	busy.value = true;
	error.value = "";
	try {
		history.value = await getProductionHistorySnapshot(props.plan?.name || "");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function hydrateStation(value) {
	hydrating = true;
	const row = value?.row;
	run.value = value?.run || null;
	manuallyOverriddenUsage.clear();
	measurements.splice(0);
	if (!row) {
		adHocMode.value = false;
		finishedContainerCount.value = 0;
		containerCountManuallySet.value = false;
		containerSuggestion.value = null;
		instructionPlan.value = null;
		if (runtimeConfig.isNative) {
			await restoreLocalProductionDraft().catch(() => {});
			await reconcileQueuedProduction().catch(() => {});
		}
		hydrating = false;
		return;
	}
	adHocMode.value = false;
	instructionPlan.value = null;
	productionDate.value = run.value?.production_date || row.planned_date || localToday();
	actualOutput.value = roundQuantity(
		run.value?.actual_output_qty ?? row.remaining_output_qty ?? row.planned_output_qty,
	);
	finishedContainerCount.value = Number(run.value?.finished_container_count || 0);
	containerCountManuallySet.value = Boolean(run.value?.finished_container_count);
	plannedOutput.value = roundQuantity(
		run.value?.planned_output_qty ?? row.remaining_output_qty ?? row.planned_output_qty,
	);
	selectedRecipe.value = run.value?.recipe || row.recipe;
	directionAction.value = run.value?.direction_action || "Advance Direction";
	notes.value = run.value?.notes || "";
	const runIngredients = new Map(
		(run.value?.ingredients || []).map((item) => [item.item_code, item]),
	);
	row.ingredients.forEach((item) => {
		const saved = runIngredients.get(item.item_code);
		measurements.push({
			...item,
			measurement_method: saved?.measurement_method || "Used",
			actual_qty: roundQuantity(saved?.actual_qty ?? item.expected_qty),
			remaining_qty: roundQuantity(saved?.remaining_qty ?? item.available_qty),
		});
	});
	employeeRows.splice(
		0,
		employeeRows.length,
		...(run.value?.employees || []).map((row) => ({ ...row })),
	);
	teamTemplate.value =
		run.value?.team_template || props.plan?.capacity_plan?.default_team_template || "";
	actualElapsedHours.value = Number(
		run.value?.actual_elapsed_hours ||
			run.value?.scheduled_elapsed_hours ||
			selectedCapacityWindow.value?.scheduled_elapsed_hours ||
			0,
	);
	dirtySinceSave.value = false;
	if (runtimeConfig.isNative) {
		await restoreLocalProductionDraft().catch(() => {});
		await reconcileQueuedProduction().catch(() => {});
	}
	await nextTick();
	hydrating = false;
}

function startAdHocProduction() {
	if (run.value || draftLocked.value) return;
	adHocMode.value = true;
	directionAction.value = "Off Plan";
	selectedRecipe.value = "";
	plannedOutput.value = 0;
	actualOutput.value = 0;
	finishedContainerCount.value = 0;
	containerCountManuallySet.value = false;
	measurements.splice(0);
	employeeRows.splice(0);
	notes.value = "";
	dirtySinceSave.value = true;
}

function returnToDirection() {
	if (draftLocked.value) return;
	adHocMode.value = false;
	hydrateStation(props.plan?.next_production);
}

async function restoreLocalProductionDraft() {
	const draft = await loadFormDraft("production-run").catch(() => null);
	if (!draft) return;
	if (draft.plan_row_name && draft.plan_row_name !== selectedRow.value?.name) return;
	if (!draft.plan_row_name && draft.direction_action !== "Off Plan") return;
	if (draft.direction_action === "Off Plan") adHocMode.value = true;
	productionDate.value = draft.production_date || productionDate.value;
	selectedRecipe.value = draft.recipe || selectedRecipe.value;
	plannedOutput.value = roundQuantity(draft.planned_output_qty);
	actualOutput.value = draft.actual_output_qty;
	finishedContainerCount.value = Number(draft.finished_container_count || 0);
	containerCountManuallySet.value = Boolean(draft.finished_container_count);
	notes.value = draft.notes || "";
	measurements.splice(0, measurements.length, ...(draft.ingredients || []));
	employeeRows.splice(0, employeeRows.length, ...(draft.employees || []));
	teamTemplate.value = draft.team_template || "";
	actualElapsedHours.value = draft.actual_elapsed_hours || 0;
	queuedMutationId.value = draft.queuedMutationId || "";
	queuedMutation.value = draft.queuedMutation || null;
	dirtySinceSave.value = true;
	offlineNotice.value = queuedMutationId.value
		? "Production is saved on this device and waiting to sync."
		: "A production draft saved on this device was restored.";
}

function localProductionDraftSnapshot(payload = productionDraftPayload()) {
	return {
		...payload,
		queuedMutationId: queuedMutationId.value,
		queuedMutation: queuedMutation.value,
	};
}

async function persistLocalProductionDraft(payload = productionDraftPayload()) {
	if (!runtimeConfig.isNative) return;
	await saveFormDraft("production-run", localProductionDraftSnapshot(payload));
}

async function reconcileQueuedProduction(attempt = 0) {
	if (!queuedMutationId.value || !nativeState.connected) return;
	const queue = await listQueuedMutations().catch(() => []);
	if (queue.some((mutation) => mutation.clientMutationId === queuedMutationId.value)) {
		if (attempt < 8)
			window.setTimeout(() => reconcileQueuedProduction(attempt + 1).catch(() => {}), 1500);
		return;
	}
	const resolution =
		offlineState.lastResolution?.clientMutationId === queuedMutationId.value
			? offlineState.lastResolution
			: null;
	const completed = offlineState.completedResults[queuedMutationId.value];
	const persisted = await loadSyncOutcome(queuedMutationId.value).catch(() => null);
	if (resolution?.action === "server" || persisted?.action === "server") {
		run.value = null;
	} else if (resolution?.result) {
		run.value = resolution.result;
	} else if (persisted?.result) {
		run.value = persisted.result;
	} else if (completed) {
		run.value = completed;
	} else if (queuedMutation.value) {
		const response = await syncOfflineMutation(queuedMutation.value);
		run.value = response?.result || run.value;
	}
	delete offlineState.completedResults[queuedMutationId.value];
	await clearSyncOutcome(queuedMutationId.value).catch(() => {});
	queuedMutationId.value = "";
	queuedMutation.value = null;
	await clearFormDraft("production-run").catch(() => {});
	dirtySinceSave.value = false;
	offlineNotice.value =
		resolution?.action === "server" || persisted?.action === "server"
			? "The server draft was kept. Local changes were discarded."
			: "Production draft synchronized with BulkBite.";
	emit("changed");
}

function productionDraftPayload() {
	return {
		name: run.value?.name || "",
		plan_name: adHocMode.value ? "" : props.plan?.name,
		plan_row_name: adHocMode.value ? "" : selectedRow.value?.name,
		production_date: productionDate.value,
		source_location: props.plan?.location,
		target_location: "Finished Meals",
		recipe: selectedRecipe.value,
		planned_output_qty: roundQuantity(plannedOutput.value),
		actual_output_qty: roundQuantity(actualOutput.value),
		finished_container_count: Number(finishedContainerCount.value || 0),
		direction_action: directionAction.value,
		ingredients: measurements.map((item) => ({
			item_code: item.item_code,
			measurement_method: item.measurement_method,
			actual_qty: roundQuantity(item.actual_qty),
			remaining_qty: roundQuantity(item.remaining_qty),
		})),
		notes: notes.value,
		employees: employeeRows.map((row) => ({ ...row })),
		team_template: teamTemplate.value,
		actual_elapsed_hours: Number(actualElapsedHours.value || 0),
		scheduled_elapsed_hours: selectedCapacityWindow.value?.scheduled_elapsed_hours,
	};
}

async function saveRun() {
	busy.value = true;
	error.value = "";
	try {
		if (!selectedRow.value && !adHocMode.value)
			throw new Error("There is no planned meal ready.");
		if (!productionDate.value) throw new Error("Choose the production date.");
		if (Number(actualOutput.value) <= 0)
			throw new Error("Food made must be greater than zero.");
		if (
			measurements.some(
				(item) =>
					Number(
						item.measurement_method === "Remaining"
							? item.remaining_qty
							: item.actual_qty,
					) < 0,
			)
		)
			throw new Error("Ingredient measurements cannot be negative.");
		if (!selectedRecipe.value) throw new Error("Choose the meal that was made.");
		if (Number(plannedOutput.value) <= 0)
			throw new Error("Planned output must be greater than zero.");
		if (runtimeConfig.isNative) {
			const synced = await syncDraftMutation(
				syncOfflineMutation,
				"save_production_draft",
				productionDraftPayload(),
				run.value?.modified || null,
			);
			if (synced.queued) {
				queuedMutationId.value = synced.mutation.clientMutationId;
				queuedMutation.value = synced.mutation;
				await persistLocalProductionDraft();
				offlineNotice.value =
					"Production draft saved on this device. Connect before posting it to stock.";
			} else {
				run.value = synced.result;
				offlineNotice.value = "";
			}
		} else if (adHocMode.value && !run.value) {
			run.value = await createAdHocProductionRun(
				selectedRecipe.value,
				plannedOutput.value,
				productionDate.value,
				props.plan?.location || "Ingredients",
			);
			run.value = await updateProductionActuals(
				run.value.name,
				roundQuantity(actualOutput.value),
				measurements.map((item) => ({
					item_code: item.item_code,
					measurement_method: item.measurement_method,
					actual_qty: roundQuantity(item.actual_qty),
					remaining_qty: roundQuantity(item.remaining_qty),
				})),
				notes.value,
				Number(finishedContainerCount.value || 0),
			);
			run.value = await saveProductionEmployees(
				run.value.name,
				employeeRows,
				teamTemplate.value,
				actualElapsedHours.value,
				null,
			);
		} else {
			if (!run.value)
				run.value = await createRunFromPlan(
					props.plan.name,
					selectedRow.value.name,
					productionDate.value,
					props.plan.location,
					"Finished Meals",
					selectedRecipe.value,
					plannedOutput.value,
					directionAction.value,
				);
			run.value = await updateProductionActuals(
				run.value.name,
				roundQuantity(actualOutput.value),
				measurements.map((item) => ({
					item_code: item.item_code,
					measurement_method: item.measurement_method,
					actual_qty: roundQuantity(item.actual_qty),
					remaining_qty: roundQuantity(item.remaining_qty),
				})),
				notes.value,
				Number(finishedContainerCount.value || 0),
			);
			run.value = await saveProductionEmployees(
				run.value.name,
				employeeRows,
				teamTemplate.value,
				actualElapsedHours.value,
				selectedCapacityWindow.value?.scheduled_elapsed_hours,
			);
		}
		if (!queuedMutationId.value) {
			await clearFormDraft("production-run").catch(() => {});
			dirtySinceSave.value = false;
		}
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function postRun() {
	busy.value = true;
	error.value = "";
	try {
		if (runtimeConfig.isNative && !nativeState.connected)
			throw new Error("Connect to BulkBite before posting production to stock.");
		if (dirtySinceSave.value) throw new Error("Save the changed measurements before posting.");
		run.value = await submitProductionRun(run.value.name);
		await loadFinishedFood();
		emit("changed");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function loadFinishedFood() {
	if (!run.value?.docstatus || !run.value?.finished_item) return;
	finishedFood.value = await getFinishedFoodPosition(
		run.value.finished_item,
		run.value.target_location || "Finished Meals",
	);
	const internalExtra = Math.min(
		Number(selectedRow.value?.extra_output_qty || 0),
		Number(finishedPosition.value?.unallocated_qty || 0),
	);
	if (internalExtra > 0 && Number(allocation.quantity || 0) <= 0) {
		Object.assign(allocation, {
			allocation_type: "Internal Consumption",
			quantity: roundQuantity(internalExtra),
			notes: "Extra food planned for internal consumption.",
		});
	}
}

async function saveAllocation() {
	busy.value = true;
	error.value = "";
	try {
		if (runtimeConfig.isNative && !nativeState.connected)
			throw new Error("Connect to BulkBite before allocating posted finished food.");
		if (Number(allocation.quantity || 0) <= 0)
			throw new Error("Allocation quantity must be greater than zero.");
		if (
			allocation.allocation_type === "Future Customer Fulfilment" &&
			!allocation.source_reservation
		)
			throw new Error("Choose the future reservation being fulfilled.");
		finishedFood.value = await allocateFinishedFood({
			...allocation,
			posting_date: localToday(),
			finished_item: run.value.finished_item,
			source_location: run.value.target_location || "Finished Meals",
			source_production_run: run.value.name,
		});
		Object.assign(allocation, {
			allocation_type: "Current Customers",
			source_reservation: "",
			demand_period: "",
			quantity: 0,
			notes: "",
		});
		emit("changed");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function discardRun() {
	if (
		!run.value ||
		!window.confirm("Discard this production draft and reload the latest customer direction?")
	)
		return;
	busy.value = true;
	error.value = "";
	try {
		await discardProductionRun(run.value.name);
		run.value = null;
		emit("changed");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

function roundQuantity(value) {
	return Math.round(Number(value || 0) * 1000) / 1000;
}
function quantity(value) {
	return roundQuantity(value).toLocaleString("en-ZA", { maximumFractionDigits: 3 });
}
const employeeOptions = computed(() => props.snapshot?.options?.employees || []);
const attendanceOptions = ["Completed", "Absent", "Cancelled"].map((value) => ({
	label: value,
	value,
}));
const employeeByName = computed(
	() => new Map(employeeOptions.value.map((option) => [option.value, option])),
);
const planningRate = computed(() =>
	Number(props.plan?.workforce?.planning_labour_minutes_per_kg || 0),
);
const runOutput = computed(() =>
	Number(actualOutput.value || selectedRow.value?.planned_output_qty || 0),
);
const teamTemplates = computed(() => props.snapshot?.options?.team_templates || []);
const teamTemplateOptions = computed(() =>
	teamTemplates.value.map((row) => ({ label: row.template_name, value: row.name })),
);
const recipeOptions = computed(() =>
	(props.snapshot?.options?.recipes || []).map((row) => ({
		label: row.recipe_name,
		value: row.name,
	})),
);
const directionOptions = [
	{ label: "Advance when this meal target is complete", value: "Advance Direction" },
	{ label: "Repeat this planned meal next time", value: "Repeat Meal" },
	{ label: "Off-plan meal, leave direction where it is", value: "Off Plan" },
];
const actualTeam = computed(() =>
	employeeRows.filter((row) => row.completion_status === "Completed" && row.employee),
);
const labourHours = computed(() =>
	actualTeam.value.reduce(
		(sum, row) => sum + Number(row.custom_hours ? row.hours_worked : actualElapsedHours.value),
		0,
	),
);
const actualRate = computed(() =>
	runOutput.value ? (labourHours.value * 60) / runOutput.value : 0,
);
const frozenTakt = computed(() =>
	Number(run.value?.planned_takt_minutes_per_kg || planningRate.value || 0),
);
const taktVariance = computed(() =>
	actualRate.value && frozenTakt.value ? actualRate.value - frozenTakt.value : 0,
);
const paceStatus = computed(() =>
	!actualRate.value || !frozenTakt.value
		? "Not measured"
		: Math.abs(taktVariance.value) <= 0.1
			? "On pace"
			: taktVariance.value < 0
				? "Faster than takt"
				: "Slower than takt",
);
function addEmployee() {
	if (draftLocked.value) return;
	employeeRows.push({
		employee: "",
		custom_hours: false,
		hours_worked: Number(actualElapsedHours.value || 0),
		completion_status: "Completed",
		notes: "",
	});
	dirtySinceSave.value = true;
}
function removeEmployee(index) {
	if (draftLocked.value) return;
	employeeRows.splice(index, 1);
	dirtySinceSave.value = true;
}
function changeEmployee(row, employeeName) {
	if (draftLocked.value) return;
	row.employee = employeeName;
	row.hours_worked = Number(
		actualElapsedHours.value ||
			employeeByName.value.get(employeeName)?.available_hours_per_run ||
			0,
	);
	dirtySinceSave.value = true;
}
function applyTeamTemplate() {
	if (draftLocked.value) return;
	const template = teamTemplates.value.find((row) => row.name === teamTemplate.value);
	if (!template) return;
	actualElapsedHours.value = Number(
		run.value?.actual_elapsed_hours ||
			template.default_elapsed_hours ||
			selectedCapacityWindow.value?.scheduled_elapsed_hours ||
			0,
	);
	employeeRows.splice(
		0,
		employeeRows.length,
		...template.members.map((member) => ({
			employee: member.employee,
			employee_name: member.employee_name,
			employee_type: member.employee_type,
			custom_hours: Number(member.default_hours_override || 0) > 0,
			hours_worked: Number(member.default_hours_override || actualElapsedHours.value),
			completion_status: "Completed",
			notes: "",
		})),
	);
	dirtySinceSave.value = true;
}
async function changeRecipe(recipe) {
	selectedRecipe.value = recipe;
	if (run.value || !recipe) return;
	if (Number(plannedOutput.value) <= 0) {
		const configured = (props.snapshot?.options?.recipes || []).find(
			(row) => row.name === recipe,
		);
		plannedOutput.value = roundQuantity(configured?.quantity || 1);
	}
	error.value = "";
	try {
		const expectation = await getRecipeExpectation(
			recipe,
			plannedOutput.value,
			props.plan?.location || "Ingredients",
		);
		measurements.splice(
			0,
			measurements.length,
			...expectation.ingredients.map((item) => ({
				...item,
				available_qty: item.available_before_measurement,
				measurement_method: "Used",
				actual_qty: roundQuantity(item.expected_qty),
				remaining_qty: roundQuantity(item.available_before_measurement),
			})),
		);
		actualOutput.value = plannedOutput.value;
	} catch (exception) {
		error.value = exception.message;
	}
}
function queueExpectationScale() {
	if (
		hydrating ||
		draftLocked.value ||
		run.value?.docstatus ||
		!selectedRecipe.value ||
		Number(actualOutput.value) <= 0
	)
		return;
	window.clearTimeout(expectationTimer);
	expectationTimer = window.setTimeout(scaleRecipeExpectation, 280);
}
async function scaleRecipeExpectation() {
	const request = ++expectationRequest;
	try {
		const expectation = await getRecipeExpectation(
			selectedRecipe.value,
			roundQuantity(actualOutput.value),
			props.plan?.location || "Ingredients",
		);
		if (request !== expectationRequest) return;
		const current = new Map(measurements.map((item) => [item.item_code, item]));
		measurements.splice(
			0,
			measurements.length,
			...expectation.ingredients.map((item) => {
				const existing = current.get(item.item_code);
				const usedUntouched = !existing || (existing.measurement_method === "Used" && !manuallyOverriddenUsage.has(item.item_code));
				return {
					...item,
					available_qty: item.available_before_measurement,
					measurement_method: existing?.measurement_method || "Used",
					actual_qty: roundQuantity(
						usedUntouched ? item.expected_qty : existing.actual_qty,
					),
					remaining_qty: roundQuantity(
						existing?.remaining_qty ?? item.available_before_measurement,
					),
				};
			}),
		);
	} catch (exception) {
		error.value = exception.message;
	}
}
function updateActualQuantity(item, value) {
	item.actual_qty = value;
	manuallyOverriddenUsage.add(item.item_code);
}
let containerSuggestionTimer;
function queueContainerSuggestion() {
	window.clearTimeout(containerSuggestionTimer);
	if (Number(actualOutput.value) <= 0) return;
	containerSuggestionTimer = window.setTimeout(loadContainerSuggestion, 180);
}
async function loadContainerSuggestion() {
	try {
		containerSuggestion.value = await getContainerSuggestion(roundQuantity(actualOutput.value));
		if (!containerCountManuallySet.value && containerSuggestion.value?.available)
			finishedContainerCount.value = Number(containerSuggestion.value.suggested_count || 0);
	} catch {
		containerSuggestion.value = null;
	}
}
function setFinishedContainerCount(value) {
	containerCountManuallySet.value = true;
	finishedContainerCount.value = value;
}
async function openInstructions() {
	error.value = "";
	if (!selectedRecipe.value || Number(actualOutput.value) <= 0)
		return (error.value = "Choose a meal and food quantity before opening instructions.");
	busy.value = true;
	try {
		instructionPlan.value = await getProductionInstructions(
			selectedRecipe.value,
			roundQuantity(actualOutput.value),
			Math.max(actualTeam.value.length || Number(run.value?.actual_team_size || 0) || 1, 1),
		);
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}
function closeInstructions() {
	instructionPlan.value = null;
}
function openRecipeRecords(create = false) {
	router.push({
		name: create ? "AuxiliaryRecordCreate" : "BulkBiteSetupList",
		params: { doctype: "BulkBite Recipe" },
	});
}

// endregion PLANNED PRODUCTION STATION
</script>

<template>
	<section
		data-block="production-measurement"
		class="workflow-block"
		:data-offline-draft-dirty="dirtySinceSave || undefined"
	>
		<template v-if="mode === 'history'">
			<header class="workflow-header">
				<div><p class="eyebrow">Production truth</p><h1>Production history</h1><p>Compare customer need, planned output, actual food, labour, allocations, and reusable containers.</p></div>
				<div class="button-row"><SystemOperationalButton variant="outline" :loading="busy" @click="loadHistory">Refresh</SystemOperationalButton><SystemOperationalButton variant="solid" @click="emit('close')">Record production</SystemOperationalButton></div>
			</header>
			<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
			<section v-if="history" class="history-summary" :class="history.summary.needs_another_run ? 'is-behind' : 'is-ready'">
				<div><p class="eyebrow">Current cycle</p><h2>{{ history.summary.needs_another_run ? "More production is needed" : "Production is on pace" }}</h2><p>{{ history.summary.needs_another_run ? `${quantity(history.summary.remaining_customer_qty)} kg still has to be made for customers.` : "Posted output covers the current customer requirement." }}</p></div>
				<div class="metric-board"><div><strong>{{ quantity(history.summary.customer_required_qty) }} kg</strong><span>customers need</span></div><div><strong>{{ quantity(history.summary.planned_qty) }} kg</strong><span>theory planned</span></div><div><strong>{{ quantity(history.summary.actual_qty) }} kg</strong><span>actually made</span></div><div><strong>{{ quantity(Math.abs(history.summary.output_difference_qty)) }} kg</strong><span>{{ history.summary.output_difference_qty < 0 ? "missing" : "above need" }}</span></div></div>
			</section>
			<section v-if="history" class="data-section">
				<div class="section-heading"><div><p class="eyebrow">Finished food allocation</p><h2>Where the food went</h2></div></div>
				<div class="metric-board"><div v-for="(value, label) in history.summary.allocations" :key="label"><strong>{{ quantity(value) }} kg</strong><span>{{ label }}</span></div></div>
			</section>
			<section v-if="history" class="data-section">
				<div class="section-heading"><div><p class="eyebrow">Run evidence</p><h2>Theory against actual</h2></div><SystemBadge>{{ history.runs.length }} posted runs</SystemBadge></div>
				<div class="history-run-list"><article v-for="item in history.runs" :key="item.name"><div class="history-run-heading"><div><strong>{{ item.finished_item }}</strong><small>{{ item.production_date }} · {{ item.name }}</small></div><SystemBadge :theme="item.customer_coverage_status === 'Short' ? 'red' : 'green'">{{ item.customer_coverage_status }}</SystemBadge></div><div class="metric-board"><div><strong>{{ quantity(item.planned_output_qty) }} kg</strong><span>planned</span></div><div><strong>{{ quantity(item.actual_output_qty) }} kg</strong><span>made</span></div><div><strong>{{ quantity(item.theory_customer_qty) }} kg</strong><span>customer theory</span></div><div><strong>{{ quantity(item.unallocated_output_qty) }} kg</strong><span>unallocated</span></div><div><strong>{{ item.finished_container_count }}</strong><span>containers filled</span></div><div><strong>{{ quantity(item.actual_labour_minutes_per_kg) }} min/kg</strong><span>actual labour rate</span></div></div><div v-if="item.allocations.length" class="allocation-strip"><span v-for="allocationRow in item.allocations" :key="allocationRow.name">{{ allocationRow.allocation_type }}: {{ quantity(allocationRow.quantity) }} {{ allocationRow.uom }}</span></div></article></div>
			</section>
			<section v-if="history" class="data-section"><div class="section-heading"><div><p class="eyebrow">Reusable containers</p><h2>Container position</h2></div></div><div class="metric-board"><div><strong>{{ history.containers.states.Clean || 0 }}</strong><span>clean</span></div><div><strong>{{ history.containers.states.Filled || 0 }}</strong><span>filled food</span></div><div><strong>{{ history.containers.states['With Customer'] || 0 }}</strong><span>with customers</span></div><div><strong>{{ history.containers.overdue || 0 }}</strong><span>overdue</span></div><div><strong>{{ history.containers.states.Maintenance || 0 }}</strong><span>maintenance</span></div></div></section>
		</template>
		<template v-else>
		<header class="workflow-header">
			<div>
				<p class="eyebrow">Production</p>
				<h1>{{ adHocMode ? "Record an off-plan meal" : "Record the next meal" }}</h1>
				<p>
					{{
						adHocMode
							? "Choose any approved recipe and record what was actually made. This does not move the current meal direction."
							: "The current direction chooses the next meal. Saving keeps a draft; posting moves stock once."
					}}
				</p>
			</div>
			<div class="button-row">
				<SystemOperationalButton
					v-if="!run"
					variant="outline"
					:disabled="draftLocked"
					@click="adHocMode ? returnToDirection() : startAdHocProduction()"
					>{{
						adHocMode ? "Return to direction" : "Make something else"
					}}</SystemOperationalButton
				><SystemOperationalButton variant="outline" @click="emit('open-employees')"
					>Manage employees</SystemOperationalButton
				><SystemOperationalButton variant="outline" @click="emit('open-worker-sheets')"
					>Worker sheets</SystemOperationalButton
				><SystemOperationalButton variant="outline" @click="emit('open-history')"
					>Production history</SystemOperationalButton
				><SystemBadge v-if="selectedRow && !adHocMode"
					>Cycle {{ station.cycle_number || 1 }} · Meal
					{{ selectedRow.week_number }}</SystemBadge
				>
			</div>
		</header>
		<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
		<div v-if="offlineNotice" class="state-message" role="status">{{ offlineNotice }}</div>
		<div v-if="!plan && !adHocMode" class="state-message">
			<p>Set the current meal direction, or record an off-plan production run.</p>
			<SystemOperationalButton variant="outline" @click="startAdHocProduction"
				>Make something else</SystemOperationalButton
			>
		</div>
		<template v-else-if="selectedRow || adHocMode">
			<section v-if="instructionPlan" class="data-section instruction-workspace">
				<div class="section-heading">
					<div>
						<p class="eyebrow">Kitchen instructions</p>
						<h2>{{ instructionPlan.recipe_name }}</h2>
						<p>
							Scaled for {{ quantity(instructionPlan.output_qty) }}
							{{ instructionPlan.output_uom }} with {{ instructionPlan.team_size }}
							{{ instructionPlan.team_size === 1 ? "worker" : "workers" }}.
							Ingredient quantities come from the saved recipe.
						</p>
					</div>
					<SystemOperationalButton variant="outline" @click="closeInstructions"
						>Return to production</SystemOperationalButton
					>
				</div>
				<div
					v-if="instructionPlan.warnings?.length"
					class="state-message state-message--error"
				>
					<p v-for="warning in instructionPlan.warnings" :key="warning">{{ warning }}</p>
				</div>
				<div class="metric-board">
					<div>
						<strong>{{ instructionPlan.steps.length }}</strong
						><span>reviewed steps</span>
					</div>
					<div>
						<strong>{{ instructionPlan.worker_lanes.length }}</strong
						><span>worker lanes</span>
					</div>
					<div>
						<strong
							>{{ quantity(instructionPlan.estimated_elapsed_minutes) }} min</strong
						><span>estimated elapsed time</span>
					</div>
					<div>
						<strong>{{ instructionPlan.equipment.length }}</strong
						><span>equipment types</span>
					</div>
				</div>
				<details class="instruction-group" open>
					<summary>
						Scaled ingredients <span>{{ instructionPlan.ingredients.length }}</span>
					</summary>
					<div class="instruction-ingredient-grid">
						<article v-for="item in instructionPlan.ingredients" :key="item.item_code">
							<div class="ingredient-quantity"><strong>{{ quantity(item.quantity) }} {{ item.uom }}</strong><span>weigh raw</span></div>
							<div><strong>{{ item.item_name }}</strong><p v-if="item.piece_count_estimate">About {{ item.piece_count_estimate }} {{ item.piece_count_label }}</p><p v-else-if="item.prepared_yield_factor !== 1">Expected yield: {{ quantity(item.prepared_quantity) }} {{ item.uom }} prepared</p><small v-if="item.preparation_yield_note">{{ item.preparation_yield_note }}</small></div>
						</article>
					</div>
				</details>
				<details class="instruction-group" open>
					<summary>
						Concurrent worker lanes
						<span>{{ instructionPlan.worker_lanes.length }}</span>
					</summary>
					<div class="worker-lane-grid">
						<article v-for="lane in instructionPlan.worker_lanes" :key="lane.lane">
							<strong>Worker {{ lane.lane }}</strong>
							<ol>
								<li
									v-for="step in lane.steps"
									:key="`${lane.lane}-${step.step_number}`"
								>
									<span
										>{{ step.start_minute }} to {{ step.end_minute }} min</span
									>{{ step.step_name }}
								</li>
							</ol>
						</article>
					</div>
				</details>
				<details class="instruction-group" open>
					<summary>
						Step-by-step method <span>{{ instructionPlan.steps.length }}</span>
					</summary>
					<div class="instruction-step-list">
						<article v-for="step in instructionPlan.steps" :key="step.step_number">
							<SystemBadge>STEP {{ step.step_number }}</SystemBadge>
							<div>
								<strong>{{ step.step_name }}</strong>
								<p>{{ step.instruction }}</p>
								<small v-if="step.ingredients.length"
									>Use
									{{
										step.ingredients
											.map(
												(item) =>
															`${quantity(item.quantity)} ${item.uom} raw ${item.item_name}${item.piece_count_estimate ? `, about ${item.piece_count_estimate} ${item.piece_count_label}` : ""}`,
											)
											.join(", ")
									}}.</small
								><small
									>{{ step.estimated_minutes }} min · {{ step.minimum_workers }}
									{{ step.minimum_workers === 1 ? "worker" : "workers" }} ·
									{{ step.batch_count }}
									{{ step.batch_count === 1 ? "batch" : "batches"
									}}<span v-if="step.equipment_type">
										· {{ step.equipment_type }}</span
									></small
								>
								<p v-if="step.quality_checkpoint" class="quality-check">
									<strong>Check:</strong> {{ step.quality_checkpoint }}
								</p>
							</div>
						</article>
					</div>
				</details>
				<details v-if="instructionPlan.equipment.length" class="instruction-group">
					<summary>
						Equipment capacity <span>{{ instructionPlan.equipment.length }}</span>
					</summary>
					<div class="instruction-ingredient-grid">
						<article v-for="item in instructionPlan.equipment" :key="item.name">
							<strong>{{ item.equipment_type_name }}</strong
							><span
								>{{ quantity(item.total_concurrent_capacity) }}
								{{ item.capacity_uom }} concurrent</span
							>
						</article>
					</div>
				</details>
			</section>
			<template v-else>
				<section class="form-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">
								{{ adHocMode ? "Custom production" : "Current direction" }}
							</p>
							<h2>
								{{
									adHocMode
										? "Choose what to make"
										: selectedRow.finished_item_name
								}}
							</h2>
							<p>
								{{
									adHocMode
										? "The target creates recipe theory for this run only."
										: `${plan.plan_title}, meal ${selectedRow.week_number}. Choose whether this run completes the planned meal, repeats it next time, or records something off plan.`
								}}
							</p>
						</div>
						<SystemBadge v-if="!adHocMode"
							>{{ quantity(selectedRow.planned_output_qty) }} kg
							expected</SystemBadge
						><SystemBadge v-else>OFF PLAN</SystemBadge>
					</div>
					<div class="production-direction-grid">
						<SystemLinkedRecordField
							:model-value="selectedRecipe"
							label="Meal actually made"
							:options="recipeOptions"
							placeholder="Choose a recipe"
							create-label="Create recipe"
							manage-label="Manage recipes"
							:disabled="Boolean(run) || draftLocked"
							@update:model-value="changeRecipe"
							@create="openRecipeRecords(true)"
							@manage="openRecipeRecords(false)"
						/><SystemSelect
							v-if="!adHocMode"
							v-model="directionAction"
							label="After this run"
							:options="directionOptions"
							:disabled="Boolean(run) || draftLocked"
						/>
						<div v-else class="calculated-hours">
							<span>After this run</span
							><strong>Leave meal direction unchanged</strong>
						</div>
						<SystemFormControl
							v-model="plannedOutput"
							type="number"
							label="Target for this run (kg)"
							min="0.1"
							step="0.1"
							:disabled="Boolean(run) || draftLocked"
						/>
					</div>
					<div class="direction-note">
						<strong v-if="directionAction === 'Repeat Meal'"
							>This planned meal will stay next after posting.</strong
						><strong v-else-if="directionAction === 'Off Plan'"
							>This run will post actual stock and labour but will not move the meal
							direction.</strong
						><strong v-else-if="selectedRow.remaining_output_qty"
							>{{ quantity(selectedRow.completed_output_qty) }} kg has already been
							made. This run targets the remaining
							{{ quantity(selectedRow.remaining_output_qty) }} kg.</strong
						><strong v-else
							>The direction advances only after posted production covers this meal
							target. A smaller run leaves the remaining quantity for the next
							run.</strong
						>
					</div>
					<div class="button-row instruction-actions">
						<SystemOperationalButton
							variant="outline"
							:loading="busy"
							@click="openInstructions"
							>Open scaled instructions</SystemOperationalButton
						><SystemOperationalButton variant="ghost" @click="openRecipeRecords(false)"
							>Edit recipe method</SystemOperationalButton
						>
					</div>
					<div class="production-topline">
						<div class="field-grid">
							<SystemDatePicker
								v-model="productionDate"
								label="Production date"
								format="YYYY-MM-DD"
								:disabled="Boolean(run) || draftLocked"
								:clearable="false"
							/><SystemFormControl
								v-model="actualOutput"
								type="number"
								label="Food made (kg)"
								min="0"
								step="0.1"
								size="lg"
								:disabled="draftLocked"
							/><SystemFormControl
								:model-value="finishedContainerCount"
								type="number"
								label="Finished containers"
								min="0"
								step="1"
								size="lg"
								:disabled="draftLocked"
								@update:model-value="setFinishedContainerCount"
							/>
						</div>
						<div class="button-row">
							<SystemOperationalButton
								v-if="!run || !run.docstatus"
								variant="outline"
								size="lg"
								:loading="busy"
								:disabled="draftLocked"
								@click="saveRun"
								>{{
									draftLocked ? "Waiting to sync" : "Save draft"
								}}</SystemOperationalButton
							><SystemOperationalButton
								v-if="run && !run.docstatus"
								variant="ghost"
								size="lg"
								:disabled="busy || draftLocked"
								@click="discardRun"
								>Discard draft</SystemOperationalButton
							><SystemOperationalButton
								v-if="run && !run.docstatus"
								variant="solid"
								size="lg"
								:loading="busy"
								:disabled="dirtySinceSave || draftLocked"
								@click="postRun"
								>Post production</SystemOperationalButton
							>
						</div>
					</div>
					<div v-if="containerSuggestion?.available" class="container-suggestion">
						<div><span>Suggested packing</span><strong>{{ containerSuggestion.suggested_count }} × {{ quantity(containerSuggestion.capacity_qty) }} {{ containerSuggestion.capacity_uom }}</strong><small>{{ containerSuggestion.container_type_name }}. The count rounds up so all recorded food has space.</small></div>
						<div><span>Your entry</span><strong>{{ finishedContainerCount || 0 }} containers</strong><small v-if="finishedContainerCount > 0">{{ quantity(actualOutput / finishedContainerCount) }} kg average fill</small></div>
					</div>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Measurements</p>
							<h2>Enter what happened</h2>
							<p>Use quantity used, or enter what remained after the cook.</p>
						</div>
					</div>
					<div class="measurement-list">
						<article
							v-for="item in measurements"
							:key="item.item_code"
							class="measurement-row"
						>
							<div>
								<strong>{{ item.item_name }}</strong
								><small
									>Expected {{ quantity(item.expected_qty) }} {{ item.uom }} ·
									Available {{ quantity(item.available_qty) }}
									{{ item.uom }}</small
								>
							</div>
							<label class="field-shell"
								><span>Enter</span
								><SystemSelect
									v-model="item.measurement_method"
									:options="[
										{ label: 'Quantity used', value: 'Used' },
										{ label: 'Quantity left', value: 'Remaining' },
									]"
									size="lg"
									:disabled="draftLocked"
							/></label>
							<SystemFormControl
								v-if="item.measurement_method === 'Used'"
								:model-value="item.actual_qty"
								type="number"
								label="Used"
								min="0"
								step="0.1"
								size="lg"
								:disabled="draftLocked"
								@update:model-value="updateActualQuantity(item, $event)"
							/>
							<SystemFormControl
								v-else
								v-model="item.remaining_qty"
								type="number"
								label="Left"
								min="0"
								step="0.1"
								size="lg"
								:disabled="draftLocked"
							/>
							<span class="unit-label">{{ item.uom }}</span>
						</article>
					</div>
					<SystemTextarea
						v-model="notes"
						placeholder="Production notes or reason for a large difference"
						:rows="3"
						:disabled="draftLocked"
					/>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Actual team</p>
							<h2>Who worked on this production run?</h2>
							<p>
								Choose the team that was present and enter the total elapsed time
								once. Custom hours are only needed when one person worked a
								different time.
							</p>
						</div>
						<div class="button-row">
							<SystemOperationalButton
								variant="ghost"
								@click="emit('open-employees')"
								>Manage employees</SystemOperationalButton
							><SystemOperationalButton
								variant="outline"
								:disabled="Boolean(run?.docstatus) || draftLocked"
								@click="addEmployee"
								>Add employee</SystemOperationalButton
							>
						</div>
					</div>
					<div class="team-template-row">
						<SystemSelect
							v-model="teamTemplate"
							label="Team template"
							:options="teamTemplateOptions"
							placeholder="Choose a saved team"
							:disabled="Boolean(run?.docstatus) || draftLocked"
						/><SystemOperationalButton
							variant="outline"
							:disabled="Boolean(run?.docstatus) || draftLocked || !teamTemplate"
							@click="applyTeamTemplate"
							>Apply team template</SystemOperationalButton
						><SystemFormControl
							v-model="actualElapsedHours"
							label="Actual elapsed time (hours)"
							type="number"
							step="0.1"
							min="0"
							:disabled="Boolean(run?.docstatus) || draftLocked"
						/>
					</div>
					<div
						class="run-performance-card"
						:class="paceStatus === 'Slower than takt' ? 'is-under' : 'is-ready'"
					>
						<div>
							<span>Actual production pace</span><strong>{{ paceStatus }}</strong>
							<p>
								{{ quantity(actualTeam.length) }} people worked
								{{ quantity(actualElapsedHours) }} elapsed hours, creating
								{{ quantity(labourHours) }} labour-hours.
							</p>
						</div>
						<div>
							<SystemBadge
								:theme="paceStatus === 'Slower than takt' ? 'red' : 'green'"
								>{{ quantity(actualRate) }} min/kg actual</SystemBadge
							><small>{{ quantity(frozenTakt) }} min/kg planned takt</small>
						</div>
					</div>
					<div class="employee-assignment-list">
						<article v-for="(row, index) in employeeRows" :key="index">
							<SystemSelect
								:model-value="row.employee"
								label="Employee"
								:options="employeeOptions"
								:disabled="Boolean(run?.docstatus) || draftLocked"
								@update:model-value="changeEmployee(row, $event)"
							/><SystemSelect
								v-model="row.completion_status"
								label="Work status"
								:options="attendanceOptions"
								:disabled="Boolean(run?.docstatus) || draftLocked"
							/><SystemCheckboxShadcn
								v-model="row.custom_hours"
								label="Custom hours"
								:disabled="Boolean(run?.docstatus) || draftLocked"
							/><SystemFormControl
								v-if="row.custom_hours"
								v-model="row.hours_worked"
								label="Hours worked"
								type="number"
								step="0.1"
								min="0"
								:disabled="Boolean(run?.docstatus) || draftLocked"
							/>
							<div v-else class="calculated-hours">
								<span>Hours worked</span
								><strong
									>{{
										row.completion_status === "Completed"
											? quantity(actualElapsedHours)
											: "0"
									}}
									h</strong
								>
							</div>
							<SystemFormControl
								v-model="row.notes"
								label="Notes"
								:disabled="Boolean(run?.docstatus) || draftLocked"
							/><SystemOperationalButton
								v-if="!run?.docstatus"
								variant="ghost"
								:disabled="draftLocked"
								@click="removeEmployee(index)"
								>Remove</SystemOperationalButton
							><small v-if="row.payment_basis"
								>{{ row.payment_basis }} · R
								{{ Number(row.payment_rate || 0).toFixed(2) }} · R
								{{ Number(row.payable_amount || 0).toFixed(2) }} payable</small
							>
						</article>
						<p v-if="!employeeRows.length" class="state-message">
							No team members captured yet. Apply a team template or add the people
							who worked.
						</p>
					</div>
				</section>
				<footer class="posting-bar">
					<div>
						<SystemBadge>{{
							run
								? run.docstatus
									? "STOCK UPDATED"
									: "READY TO POST"
								: "MEASUREMENTS NOT SAVED"
						}}</SystemBadge>
						<p>
							{{
								run
									? run.docstatus
										? "Ingredient use and finished meals are now reflected in stock."
										: "Review the saved measurements, then post the production run."
									: "Save the measurements first. Stock will not change yet."
							}}
						</p>
					</div>
				</footer>
				<section v-if="run?.docstatus" class="data-section finished-allocation">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Finished food</p>
							<h2>Decide where the food goes</h2>
							<p>
								The posted run records everything made. Allocate it separately to
								current customers, future customers, internal use, or waste.
							</p>
						</div>
						<SystemOperationalButton variant="outline" @click="loadFinishedFood"
							>Refresh availability</SystemOperationalButton
						>
					</div>
					<div v-if="finishedPosition" class="metric-board">
						<div>
							<strong>{{ quantity(finishedPosition.physical_qty) }} kg</strong
							><span>physical stock</span>
						</div>
						<div>
							<strong>{{ run.finished_container_count || 0 }}</strong
							><span>finished containers</span>
						</div>
						<div>
							<strong>{{ quantity(run.average_container_qty) }} kg</strong
							><span>average per container</span>
						</div>
						<div>
							<strong>{{ quantity(finishedPosition.reserved_qty) }} kg</strong
							><span>reserved for future</span>
						</div>
						<div>
							<strong>{{ quantity(finishedPosition.unallocated_qty) }} kg</strong
							><span>available to allocate</span>
						</div>
					</div>
					<div class="allocation-grid">
						<SystemSelect
							v-model="allocation.allocation_type"
							label="Purpose"
							:options="allocationTypeOptions"
						/><SystemSelect
							v-if="allocation.allocation_type === 'Future Customer Fulfilment'"
							v-model="allocation.source_reservation"
							label="Future reservation"
							:options="reservationOptions"
							placeholder="Choose reservation"
						/><SystemFormControl
							v-else-if="allocation.allocation_type === 'Future Customers'"
							v-model="allocation.demand_period"
							label="Future week or reference"
						/><SystemFormControl
							v-model="allocation.quantity"
							type="number"
							min="0.1"
							step="0.1"
							label="Quantity (kg)"
						/><SystemFormControl
							v-model="allocation.notes"
							label="Notes"
						/><SystemOperationalButton
							variant="solid"
							:loading="busy"
							@click="saveAllocation"
							>Allocate food</SystemOperationalButton
						>
					</div>
					<div
						v-if="finishedFood?.recent_allocations?.length"
						class="allocation-history"
					>
						<article v-for="row in finishedFood.recent_allocations" :key="row.name">
							<div>
								<strong>{{ row.allocation_type }}</strong
								><small
									>{{ row.posting_date }} ·
									{{
										row.demand_period ||
										row.source_reservation ||
										row.source_production_run ||
										row.name
									}}</small
								>
							</div>
							<SystemBadge :theme="row.status === 'Issued' ? 'green' : undefined"
								>{{ quantity(row.quantity) }} {{ row.uom }} ·
								{{ row.status }}</SystemBadge
							>
						</article>
					</div>
				</section>
			</template>
		</template>
		</template>
	</section>
</template>

<style scoped>
.history-summary,
.history-run-list > article {
	display: grid;
	gap: var(--spacing-s);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface-raised);
}
.history-summary {
	grid-template-columns: minmax(16rem, 0.65fr) minmax(0, 1.35fr);
}
.history-summary.is-behind {
	border-color: color-mix(in oklch, var(--theme-error) 48%, var(--theme-border));
	background: color-mix(in oklch, var(--theme-error) 7%, var(--theme-surface-raised));
}
.history-summary.is-ready {
	border-color: color-mix(in oklch, var(--theme-success) 38%, var(--theme-border));
}
.history-summary h2,
.history-summary p {
	margin: var(--spacing-3xs) 0 0;
}
.history-summary p:not(.eyebrow) {
	color: var(--theme-text-muted);
}
.history-run-list {
	display: grid;
	gap: var(--spacing-xs);
}
.history-run-heading {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: var(--spacing-s);
}
.history-run-heading small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.allocation-strip {
	display: flex;
	flex-wrap: wrap;
	gap: var(--spacing-2xs);
}
.allocation-strip span {
	padding: var(--spacing-3xs) var(--spacing-xs);
	border-radius: 999px;
	background: var(--theme-secondary);
	color: var(--theme-text-muted);
	font-size: var(--font-size--2);
}
.production-direction-grid {
	display: grid;
	grid-template-columns: minmax(16rem, 1fr) minmax(16rem, 1fr) minmax(10rem, 0.5fr);
	align-items: end;
	gap: var(--spacing-s);
	margin-bottom: var(--spacing-s);
}
@media (max-width: 54rem) {
	.history-summary {
		grid-template-columns: 1fr;
	}
}
.direction-note {
	margin-bottom: var(--spacing-s);
	padding: var(--spacing-xs) var(--spacing-s);
	border-radius: var(--component-radius-field);
	background: var(--theme-secondary);
	color: var(--theme-text-muted);
}
.instruction-actions {
	margin-bottom: var(--spacing-s);
}
.instruction-workspace {
	display: grid;
	gap: var(--spacing-s);
}
.instruction-group {
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface-raised);
	overflow: hidden;
}
.instruction-group > summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	cursor: pointer;
	font-weight: var(--font-weight-semibold);
}
.instruction-group > summary span {
	color: var(--theme-text-muted);
	font-size: var(--font-size--2);
}
.instruction-ingredient-grid,
.worker-lane-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--spacing-xs);
	padding: 0 var(--spacing-s) var(--spacing-s);
}
.instruction-ingredient-grid article,
.worker-lane-grid article {
	display: grid;
	gap: var(--spacing-3xs);
	padding: var(--spacing-s);
	border-radius: var(--component-radius-field);
	background: var(--theme-secondary);
}
.instruction-ingredient-grid article {
	grid-template-columns: minmax(7rem, 0.45fr) minmax(0, 1fr);
	align-items: start;
	gap: var(--spacing-xs);
}
.instruction-ingredient-grid article p,
.instruction-ingredient-grid article small {
	margin: var(--spacing-3xs) 0 0;
	color: var(--theme-text-muted);
}
.ingredient-quantity {
	display: grid;
	gap: var(--spacing-3xs);
	padding: var(--spacing-xs);
	border-radius: var(--component-radius-control);
	background: var(--theme-surface-raised);
}
.ingredient-quantity strong {
	font-size: var(--font-size-1);
	font-variant-numeric: tabular-nums;
}
.ingredient-quantity span {
	font-size: var(--font-size--2);
	text-transform: uppercase;
	letter-spacing: 0.06em;
}
.instruction-ingredient-grid span,
.worker-lane-grid span,
.instruction-step-list small {
	color: var(--theme-text-muted);
}
.worker-lane-grid ol {
	display: grid;
	gap: var(--spacing-xs);
	margin: var(--spacing-xs) 0 0;
	padding-left: var(--spacing-m);
}
.worker-lane-grid li {
	padding-left: var(--spacing-2xs);
}
.worker-lane-grid li span {
	display: block;
	font-size: var(--font-size--2);
}
.instruction-step-list {
	display: grid;
	gap: var(--spacing-xs);
	padding: 0 var(--spacing-s) var(--spacing-s);
}
.instruction-step-list article {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr);
	align-items: start;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	border-radius: var(--component-radius-field);
	background: var(--theme-secondary);
}
.instruction-step-list p {
	margin: var(--spacing-3xs) 0;
}
.instruction-step-list small {
	display: block;
	margin-top: var(--spacing-3xs);
}
.quality-check {
	padding: var(--spacing-xs);
	border-radius: var(--component-radius-field);
	background: var(--theme-surface-raised);
}
.container-suggestion {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--spacing-xs);
	margin-bottom: var(--spacing-s);
	padding: var(--spacing-s);
	border: var(--border-width-1) solid color-mix(in oklch, var(--theme-success) 34%, var(--theme-border));
	border-radius: var(--component-radius-card);
	background: color-mix(in oklch, var(--theme-success) 6%, var(--theme-surface-raised));
}
.container-suggestion div {
	display: grid;
	gap: var(--spacing-3xs);
}
.container-suggestion span,
.container-suggestion small {
	color: var(--theme-text-muted);
}
.allocation-grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
	align-items: end;
	gap: var(--spacing-xs);
}
.allocation-history {
	display: grid;
	margin-top: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	overflow: hidden;
}
.allocation-history article {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	border-bottom: var(--border-width-1) solid var(--theme-border);
	background: var(--theme-surface-raised);
}
.allocation-history article:last-child {
	border-bottom: 0;
}
.allocation-history small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.team-template-row {
	display: grid;
	grid-template-columns: minmax(14rem, 1fr) auto minmax(12rem, 0.7fr);
	align-items: end;
	gap: var(--spacing-s);
	margin-bottom: var(--spacing-s);
}
.run-performance-card {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	margin-bottom: var(--spacing-s);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
}
.run-performance-card.is-under {
	border-color: color-mix(in oklch, var(--theme-error) 52%, var(--theme-border));
	background: color-mix(in oklch, var(--theme-error) 10%, var(--theme-surface-raised));
}
.run-performance-card.is-ready {
	border-color: color-mix(in oklch, var(--theme-success) 52%, var(--theme-border));
	background: color-mix(in oklch, var(--theme-success) 10%, var(--theme-surface-raised));
}
.run-performance-card span,
.run-performance-card p,
.run-performance-card small {
	color: var(--theme-text-muted);
}
.run-performance-card strong {
	display: block;
	margin-top: var(--spacing-3xs);
	font-size: var(--font-size-2);
}
.run-performance-card p {
	margin: var(--spacing-3xs) 0 0;
}
.run-performance-card > div:last-child {
	display: grid;
	justify-items: end;
	gap: var(--spacing-3xs);
}
.calculated-hours {
	display: grid;
	align-content: center;
	gap: var(--spacing-3xs);
	min-height: 2.75rem;
}
.calculated-hours span {
	color: var(--theme-text-muted);
	font-size: var(--font-size--2);
}
.production-topline {
	display: flex;
	align-items: end;
	justify-content: space-between;
	gap: var(--spacing-s);
	flex-wrap: wrap;
}
.production-topline > .field-grid {
	flex: 1 1 34rem;
}
.production-topline > .button-row {
	justify-content: flex-end;
}
.run-capacity-card {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	margin-bottom: var(--spacing-s);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
}
.run-capacity-card.is-under {
	border-color: color-mix(in oklch, var(--theme-error) 52%, var(--theme-border));
	background: color-mix(in oklch, var(--theme-error) 10%, var(--theme-surface-raised));
}
.run-capacity-card.is-ready {
	border-color: color-mix(in oklch, var(--theme-success) 52%, var(--theme-border));
	background: color-mix(in oklch, var(--theme-success) 10%, var(--theme-surface-raised));
}
.run-capacity-card span,
.run-capacity-card p,
.run-capacity-card small {
	color: var(--theme-text-muted);
}
.run-capacity-card strong {
	display: block;
	margin-top: var(--spacing-3xs);
	font-size: var(--font-size-2);
}
.run-capacity-card p {
	margin: var(--spacing-3xs) 0 0;
}
.run-capacity-card > div:last-child {
	display: grid;
	justify-items: end;
	gap: var(--spacing-3xs);
}
.employee-assignment-list {
	display: grid;
	gap: var(--spacing-xs);
}
.employee-assignment-list article {
	display: grid;
	grid-template-columns: 1fr 0.65fr 0.75fr 0.75fr 1fr auto;
	align-items: end;
	gap: var(--spacing-xs);
	padding: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-secondary);
}
.employee-assignment-list article > small {
	grid-column: 1/-1;
	color: var(--theme-text-muted);
}
@media (max-width: 70rem) {
	.employee-assignment-list article {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}
	.employee-assignment-list article > *:last-of-type {
		justify-self: start;
	}
}
@media (max-width: 52rem) {
	.production-topline,
	.production-topline > .field-grid {
		display: grid;
		grid-template-columns: 1fr;
		width: 100%;
	}
	.production-topline > .button-row {
		justify-content: stretch;
	}
	.production-topline > .button-row > * {
		flex: 1 1 auto;
	}
	.employee-assignment-list article {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}
@media (max-width: 44rem) {
	.employee-assignment-list article {
		grid-template-columns: 1fr;
	}
	.run-capacity-card {
		align-items: flex-start;
		flex-direction: column;
	}
	.run-capacity-card > div:last-child {
		justify-items: start;
	}
}
@media (max-width: 70rem) {
	.production-direction-grid {
		grid-template-columns: 1fr 1fr;
	}
	.production-direction-grid > *:last-child {
		grid-column: 1/-1;
	}
	.allocation-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
	.instruction-ingredient-grid,
	.worker-lane-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}
@media (max-width: 52rem) {
	.team-template-row {
		grid-template-columns: 1fr 1fr;
	}
	.team-template-row > *:first-child {
		grid-column: 1/-1;
	}
}
@media (max-width: 44rem) {
	.production-direction-grid,
	.team-template-row,
	.allocation-grid,
	.instruction-ingredient-grid,
	.worker-lane-grid {
		grid-template-columns: 1fr;
	}
	.production-direction-grid > *:last-child,
	.team-template-row > *:first-child {
		grid-column: auto;
	}
	.run-performance-card,
	.allocation-history article {
		align-items: flex-start;
		flex-direction: column;
	}
	.run-performance-card > div:last-child {
		justify-items: start;
	}
	.instruction-step-list article {
		grid-template-columns: 1fr;
	}
	.instruction-ingredient-grid article,
	.container-suggestion {
		grid-template-columns: 1fr;
	}
}
</style>
