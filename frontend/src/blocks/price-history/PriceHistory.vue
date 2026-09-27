<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import {
	SystemBadge,
	SystemCheckboxShadcn,
	SystemDatePicker,
	SystemFileUploader,
	SystemFormControl,
	SystemLinkedRecordField,
	SystemOperationalButton,
	SystemSelect,
	SystemTextarea,
} from "@/desyium";
import {
	applyPriceWorkbook,
	applySpreadsheetWorkspaceImport,
	getPriceImportFields,
	getPriceImportImprovementStatus,
	getPurchasePriceHistory,
	inspectPriceFile,
	previewPriceWorkbook,
	priceWorkbookUrl,
	startPriceImportImprovement,
	downloadAuthenticatedFile,
	reviewPriceWorkbook,
	getSpreadsheetWorkspaceContract,
	inspectSpreadsheetWorkspaceFile,
	previewSpreadsheetWorkspaceImport,
	reviewSpreadsheetWorkspaceImport,
	spreadsheetWorkspaceUrl,
} from "@/resources/api";

// =============================================================================
// region PRICE CATALOGUE AND IMPORT WORKSPACE
// =============================================================================

const props = defineProps({
	snapshot: { type: Object, default: null },
	inventory: { type: Object, default: null },
	mode: { type: String, default: "catalogue" },
});
defineEmits(["changed"]);

// region 1. SHARED STATE

const busy = ref(false);
const error = ref("");
const success = ref("");

