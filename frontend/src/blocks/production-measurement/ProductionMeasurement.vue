<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
	SystemAccordion,
	SystemAccordionContent,
	SystemAccordionItem,
	SystemAccordionTrigger,
	SystemBadge,
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
	getFinishedFoodPosition,
	getContainerSuggestion,
	getProductionHistorySnapshot,
	getRecipeExpectation,
	saveProductionActualTeam,
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
const scheduledElapsedHours = ref(0);
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
const selectedCapacityRun = computed(
	() =>
		props.plan?.capacity_plan?.runs?.find(
			(row) => Number(row.week_number) === Number(selectedRow.value?.week_number),
		) || null,
);
const selectedCapacityWindow = computed(
	() =>
		props.plan?.capacity_plan?.windows?.find(
			(row) => Number(row.week_number) === Number(selectedRow.value?.week_number),
		) || null,
);
const attendanceOptions = ["Completed", "Absent", "Cancelled"].map((value) => ({
	label: value,
	value,
}));
const completedTeam = computed(() =>
	employeeRows.filter((row) => row.employee && row.completion_status === "Completed"),
);
const actualTeamHours = computed(
	() => completedTeam.value.length * Number(actualElapsedHours.value || 0),
);
const actualLabourPace = computed(() =>
	Number(actualOutput.value || 0)
		? (actualTeamHours.value * 60) / Number(actualOutput.value)
		: 0,
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
watch([teamTemplate, scheduledElapsedHours, actualElapsedHours], () => {
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
		scheduledElapsedHours,
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
		if (runtimeConfig.isNative) {
			await restoreLocalProductionDraft().catch(() => {});
			await reconcileQueuedProduction().catch(() => {});
		}
		hydrating = false;
		return;
	}
	adHocMode.value = false;
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
		...(run.value?.employees || []).map((row) => ({
			...row,
			completion_status:
				row.completion_status === "Assigned" ? "Completed" : row.completion_status,
		})),
	);
	teamTemplate.value =
		run.value?.team_template || props.plan?.capacity_plan?.default_team_template || "";
	scheduledElapsedHours.value = Number(
		run.value?.scheduled_elapsed_hours ||
			selectedCapacityRun.value?.scheduled_elapsed_hours ||
			selectedCapacityWindow.value?.scheduled_elapsed_hours ||
			8,
	);
	actualElapsedHours.value = Number(
		run.value?.actual_elapsed_hours || 0,
	);
	dirtySinceSave.value = false;
	if (runtimeConfig.isNative) {
		await restoreLocalProductionDraft().catch(() => {});
		await reconcileQueuedProduction().catch(() => {});
	}
	await hydrateContainerSuggestion();
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
	employeeRows.splice(
		0,
		employeeRows.length,
		...(draft.employees || []).map((row) => ({
			...row,
			completion_status:
				row.completion_status === "Assigned" ? "Completed" : row.completion_status,
		})),
	);
	teamTemplate.value = draft.team_template || "";
	scheduledElapsedHours.value = Number(draft.scheduled_elapsed_hours || 0);
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
		scheduled_elapsed_hours: undefined,
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
			run.value = await saveProductionActualTeam(
				run.value.name,
				employeeRows,
				teamTemplate.value,
				actualElapsedHours.value,
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
			run.value = await saveProductionActualTeam(
				run.value.name,
				employeeRows,
				teamTemplate.value,
				actualElapsedHours.value,
			);
		}
		if (!queuedMutationId.value) {
			await clearFormDraft("production-run").catch(() => {});
			dirtySinceSave.value = false;
		}
		return Boolean(run.value?.name && !queuedMutationId.value);
	} catch (exception) {
		error.value = exception.message;
		return false;
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

async function saveAndPostRun() {
	if (run.value?.docstatus || draftLocked.value) return;
	const saved = await saveRun();
	if (!saved || queuedMutationId.value) return;
	await postRun();
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

function roundQuantity(value) {
	return Math.round(Number(value || 0) * 1000) / 1000;
}
function quantity(value) {
	return roundQuantity(value).toLocaleString("en-ZA", { maximumFractionDigits: 3 });
}
const recipeOptions = computed(() =>
	(props.snapshot?.options?.recipes || []).map((row) => ({
		label: row.recipe_name,
		value: row.name,
	})),
);
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
async function hydrateContainerSuggestion() {
	if (Number(actualOutput.value) <= 0) {
		containerSuggestion.value = null;
		return;
	}
	if (!containerCountManuallySet.value) await loadContainerSuggestion();
}
function setFinishedContainerCount(value) {
	containerCountManuallySet.value = true;
	finishedContainerCount.value = value;
}
async function openInstructions() {
	error.value = "";
	if (!selectedRecipe.value || Number(plannedOutput.value) <= 0)
		return (error.value = "Choose a meal and run target before building the cooking plan.");
	if (!run.value || dirtySinceSave.value) {
		const saved = await saveRun();
		if (!saved) return;
	}
	if (queuedMutationId.value)
		return (error.value = "Connect and synchronize this production draft before opening its cooking plan.");
	await router.push({ name: "BulkBiteKitchenPlan", params: { runName: run.value.name } });
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
				<div><p class="eyebrow">Production truth</p><h1>Production history</h1></div>
				<div class="button-row"><SystemOperationalButton variant="outline" :loading="busy" @click="loadHistory">Refresh</SystemOperationalButton><SystemOperationalButton variant="solid" @click="emit('close')">Record production</SystemOperationalButton></div>
			</header>
			<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
			<section v-if="history" class="history-summary" :class="history.summary.needs_another_run ? 'is-behind' : 'is-ready'">
				<div><p class="eyebrow">Current service period</p><h2>{{ history.summary.needs_another_run ? "More production is needed" : history.summary.status === "Ahead" ? "Production is ahead" : "Production is on pace" }}</h2><p>{{ history.summary.needs_another_run ? `${quantity(history.summary.remaining_customer_qty)} kg still has to be made for customers.` : history.summary.planned_date ? `Current customer service is dated ${history.summary.planned_date}.` : "Posted output covers the current customer requirement." }}</p></div>
				<div class="metric-board"><div><strong>{{ quantity(history.summary.customer_required_qty) }} kg</strong><span>customers need</span></div><div><strong>{{ quantity(history.summary.planned_qty) }} kg</strong><span>theory planned</span></div><div><strong>{{ quantity(history.summary.actual_qty) }} kg</strong><span>actually made</span></div><div><strong>{{ quantity(Math.abs(history.summary.output_difference_qty)) }} kg</strong><span>{{ history.summary.output_difference_qty < 0 ? "missing" : "above need" }}</span></div></div>
			</section>
			<SystemAccordion v-if="history" type="multiple" :default-value="['food-allocation', 'run-evidence', 'container-position']" class="production-details">
			<SystemAccordionItem value="food-allocation" class="data-section production-details__card">
				<SystemAccordionTrigger class="production-details__trigger"><div><span>Finished food allocation</span><strong>Where the food went</strong></div></SystemAccordionTrigger>
				<SystemAccordionContent class="production-details__content">
				<div class="metric-board"><div v-for="(value, label) in history.summary.allocations" :key="label"><strong>{{ quantity(value) }} kg</strong><span>{{ label }}</span></div></div>
				</SystemAccordionContent>
			</SystemAccordionItem>
			<SystemAccordionItem value="run-evidence" class="data-section production-details__card">
				<SystemAccordionTrigger class="production-details__trigger"><div><span>Run evidence</span><strong>Theory against actual</strong></div><SystemBadge>{{ history.runs.length }} posted runs</SystemBadge></SystemAccordionTrigger>
				<SystemAccordionContent class="production-details__content">
				<div v-if="history.service_periods?.length" class="skipped-week-list"><article v-for="item in history.service_periods" :key="item.name" :class="`is-${item.status.toLowerCase().replaceAll(' ', '-')}`"><div><SystemBadge :theme="item.status === 'Missed' ? 'red' : item.status === 'Fulfilled' ? 'green' : undefined">{{ item.status }}</SystemBadge><strong>{{ item.finished_item }}</strong><small>{{ item.planned_date }} · cycle {{ item.cycle_number }}, meal {{ item.meal_number }}</small></div><span v-if="item.status === 'Missed'">{{ quantity(item.missing_output_qty) }} kg missing</span><span v-else-if="item.status === 'Fulfilled'">{{ quantity(item.actual_output_qty) }} kg made</span><span v-else>{{ item.resolution_reason }}</span></article></div>
				<div class="history-run-list"><article v-for="item in history.runs" :key="item.name"><div class="history-run-heading"><div><strong>{{ item.finished_item }}</strong><small>{{ item.production_date }} · {{ item.name }}</small></div><SystemBadge :theme="item.customer_coverage_status === 'Short' ? 'red' : 'green'">{{ item.customer_coverage_status }}</SystemBadge></div><div class="metric-board"><div><strong>{{ quantity(item.planned_output_qty) }} kg</strong><span>planned</span></div><div><strong>{{ quantity(item.actual_output_qty) }} kg</strong><span>made</span></div><div><strong>{{ quantity(item.theory_customer_qty) }} kg</strong><span>customer theory</span></div><div><strong>{{ quantity(item.unallocated_output_qty) }} kg</strong><span>unallocated</span></div><div><strong>{{ item.finished_container_count }}</strong><span>containers filled</span></div><div><strong>{{ quantity(item.actual_labour_minutes_per_kg) }} min/kg</strong><span>actual labour rate</span></div></div><div v-if="item.allocations.length" class="allocation-strip"><span v-for="allocationRow in item.allocations" :key="allocationRow.name">{{ allocationRow.allocation_type }}: {{ quantity(allocationRow.quantity) }} {{ allocationRow.uom }}</span></div></article></div>
				</SystemAccordionContent>
			</SystemAccordionItem>
			<SystemAccordionItem value="container-position" class="data-section production-details__card">
				<SystemAccordionTrigger class="production-details__trigger"><div><span>Reusable containers</span><strong>Container position</strong></div></SystemAccordionTrigger>
				<SystemAccordionContent class="production-details__content"><div class="metric-board"><div><strong>{{ history.containers.states.Clean || 0 }}</strong><span>clean</span></div><div><strong>{{ history.containers.states.Filled || 0 }}</strong><span>filled food</span></div><div><strong>{{ history.containers.states['With Customer'] || 0 }}</strong><span>with customers</span></div><div><strong>{{ history.containers.overdue || 0 }}</strong><span>overdue</span></div><div><strong>{{ history.containers.states.Maintenance || 0 }}</strong><span>maintenance</span></div></div></SystemAccordionContent>
			</SystemAccordionItem>
			</SystemAccordion>
		</template>
		<template v-else>
		<header class="workflow-header">
			<div>
				<p class="eyebrow">Production</p>
				<h1>{{ adHocMode ? "Record an off-plan meal" : "Record the next meal" }}</h1>
				<p>
					{{
						adHocMode
							? "Off-plan run. The meal direction does not move."
							: "Saving keeps a draft; posting moves stock once."
					}}
				</p>
			</div>
			<div class="button-row">
				<SystemOperationalButton variant="outline" @click="emit('open-history')"
					>Production history</SystemOperationalButton
				><SystemBadge v-if="selectedRow && !adHocMode"
					>Cycle {{ station.cycle_number || 1 }} · Meal
					{{ selectedRow.week_number }}</SystemBadge
				>
			</div>
		</header>
		<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
		<div v-if="offlineNotice" class="state-message" role="status">{{ offlineNotice }}</div>
		<div v-if="station.behind_calendar && station.calendar?.row" class="state-message state-message--warning" role="status">
			This saved draft is behind the current calendar direction. The upcoming slot is meal {{ station.calendar.row.week_number }} on {{ station.calendar.planned_date }}. Finish or post this draft first so its measurements are not lost.
		</div>
		<div v-if="!plan && !adHocMode" class="state-message">
			<p>Set the current meal direction, or record an off-plan production run.</p>
			<SystemOperationalButton variant="outline" @click="startAdHocProduction"
				>Make something else</SystemOperationalButton
			>
		</div>
		<template v-else-if="selectedRow || adHocMode">
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
						<p v-if="adHocMode">Choose an approved recipe and target. This run will not move the planned meal direction.</p>
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
						:disabled="!adHocMode || Boolean(run) || draftLocked"
							@update:model-value="changeRecipe"
							@create="openRecipeRecords(true)"
							@manage="openRecipeRecords(false)"
					/><SystemFormControl
							v-model="plannedOutput"
							type="number"
							label="Target for this run (kg)"
							min="0.1"
							step="0.1"
						:disabled="!adHocMode || Boolean(run) || draftLocked"
						/>
						<SystemOperationalButton
							v-if="!run"
							class="custom-run-trigger"
							variant="subtle"
							:disabled="draftLocked"
							@click="adHocMode ? returnToDirection() : startAdHocProduction()"
						>{{ adHocMode ? "Return to direction" : "Custom run" }}</SystemOperationalButton>
					</div>
				<div v-if="!adHocMode && selectedRow.remaining_output_qty" class="direction-note">
					<strong
						>{{ quantity(selectedRow.completed_output_qty) }} kg has already been
						made. This run targets the remaining
						{{ quantity(selectedRow.remaining_output_qty) }} kg.</strong>
					</div>
					<div class="button-row instruction-actions">
						<SystemOperationalButton
							variant="outline"
							:loading="busy"
							@click="openInstructions"
						>Build cooking plan</SystemOperationalButton>
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
							/><SystemFormControl
								v-model="actualElapsedHours"
								type="number"
								label="Actual elapsed time (hours)"
								min="0"
								step="0.1"
								size="lg"
								:disabled="draftLocked"
							/>
						</div>
					<div class="button-row">
						<SystemOperationalButton
							v-if="!run?.docstatus"
							variant="solid"
							size="lg"
							:loading="busy"
							:disabled="draftLocked"
							@click="saveAndPostRun"
							>{{
								draftLocked ? "Waiting to sync" : "Post production run"
							}}</SystemOperationalButton
						>
						</div>
					</div>
					<div v-if="containerSuggestion?.available" class="container-suggestion">
						<div><span>Suggested packing</span><strong>{{ containerSuggestion.suggested_count }} × {{ quantity(containerSuggestion.capacity_qty) }} {{ containerSuggestion.capacity_uom }}</strong><small>{{ containerSuggestion.container_type_name }}. The count rounds up so all recorded food has space.</small></div>
						<div><span>Your entry</span><strong>{{ finishedContainerCount || 0 }} containers</strong><small v-if="finishedContainerCount > 0">{{ quantity(actualOutput / finishedContainerCount) }} kg average fill</small></div>
					</div>
				</section>
				<SystemAccordion type="multiple" class="production-details">
				<SystemAccordionItem value="measurements" class="data-section production-details__card">
					<SystemAccordionTrigger class="production-details__trigger"><div class="section-heading">
						<div>
							<p class="eyebrow">Measurements</p>
							<h2>Actual items used and production notes</h2>
							<p>Use quantity used, or enter what remained after the cook.</p>
						</div>
						<SystemBadge>{{ measurements.length }} items</SystemBadge>
					</div></SystemAccordionTrigger>
					<SystemAccordionContent class="production-details__content">
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
					</SystemAccordionContent>
				</SystemAccordionItem>
				</SystemAccordion>
				<SystemAccordion type="multiple" :default-value="['actual-timing']" class="production-details">
				<SystemAccordionItem value="actual-timing" class="data-section actual-timing-section production-details__card">
					<SystemAccordionTrigger class="production-details__trigger"><div class="section-heading">
						<div>
							<p class="eyebrow">Actual timing</p>
							<h2>Who worked the cook</h2>
						</div>
						<SystemBadge>{{ completedTeam.length }} COMPLETED</SystemBadge>
					</div></SystemAccordionTrigger>
					<SystemAccordionContent class="production-details__content">
					<div class="actual-timing-grid">
						<div class="calculated-hours"><span>Actual team-hours</span><strong>{{ quantity(actualTeamHours) }} h</strong></div>
						<div class="calculated-hours"><span>Actual labour rate</span><strong>{{ quantity(actualLabourPace) }} min/kg</strong></div>
					</div>
					<div v-if="employeeRows.length" class="actual-team-list">
						<article v-for="row in employeeRows" :key="row.employee">
							<div><strong>{{ row.employee_name || row.employee }}</strong><small>{{ row.employee_type || "Production team" }}</small></div>
							<SystemSelect v-model="row.completion_status" label="Actual attendance" :options="attendanceOptions" :disabled="draftLocked" />
							<div class="calculated-hours"><span>Hours worked</span><strong>{{ row.completion_status === "Completed" ? quantity(actualElapsedHours) : "0" }} h</strong></div>
						</article>
					</div>
					<div v-else class="direction-note">No planned team is attached to this run yet.</div>
					</SystemAccordionContent>
				</SystemAccordionItem>
				</SystemAccordion>
				<footer v-if="run?.docstatus" class="posting-bar">
					<div>
						<SystemBadge>STOCK UPDATED</SystemBadge>
						<p>Ingredient use and finished meals are now reflected in stock.</p>
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
	</section>
</template>

<style scoped>
.production-details{display:grid}.production-details__card{overflow:hidden}.production-details__trigger{width:100%;text-align:left;text-decoration:none!important}.production-details__trigger .section-heading{width:100%;padding-right:var(--spacing-xs)}.production-details__content{display:grid;gap:var(--spacing-s)}
.skipped-week-list{display:grid;gap:var(--spacing-xs);margin-bottom:var(--spacing-m)}.skipped-week-list article{display:flex;align-items:center;justify-content:space-between;gap:var(--spacing-s);padding:var(--spacing-s);border:var(--border-width-1) solid var(--theme-border);border-radius:var(--component-radius-card);background:var(--theme-surface-raised)}.skipped-week-list article.is-missed{border-color:color-mix(in oklch,var(--theme-error) 38%,var(--theme-border));background:color-mix(in oklch,var(--theme-error) 6%,var(--theme-surface-raised))}.skipped-week-list article.is-fulfilled{border-color:color-mix(in oklch,var(--theme-success) 32%,var(--theme-border));background:color-mix(in oklch,var(--theme-success) 5%,var(--theme-surface-raised))}.skipped-week-list article>div{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:var(--spacing-3xs) var(--spacing-xs)}.skipped-week-list strong{min-width:0}.skipped-week-list small{grid-column:2;color:var(--theme-text-muted)}.skipped-week-list>article>span{white-space:nowrap;font-weight:var(--font-weight-700)}
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
.container-suggestion {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--spacing-xs);
	margin-top: var(--spacing-s);
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
.actual-timing-grid {
	display: grid;
	grid-template-columns: minmax(14rem, 1fr) repeat(2, minmax(10rem, 0.65fr));
	align-items: end;
	gap: var(--spacing-s);
	margin-top: var(--spacing-s);
}
.actual-team-list {
	display: grid;
	gap: var(--spacing-xs);
	margin-top: var(--spacing-s);
}
.custom-run-trigger {
	align-self: end;
}

.actual-timing-section > .direction-note {
	margin-top: var(--spacing-s);
}
.actual-team-list article {
	display: grid;
	grid-template-columns: minmax(14rem, 1fr) minmax(12rem, 0.8fr) minmax(8rem, 0.5fr);
	align-items: end;
	gap: var(--spacing-xs);
	padding: var(--spacing-xs);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-field);
	background: var(--theme-surface-raised);
}
.actual-team-list article > div:first-child {
	display: grid;
	gap: var(--spacing-3xs);
}
.actual-team-list small {
	color: var(--theme-text-muted);
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
	.actual-timing-grid,
	.actual-team-list article {
		grid-template-columns: 1fr 1fr;
	}
	.actual-team-list article > div:first-child {
		grid-column: 1 / -1;
	}
}
@media (max-width: 44rem) {
	.skipped-week-list article{align-items:flex-start;flex-direction:column}.skipped-week-list>article>span{white-space:normal}
	.production-direction-grid,
	.allocation-grid,
	.container-suggestion,
	.actual-timing-grid,
	.actual-team-list article {
		grid-template-columns: 1fr;
	}
	.production-direction-grid > *:last-child {
		grid-column: auto;
	}
	.allocation-history article {
		align-items: flex-start;
		flex-direction: column;
	}
	.actual-team-list article > div:first-child {
		grid-column: auto;
	}
}
</style>