function clearMessages() {
	error.value = "";
	success.value = "";
}
function money(value) {
	return value === null || value === undefined
		? "Not available"
		: `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function quantity(value) {
	return Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 2 });
}
function statusTheme(status) {
	return status === "error" ? "red" : status === "unchanged" ? undefined : "green";
}

// endregion 1. SHARED STATE

// region 1. CATALOGUE EXCHANGE

const result = ref({
	rows: [],
	summary: { theory_count: 0, actual_count: 0, item_count: 0, supplier_count: 0 },
});
const exchangeTarget = ref("catalogue");
const setupDoctype = ref("");
const exchangeTargetOptions = [
	{ label: "Stock catalogue", value: "catalogue" },
	{ label: "Recipes", value: "recipes" },
	{ label: "Other setup data", value: "setup" },
];
const fieldContract = ref({ fields: [], default_fields: [] });
const selectedFields = ref([]);
const importInspection = ref(null);
const importMapping = reactive({});
const importBatch = ref(null);
const importImprovementStage = ref("");
const filters = reactive({ item_code: "", supplier: "", from_date: "", to_date: "" });
const itemOptions = computed(() =>
	(props.inventory?.items || []).map((item) => ({
		label: item.item_name,
		value: item.item_code,
	})),
);
const supplierOptions = computed(() =>
	(props.snapshot?.options?.suppliers || []).map((value) => ({ label: value, value })),
);
const targetFieldOptions = computed(() => [
	{ label: "Do not import", value: "" },
	...(importInspection.value?.target_fields || []),
]);
const importUnitOptions = ["g", "Kg", "ml", "Litre", "Each"].map((value) => ({
	label: value,
	value,
}));
const stockUnitOptions = ["Kg", "Litre", "Each"].map((value) => ({ label: value, value }));
const importEntityGroups = computed(() =>
	importBatch.value
		? [
				{ key: "suppliers", label: "Suppliers", rows: importBatch.value.suppliers || [] },
				{
					key: "categories",
					label: "Categories",
					rows: importBatch.value.categories || [],
				},
				{ key: "items", label: "Items", rows: importBatch.value.items || [] },
			]
		: [],
);
const importHasChanges = computed(
	() =>
		importBatch.value &&
		(importBatch.value.counts.insert > 0 || importBatch.value.counts.update > 0),
);
const setupTargetOptions = computed(() => fieldContract.value.setup_targets || []);
const exchangeLabel = computed(
	() =>
		exchangeTargetOptions.find((option) => option.value === exchangeTarget.value)?.label ||
		"Spreadsheet",
);
const isCatalogueExchange = computed(() => exchangeTarget.value === "catalogue");
const matchedImportColumns = computed(() => Object.values(importMapping).filter(Boolean).length);

function toggleField(field) {
	selectedFields.value = selectedFields.value.includes(field)
		? selectedFields.value.filter((value) => value !== field)
		: [...selectedFields.value, field];
}
function reviewErrorCount(rows) {
	return rows.reduce((total, row) => total + (row.errors?.length ? 1 : 0), 0);
}
async function downloadWorkbook() {
	const url = isCatalogueExchange.value
		? priceWorkbookUrl(selectedFields.value)
		: spreadsheetWorkspaceUrl(exchangeTarget.value, selectedFields.value, setupDoctype.value);
	try {
		await downloadAuthenticatedFile(url, `bulkbite-${exchangeTarget.value}.xlsx`);
	} catch (exception) {
		error.value = exception.message;
	}
}
function uploadedFileUrl(file) {
	return file?.file_url || file?.message?.file_url || file?.data?.file_url || "";
}
function variance(row) {
	if (row.record_type !== "Actual" || row.variance === null || row.variance === undefined)
		return "No matching theory";
	const sign = Number(row.variance) > 0 ? "+" : "";
	return `${sign}${money(row.variance)} (${sign}${Number(row.variance_percent || 0).toFixed(1)}%)`;
}
function rowLabel(row) {
	return row.item_name || row.record_name || `Spreadsheet row ${row.row_number}`;
}

async function loadCatalogue() {
	busy.value = true;
	clearMessages();
	try {
		const [contract, history] = await Promise.all([
			getPriceImportFields(),
			getPurchasePriceHistory(filters),
		]);
		fieldContract.value = contract;
		selectedFields.value = [...contract.default_fields];
		result.value = history;
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function changeExchangeTarget(value = exchangeTarget.value) {
	exchangeTarget.value = value;
	setupDoctype.value = "";
	importInspection.value = null;
	importBatch.value = null;
	Object.keys(importMapping).forEach((key) => delete importMapping[key]);
	busy.value = true;
	clearMessages();
	try {
		fieldContract.value =
			value === "catalogue"
				? await getPriceImportFields()
				: await getSpreadsheetWorkspaceContract(value);
		selectedFields.value = [...fieldContract.value.default_fields];
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function changeSetupDoctype(value) {
	setupDoctype.value = value;
	importInspection.value = null;
	importBatch.value = null;
	if (!value) return;
	busy.value = true;
	clearMessages();
	try {
		fieldContract.value = await getSpreadsheetWorkspaceContract("setup", value);
		selectedFields.value = [...fieldContract.value.default_fields];
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function onImportUpload(file) {
	const fileUrl = uploadedFileUrl(file);
	if (!fileUrl)
		return (error.value = "The spreadsheet uploaded, but its private address was missing.");
	busy.value = true;
	clearMessages();
	importBatch.value = null;
	try {
		importInspection.value = isCatalogueExchange.value
			? await inspectPriceFile(fileUrl)
			: await inspectSpreadsheetWorkspaceFile(
					exchangeTarget.value,
					fileUrl,
					setupDoctype.value,
				);
		Object.keys(importMapping).forEach((key) => delete importMapping[key]);
		Object.assign(importMapping, importInspection.value.suggested_mapping);
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function previewImport() {
	busy.value = true;
	clearMessages();
	try {
		importBatch.value = isCatalogueExchange.value
			? await previewPriceWorkbook(importInspection.value.file_url, importMapping)
			: await previewSpreadsheetWorkspaceImport(
					exchangeTarget.value,
					importInspection.value.file_url,
					importMapping,
					setupDoctype.value,
				);
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function improveImport() {
	busy.value = true;
	clearMessages();
	importImprovementStage.value = "saving your edits";
	try {
		importBatch.value = await reviewPriceWorkbook(importBatch.value.name, reviewedProposal());
		const job = await startPriceImportImprovement(importBatch.value.name);
		importBatch.value = await waitForPriceImprovement(job.job_id);
		success.value =
			"AI suggestions are ready to review. Nothing has been applied to the catalogue.";
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
		importImprovementStage.value = "";
	}
}

async function waitForPriceImprovement(jobId) {
	const deadline = Date.now() + 10 * 60 * 1000;
	while (Date.now() < deadline) {
		const state = await getPriceImportImprovementStatus(jobId);
		importImprovementStage.value = state.stage || state.status;
		if (state.status === "finished") return state.result;
		if (state.status === "failed")
			throw new Error(
				state.error || "AI catalogue improvement failed. Your saved review is unchanged.",
			);
		await new Promise((resolve) => window.setTimeout(resolve, 1500));
	}
	throw new Error(
		"AI catalogue improvement took too long. Your saved review is unchanged, so you can try again later.",
	);
}

function reviewedProposal() {
	if (exchangeTarget.value === "recipes")
		return {
			target: "recipes",
			mapping: importBatch.value.mapping || {},
			recipes: importBatch.value.recipes || [],
		};
	if (exchangeTarget.value === "setup")
		return {
			target: "setup",
			setup_doctype: importBatch.value.setup_doctype,
			mapping: importBatch.value.mapping || {},
			records: importBatch.value.records || [],
		};
	return {
		mapping: importBatch.value.mapping || {},
		suppliers: importBatch.value.suppliers || [],
		categories: importBatch.value.categories || [],
		items: importBatch.value.items || [],
		offers: importBatch.value.offers || importBatch.value.rows || [],
		ai_used: Boolean(importBatch.value.ai_used),
		ai_notes: importBatch.value.ai_notes || "",
	};
}

async function saveImportReview() {
	busy.value = true;
	clearMessages();
	try {
		importBatch.value = isCatalogueExchange.value
			? await reviewPriceWorkbook(importBatch.value.name, reviewedProposal())
			: await reviewSpreadsheetWorkspaceImport(importBatch.value.name, reviewedProposal());
		success.value = "Review saved and revalidated. Nothing has been applied yet.";
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function applyImport() {
	busy.value = true;
	clearMessages();
	try {
		importBatch.value = isCatalogueExchange.value
			? await reviewPriceWorkbook(importBatch.value.name, reviewedProposal())
			: await reviewSpreadsheetWorkspaceImport(importBatch.value.name, reviewedProposal());
		if (importBatch.value.counts.error > 0)
			throw new Error("Fix the highlighted review errors before applying.");
		importBatch.value = isCatalogueExchange.value
			? await applyPriceWorkbook(importBatch.value.name)
			: await applySpreadsheetWorkspaceImport(importBatch.value.name);
		success.value = `Reviewed ${exchangeLabel.value.toLowerCase()} records were applied. Stock and ledgers were not changed.`;
		if (isCatalogueExchange.value) await loadPriceHistory();
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function loadPriceHistory() {
	if (filters.from_date && filters.to_date && filters.from_date > filters.to_date)
		return (error.value = "From date must be on or before to date.");
	busy.value = true;
	clearMessages();
	try {
		result.value = await getPurchasePriceHistory(filters);
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

// endregion 1. CATALOGUE EXCHANGE

onMounted(loadCatalogue);

// endregion PRICE CATALOGUE AND IMPORT WORKSPACE
</script>

<template>
	<section data-block="price-history" class="workflow-block">
		<header class="workflow-header">
			<div>
				<p class="eyebrow">
					{{ mode === "import" ? "Data import" : "Stock setup" }}
				</p>
				<h1>
					{{ mode === "import" ? "Import and export" : "Price catalogue" }}
				</h1>
				<p>
					{{
						mode === "import"
							? "Bring reviewed stock, recipe, and setup records into BulkBite through one controlled spreadsheet flow."
							: "Maintain the supplier prices used to calculate what stock should cost."
					}}
				</p>
			</div>
			<SystemBadge>{{
				mode === "import" ? "Reviewed writes only" : "Does not change stock"
			}}</SystemBadge>
		</header>
		<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
		<div v-if="success" class="state-message" role="status">{{ success }}</div>

		<section v-if="mode === 'import'" class="form-section exchange-target">
			<div class="section-heading">
				<div>
					<p class="eyebrow">Spreadsheet workspace</p>
					<h2>Choose what you are working with</h2>
					<p>
						Stock and recipes use guided flows. Other setup data is restricted to
						approved record types.
					</p>
				</div>
			</div>
			<div class="field-grid">
				<label class="field-shell"
					><span>Data type</span
					><SystemSelect
						:model-value="exchangeTarget"
						:options="exchangeTargetOptions"
						@update:model-value="changeExchangeTarget" /></label
				><label v-if="exchangeTarget === 'setup'" class="field-shell"
					><span>Setup record type</span
					><SystemSelect
						:model-value="setupDoctype"
						:options="setupTargetOptions"
						placeholder="Choose a record type"
						@update:model-value="changeSetupDoctype"
				/></label>
			</div>
		</section>
		<section
			v-if="mode === 'import' && (exchangeTarget !== 'setup' || setupDoctype)"
			class="form-section"
		>
			<div class="section-heading">
				<div>
					<p class="eyebrow">Download</p>
					<h2>Choose the columns</h2>
					<p>
						The file contains one header row and the selected
						{{ exchangeLabel.toLowerCase() }} data. Nothing else.
					</p>
				</div>
			</div>
			<div class="field-choice-grid">
				<label v-for="field in fieldContract.fields" :key="field.fieldname"
					><SystemCheckboxShadcn
						:model-value="selectedFields.includes(field.fieldname)"
						@update:model-value="toggleField(field.fieldname)"
					/><span>{{ field.label }}</span></label
				>
			</div>
			<div class="button-row">
				<SystemOperationalButton
					variant="solid"
					:disabled="!selectedFields.length"
					@click="downloadWorkbook"
					>Download {{ exchangeLabel.toLowerCase() }}</SystemOperationalButton
				>
			</div>
		</section>
		<section
			v-if="mode === 'import' && (exchangeTarget !== 'setup' || setupDoctype)"
			class="form-section"
		>
			<div class="section-heading">
				<div>
					<p class="eyebrow">Upload</p>
					<h2>Match the spreadsheet columns</h2>
					<p>
						BulkBite finds the most useful worksheet and header row, then suggests
						matches you can change.
					</p>
				</div>
			</div>
			<SystemFileUploader
				:upload-args="{ private: true }"
				:file-types="['.xlsx', '.xlsm', '.csv']"
				@success="onImportUpload"
				><template #default="upload"
					><SystemOperationalButton
						variant="outline"
						:loading="upload.uploading || busy"
						@click="upload.openFileSelector"
						>{{
							importInspection ? "Replace spreadsheet" : "Upload spreadsheet"
						}}</SystemOperationalButton
					></template
				></SystemFileUploader
			>
			<div v-if="importInspection?.source_note" class="state-message" role="status">
				<strong>{{ importInspection.source_note }}</strong>
				<p>
					{{ matchedImportColumns }} of
					{{ importInspection.source_columns.length }} columns matched automatically.
				</p>
			</div>
			<div v-if="importInspection" class="mapping-list">
				<article
					v-for="source in importInspection.source_columns"
					:key="source.column"
				>
					<div>
						<strong>{{ source.column }}</strong
						><small>{{ source.samples.join(" · ") || "No sample value" }}</small>
					</div>
					<SystemSelect
						:model-value="importMapping[source.column]"
						:options="targetFieldOptions"
						placeholder="Do not import"
						@update:model-value="importMapping[source.column] = $event"
					/>
				</article>
			</div>
			<div v-if="importInspection" class="button-row">
				<SystemOperationalButton
					variant="solid"
					:loading="busy"
					:disabled="!matchedImportColumns || !importInspection.row_count"
					@click="previewImport"
					>Preview {{ importInspection.row_count }} rows</SystemOperationalButton
				>
			</div>
		</section>
		<section v-if="mode === 'import' && importBatch" class="data-section catalogue-review">
			<div class="section-heading">
				<div>
					<p class="eyebrow">Editable review</p>
					<h2>Exactly what BulkBite will add or update</h2>
					<p>
						Edit the proposed {{ exchangeLabel.toLowerCase() }} values here. Saving
						the review does not apply records or change stock.
					</p>
				</div>
				<SystemBadge :theme="importBatch.status === 'Applied' ? 'green' : undefined">{{
					importBatch.status
				}}</SystemBadge>
			</div>
			<div class="metric-board metric-board--paper">
				<div>
					<strong>{{ importBatch.counts.insert }}</strong
					><span>new records</span>
				</div>
				<div>
					<strong>{{ importBatch.counts.update }}</strong
					><span>updates</span>
				</div>
				<div>
					<strong>{{ importBatch.counts.unchanged }}</strong
					><span>unchanged</span>
				</div>
				<div>
					<strong>{{ importBatch.counts.error }}</strong
					><span>errors</span>
				</div>
			</div>
			<div v-if="importBatch.status !== 'Applied'" class="button-row">
				<SystemOperationalButton
					v-if="isCatalogueExchange && importInspection?.ai_available"
					variant="outline"
					:loading="busy"
					@click="improveImport"
					>Improve suggestions with AI</SystemOperationalButton
				><SystemOperationalButton
					variant="outline"
					:loading="busy"
					@click="saveImportReview"
					>Save and recheck review</SystemOperationalButton
				>
			</div>
			<p v-if="busy && importImprovementStage" class="field-note" role="status">
				<strong>AI review:</strong> {{ importImprovementStage }}
			</p>
			<p v-if="importBatch.ai_used" class="field-note">
				<strong>AI suggestions used.</strong>
				{{
					importBatch.ai_notes ||
					"Review every suggested identity and pack value before applying."
				}}
			</p>

			<template v-if="isCatalogueExchange">
				<details
					v-for="group in importEntityGroups"
					:key="group.key"
					class="review-group"
					:open="reviewErrorCount(group.rows) > 0 || undefined"
				>
					<summary class="review-group-summary">
						<span
							><strong>{{ group.label }}</strong
							><small
								>{{ group.rows.length }} proposed or matched records</small
							></span
						><span class="review-group-meta"
							><SystemBadge v-if="reviewErrorCount(group.rows)" theme="red"
								>{{ reviewErrorCount(group.rows) }} errors</SystemBadge
							><span class="review-group-chevron" aria-hidden="true"
								>›</span
							></span
						>
					</summary>
					<div class="setup-review-list">
						<article
							v-for="row in group.rows"
							:key="`${group.key}-${row.source_key}`"
							class="setup-review-card"
						>
							<div class="review-card-heading">
								<div>
									<strong>{{
										row.name || row.item_name || row.source_key
									}}</strong
									><small>{{ row.reason }}</small>
								</div>
								<SystemBadge :theme="statusTheme(row.status)">{{
									row.status
								}}</SystemBadge>
							</div>
							<div v-if="group.key === 'suppliers'" class="review-field-grid">
								<SystemFormControl
									v-model="row.name"
									label="Supplier name"
									:disabled="importBatch.status === 'Applied'"
								/>
							</div>
							<div
								v-else-if="group.key === 'categories'"
								class="review-field-grid"
							>
								<SystemFormControl
									v-model="row.name"
									label="Category name"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.default_supplier"
									label="Default supplier"
									:disabled="importBatch.status === 'Applied'"
								/>
							</div>
							<div v-else class="review-field-grid">
								<SystemFormControl
									v-model="row.item_code"
									label="Item code"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.item_name"
									label="Item name"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.item_category"
									label="Category"
									:disabled="importBatch.status === 'Applied'"
								/><label class="field-shell"
									><span>Stock unit</span
									><SystemSelect
										v-model="row.stock_uom"
										:options="stockUnitOptions"
										size="lg"
										:disabled="importBatch.status === 'Applied'"
								/></label>
							</div>
							<p v-if="row.errors?.length" class="review-errors">
								{{ row.errors.join(" ") }}
							</p>
						</article>
					</div>
				</details>

				<details
					class="review-group"
					:open="reviewErrorCount(importBatch.offers) > 0 || undefined"
				>
					<summary class="review-group-summary">
						<span
							><strong>Supplier offers</strong
							><small
								>{{ importBatch.offers.length }} prices to review</small
							></span
						><span class="review-group-meta"
							><SystemBadge
								v-if="reviewErrorCount(importBatch.offers)"
								theme="red"
								>{{ reviewErrorCount(importBatch.offers) }} errors</SystemBadge
							><span class="review-group-chevron" aria-hidden="true"
								>›</span
							></span
						>
					</summary>
					<div class="offer-review-list">
						<article
							v-for="row in importBatch.offers"
							:key="row.row_number"
							class="offer-review-card"
						>
							<div class="review-card-heading">
								<div>
									<strong>{{ rowLabel(row) }}</strong
									><small
										>Spreadsheet row {{ row.row_number }} ·
										{{ Math.round(Number(row.confidence || 0) * 100) }}%
										confidence</small
									>
								</div>
								<SystemBadge :theme="statusTheme(row.status)">{{
									row.status
								}}</SystemBadge>
							</div>
							<p class="review-reason">{{ row.reason }}</p>
							<div class="review-field-grid review-field-grid--offer">
								<SystemFormControl
									v-model="row.item_code"
									label="Item code"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.item_name"
									label="Item name"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.supplier"
									label="Supplier"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.item_category"
									label="Category"
									:disabled="importBatch.status === 'Applied'"
								/>
							</div>
							<div class="review-field-grid review-field-grid--offer">
								<SystemFormControl
									v-model="row.values.supplier_item_code"
									label="Supplier item code"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.values.units_per_pack"
									type="number"
									min="0.1"
									step="0.1"
									label="Units per pack"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.values.unit_size"
									type="number"
									min="0.1"
									step="0.1"
									label="Size per unit"
									:disabled="importBatch.status === 'Applied'"
								/><label class="field-shell"
									><span>Size unit</span
									><SystemSelect
										v-model="row.values.purchase_uom"
										:options="importUnitOptions"
										size="lg"
										:disabled="importBatch.status === 'Applied'"
								/></label>
							</div>
							<div class="review-field-grid review-field-grid--offer">
								<SystemFormControl
									v-model="row.values.normal_price"
									type="number"
									min="0"
									step="0.1"
									label="Normal pack price"
									:disabled="importBatch.status === 'Applied'"
								/><SystemFormControl
									v-model="row.values.discounted_price"
									type="number"
									min="0"
									step="0.1"
									label="Discounted pack price"
									:disabled="importBatch.status === 'Applied'"
								/><SystemDatePicker
									v-model="row.values.discount_from"
									label="Discount from"
									format="YYYY-MM-DD"
									:disabled="importBatch.status === 'Applied'"
								/><SystemDatePicker
									v-model="row.values.discount_to"
									label="Discount to"
									format="YYYY-MM-DD"
									:disabled="importBatch.status === 'Applied'"
								/>
							</div>
							<SystemTextarea
								v-model="row.values.notes"
								label="Notes"
								:disabled="importBatch.status === 'Applied'"
							/>
							<p v-if="row.errors?.length" class="review-errors">
								{{ row.errors.join(" ") }}
							</p>
							<p v-else class="review-impact">
								{{
									row.changes?.length
										? `${row.changes.length} fields will change.`
										: "No offer fields will change."
								}}
							</p>
						</article>
					</div>
				</details>
			</template>
			<template v-else-if="exchangeTarget === 'recipes'">
				<details
					v-for="recipe in importBatch.recipes"
					:key="recipe.recipe_id || recipe.recipe_name"
					class="review-group"
					:open="recipe.status === 'error' || undefined"
				>
					<summary class="review-group-summary">
						<span
							><strong>{{ recipe.recipe_name || "Unnamed recipe" }}</strong
							><small
								>{{ recipe.ingredients.length }} ingredients ·
								{{ quantity(recipe.nominal_output_qty) }} kg output</small
							></span
						><span class="review-group-meta"
							><SystemBadge :theme="statusTheme(recipe.status)">{{
								recipe.status
							}}</SystemBadge
							><span class="review-group-chevron" aria-hidden="true"
								>›</span
							></span
						>
					</summary>
					<div class="recipe-review">
						<div class="review-field-grid review-field-grid--offer">
							<SystemFormControl
								v-model="recipe.recipe_name"
								label="Recipe name"
								:disabled="importBatch.status === 'Applied'"
							/><SystemFormControl
								v-model="recipe.version"
								type="number"
								min="1"
								step="1"
								label="Version"
								:disabled="importBatch.status === 'Applied'"
							/><SystemFormControl
								v-model="recipe.finished_item"
								label="Finished item code"
								:disabled="importBatch.status === 'Applied'"
							/><SystemFormControl
								v-model="recipe.finished_item_name"
								label="Finished item name"
								:disabled="importBatch.status === 'Applied'"
							/><SystemFormControl
								v-model="recipe.nominal_output_qty"
								type="number"
								min="0.1"
								step="0.1"
								label="Recipe output (kg)"
								:disabled="importBatch.status === 'Applied'"
							/>
						</div>
						<SystemTextarea
							v-model="recipe.instruction_guidance"
							label="Kitchen planning guidance"
							:disabled="importBatch.status === 'Applied'"
						/>
						<details class="review-subgroup" open>
							<summary>
								<strong>Ingredients</strong
								><span>{{ recipe.ingredients.length }}</span>
							</summary>
							<div class="recipe-ingredient-list">
								<article
									v-for="ingredient in recipe.ingredients"
									:key="ingredient.row_number"
								>
									<SystemFormControl
										v-model="ingredient.item_code"
										label="Ingredient item code"
										:disabled="importBatch.status === 'Applied'"
									/><SystemFormControl
										v-model="ingredient.item_name"
										label="Ingredient item name"
										:disabled="importBatch.status === 'Applied'"
									/><SystemFormControl
										v-model="ingredient.qty"
										type="number"
										min="0.1"
										step="0.1"
										label="Quantity"
										:disabled="importBatch.status === 'Applied'"
									/><label class="field-shell"
										><span>Stock unit</span
										><SystemSelect
											v-model="ingredient.uom"
											:options="stockUnitOptions"
											size="lg"
											:disabled="importBatch.status === 'Applied'"
									/></label>
									<p v-if="ingredient.errors?.length" class="review-errors">
										{{ ingredient.errors.join(" ") }}
									</p>
								</article>
							</div>
						</details>
						<details
							class="review-subgroup"
							:open="
								recipe.instruction_steps?.some(
									(step) => step.errors?.length,
								) || undefined
							"
						>
							<summary>
								<strong>Production instructions</strong
								><span>{{ recipe.instruction_steps?.length || 0 }}</span>
							</summary>
							<div class="recipe-instruction-list">
								<article
									v-for="step in recipe.instruction_steps || []"
									:key="step.row_number || step.step_number"
								>
									<SystemFormControl
										v-model="step.step_number"
										type="number"
										min="1"
										step="1"
										label="Step"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.step_name"
										label="Step name"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemTextarea
										v-model="step.instruction"
										label="Instruction"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.ingredient_items"
										label="Ingredient item codes"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.equipment_type"
										label="Equipment type"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.depends_on_steps"
										label="Depends on steps"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.duration_minutes"
										type="number"
										min="0"
										step="0.1"
										label="Base minutes"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.duration_per_kg_minutes"
										type="number"
										min="0"
										step="0.01"
										label="Minutes per kg"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.minimum_workers"
										type="number"
										min="1"
										step="1"
										label="Minimum workers"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemFormControl
										v-model="step.worker_role"
										label="Worker role"
										:disabled="importBatch.status === 'Applied'"
									/>
									<SystemTextarea
										v-model="step.quality_checkpoint"
										label="Quality checkpoint"
										:disabled="importBatch.status === 'Applied'"
									/>
									<label class="check-field"
										><SystemCheckboxShadcn
											v-model="step.can_run_concurrently"
											:disabled="importBatch.status === 'Applied'"
										/><span>Can run concurrently</span></label
									>
									<p v-if="step.errors?.length" class="review-errors">
										{{ step.errors.join(" ") }}
									</p>
								</article>
								<p
									v-if="!recipe.instruction_steps?.length"
									class="empty-state"
								>
									No instruction rows were supplied for this recipe.
								</p>
							</div>
						</details>
						<p v-if="recipe.errors?.length" class="review-errors">
							{{ recipe.errors.join(" ") }}
						</p>
					</div>
				</details>
			</template>
			<template v-else>
				<div class="setup-review-list">
					<article
						v-for="(row, index) in importBatch.records"
						:key="row.record_name || index"
						class="setup-review-card"
					>
						<div class="review-card-heading">
							<div>
								<strong>{{
									row.identity || `Spreadsheet row ${index + 2}`
								}}</strong
								><small>{{ importBatch.setup_doctype }}</small>
							</div>
							<SystemBadge :theme="statusTheme(row.status)">{{
								row.status
							}}</SystemBadge>
						</div>
						<div class="review-field-grid">
							<SystemFormControl
								v-for="field in fieldContract.fields"
								:key="field.fieldname"
								v-model="row.values[field.fieldname]"
								:label="field.label"
								:disabled="importBatch.status === 'Applied'"
							/>
						</div>
						<p v-if="row.errors?.length" class="review-errors">
							{{ row.errors.join(" ") }}
						</p>
					</article>
				</div>
			</template>
			<div v-if="importBatch.status !== 'Applied'" class="apply-boundary">
				<div>
					<strong>Final write boundary</strong>
					<p>
						{{
							importHasChanges
								? "This creates or updates only the records listed above. It never changes stock, receipts, or ledger entries."
								: `There are no ${exchangeLabel.toLowerCase()} changes to apply.`
						}}
					</p>
				</div>
				<SystemOperationalButton
					variant="solid"
					:disabled="importBatch.counts.error > 0 || !importHasChanges"
					:loading="busy"
					@click="applyImport"
					>Apply reviewed {{ exchangeLabel.toLowerCase() }}</SystemOperationalButton
				>
			</div>
		</section>
		<section v-if="mode === 'catalogue'" class="data-section">
			<div class="section-heading">
				<div>
					<p class="eyebrow">Price history</p>
					<h2>Theory versus receipt evidence</h2>
					<p>
						Compare the expected stock-unit price with what reviewed receipts
						prove.
					</p>
				</div>
			</div>
			<div class="field-grid">
				<SystemLinkedRecordField
					v-model="filters.item_code"
					label="Item"
					:options="itemOptions"
					placeholder="All items"
				/><SystemLinkedRecordField
					v-model="filters.supplier"
					label="Supplier"
					:options="supplierOptions"
					placeholder="All suppliers"
				/><SystemDatePicker
					v-model="filters.from_date"
					label="From date"
					format="YYYY-MM-DD"
				/><SystemDatePicker
					v-model="filters.to_date"
					label="To date"
					format="YYYY-MM-DD"
				/>
			</div>
			<div class="button-row">
				<SystemOperationalButton variant="outline" @click="loadPriceHistory"
					>Update history</SystemOperationalButton
				>
			</div>
			<div v-if="result.rows.length" class="price-table-wrap">
				<table class="price-table">
					<thead>
						<tr>
							<th>Date</th>
							<th>Basis</th>
							<th>Item</th>
							<th>Supplier</th>
							<th>Pack</th>
							<th>Pack price</th>
							<th>Price per stock unit</th>
							<th>Theory</th>
							<th>Difference</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in result.rows"
							:key="`${row.record_type}-${row.record_name}`"
						>
							<td>{{ row.date }}</td>
							<td>{{ row.record_type }}</td>
							<td>{{ row.item_name }}</td>
							<td>{{ row.supplier }}</td>
							<td>
								{{ quantity(row.packs) }} ×
								{{ quantity(row.units_per_pack) }} ×
								{{ quantity(row.unit_size) }} {{ row.purchase_uom }}
							</td>
							<td>{{ money(row.pack_price) }}</td>
							<td>{{ money(row.stock_unit_price) }} / {{ row.stock_uom }}</td>
							<td>{{ money(row.theory_stock_unit_price) }}</td>
							<td>{{ variance(row) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</section>
</template>

<style scoped>
.field-choice-grid {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--spacing-2xs) var(--spacing-m);
}
.field-choice-grid label,
.check-field {
	display: flex;
	align-items: center;
	gap: var(--spacing-xs);
	min-height: 2.75rem;
}
.field-shell {
	display: grid;
	align-content: start;
	gap: var(--spacing-2xs);
	min-width: 0;
	color: var(--theme-text);
	font-size: var(--font-size--1);
	font-weight: var(--font-weight-medium);
}
.mapping-list {
	display: grid;
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	overflow: hidden;
}
.mapping-list article {
	display: grid;
	grid-template-columns: minmax(0, 1fr) minmax(12rem, auto);
	align-items: center;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	border-bottom: var(--border-width-1) solid var(--theme-border);
	background: var(--theme-surface-raised);
}
.mapping-list article:last-child {
	border-bottom: 0;
}
.mapping-list small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.price-table-wrap {
	max-width: 100%;
	overflow-x: auto;
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
}
.price-table {
	width: 100%;
	min-width: 72rem;
	border-collapse: collapse;
	background: var(--theme-surface-raised);
}
.price-table th,
.price-table td {
	padding: var(--spacing-xs) var(--spacing-s);
	border-bottom: var(--border-width-1) solid var(--theme-border);
	text-align: left;
	vertical-align: top;
}
.price-table th {
	background: var(--theme-secondary);
	color: var(--theme-text-muted);
	white-space: nowrap;
}
.empty-state {
	margin: 0;
	padding: var(--spacing-l);
	color: var(--theme-text-muted);
	text-align: center;
}
.catalogue-review,
.review-group,
.setup-review-list,
.offer-review-list {
	display: grid;
	gap: var(--spacing-s);
}
.review-group {
	padding: 0;
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface-raised);
	overflow: hidden;
}
.review-group-summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	padding: var(--spacing-s) var(--spacing-m);
	cursor: pointer;
	list-style: none;
}
.review-group-summary::-webkit-details-marker {
	display: none;
}
.review-group-summary > span:first-child {
	display: grid;
	gap: var(--spacing-3xs);
}
.review-group-summary small {
	color: var(--theme-text-muted);
	font-weight: var(--font-weight-regular);
}
.review-group-meta {
	display: flex;
	align-items: center;
	gap: var(--spacing-xs);
}
.review-group-chevron {
	font-size: var(--font-size-2);
	line-height: 1;
	transform: rotate(0deg);
	transition: transform 140ms ease;
}
.review-group[open] .review-group-chevron {
	transform: rotate(90deg);
}
.review-group > .setup-review-list,
.review-group > .offer-review-list {
	padding: 0 var(--spacing-s) var(--spacing-s);
}
.setup-review-list {
	grid-template-columns: repeat(2, minmax(0, 1fr));
}
.setup-review-card,
.offer-review-card {
	display: grid;
	gap: var(--spacing-s);
	min-width: 0;
	padding: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface-raised);
}
.review-card-heading {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: var(--spacing-s);
}
.review-card-heading small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.review-field-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	align-items: start;
	gap: var(--spacing-xs);
}
.review-field-grid--offer {
	grid-template-columns: repeat(4, minmax(0, 1fr));
}
.review-field-grid > .field-shell {
	align-self: start;
}
.review-reason,
.review-impact,
.review-errors {
	margin: 0;
	font-size: var(--font-size--1);
}
.review-reason,
.review-impact {
	color: var(--theme-text-muted);
}
.review-errors {
	padding: var(--spacing-xs);
	border-radius: var(--component-radius-field);
	background: var(--theme-error-soft, var(--theme-secondary));
	color: var(--theme-error, var(--theme-text));
}
.apply-boundary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-m);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-secondary);
}
.apply-boundary p {
	margin: var(--spacing-3xs) 0 0;
	color: var(--theme-text-muted);
}
.exchange-target {
	border-left: 3px solid var(--theme-primary);
}
.recipe-review {
	display: grid;
	gap: var(--spacing-s);
	padding: 0 var(--spacing-s) var(--spacing-s);
}
.review-subgroup {
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface);
	overflow: hidden;
}
.review-subgroup > summary {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	cursor: pointer;
}
.recipe-ingredient-list,
.recipe-instruction-list {
	display: grid;
	gap: var(--spacing-xs);
	padding: 0 var(--spacing-s) var(--spacing-s);
}
.recipe-ingredient-list article,
.recipe-instruction-list article {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	align-items: start;
	gap: var(--spacing-xs);
	padding: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-secondary);
}
.recipe-ingredient-list .review-errors,
.recipe-instruction-list .review-errors,
.recipe-instruction-list .check-field {
	grid-column: 1/-1;
}
@media (max-width: 1100px) {
	.review-field-grid--offer {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
}
@media (max-width: 700px) {
	.field-choice-grid,
	.setup-review-list,
	.review-field-grid,
	.review-field-grid--offer,
	.recipe-ingredient-list article,
	.recipe-instruction-list article {
		grid-template-columns: 1fr;
	}
	.mapping-list article {
		grid-template-columns: 1fr;
	}
	.apply-boundary {
		align-items: stretch;
		flex-direction: column;
	}
	.recipe-ingredient-list .review-errors,
	.recipe-instruction-list .review-errors,
	.recipe-instruction-list .check-field {
		grid-column: auto;
	}
}
</style>
