<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import {
	SystemBadge,
	SystemCheckboxShadcn,
	SystemDatePicker,
	SystemFileUploader,
	SystemFormControl,
	SystemLinkedRecordField,
	SystemMultiFileUploader,
	SystemOperationalButton,
	SystemSelect,
	SystemTabs,
	SystemTabsContent,
	SystemTabsList,
	SystemTabsTrigger,
	SystemTextarea,
} from "@/desyium";
import {
	applyPriceWorkbook,
	applySpreadsheetWorkspaceImport,
	createCostInvoice,
	getCostInvoiceExtractionStatus,
	getFinanceWorkspace,
	getPriceImportFields,
	getPriceImportImprovementStatus,
	getPurchasePriceHistory,
	inspectPriceFile,
	postCostInvoice,
	previewPriceWorkbook,
	priceWorkbookUrl,
	saveExpectedCostRule,
	saveMiscellaneousCost,
	savePriceAdjustment,
	startCostInvoiceExtraction,
	startPriceImportImprovement,
	financeLedgerWorkbookUrl,
	downloadAuthenticatedFile,
	reviewPriceWorkbook,
	getSpreadsheetWorkspaceContract,
	inspectSpreadsheetWorkspaceFile,
	previewSpreadsheetWorkspaceImport,
	reviewSpreadsheetWorkspaceImport,
	spreadsheetWorkspaceUrl,
} from "@/resources/api";

// =============================================================================
// region FINANCE AND PRICE CATALOGUE WORKSPACE
// =============================================================================

const props = defineProps({
	snapshot: { type: Object, default: null },
	inventory: { type: Object, default: null },
	mode: { type: String, default: "finance" },
});
const emit = defineEmits(["open-workflow", "changed"]);
const router = useRouter();
const today = () => new Date().toLocaleDateString("en-CA");

// region 1. SHARED STATE

const busy = ref(false);
const error = ref("");
const success = ref("");
const finance = ref(null);

function clearMessages() {
	error.value = "";
	success.value = "";
}
function openRecords(doctype, create = false) {
	router.push({
		name: create ? "AuxiliaryRecordCreate" : "BulkBiteSetupList",
		params: { doctype },
	});
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
function confidenceTheme(value) {
	return Number(value || 0) >= 85 ? "green" : Number(value || 0) >= 60 ? "orange" : "red";
}
async function downloadLedger() {
	if (!finance.value?.period) return;
	try {
		await downloadAuthenticatedFile(
			financeLedgerWorkbookUrl(finance.value.period.from_date, finance.value.period.to_date),
			"bulkbite-finance-ledger.xlsx",
		);
	} catch (exception) {
		error.value = exception.message;
	}
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

// region 1. FINANCE OVERVIEW

async function loadFinance() {
	busy.value = true;
	clearMessages();
	try {
		finance.value = await getFinanceWorkspace();
	} catch (exception) {
		error.value = exception.message;
	} finally {
		busy.value = false;
	}
}

async function refreshFinance(message) {
	await loadFinance();
	if (!error.value && message) success.value = message;
	emit("changed");
}

// endregion 1. FINANCE OVERVIEW

// region 1. EXPECTED COST RULES

const costCategories = [
	"Labour",
	"Packaging",
	"Delivery",
	"Utilities",
	"Rent",
	"Kitchen Consumables",
	"Transaction Fees",
	"Other Production Overhead",
];
const costCategoryOptions = costCategories.map((value) => ({ label: value, value }));
const invoiceTypeOptions = [
	"General Supplier Invoice",
	"Utilities",
	"Rent and Property",
	"Delivery and Logistics",
	"Professional Services",
	"Equipment and Maintenance",
	"Insurance and Compliance",
	"Marketing",
	"Telecoms and Software",
	"Other",
].map((value) => ({ label: value, value }));
const expectedCostCategoryOptions = costCategories
	.filter((value) => value !== "Labour")
	.map((value) => ({ label: value, value }));
const costBasisOptions = [
	"Fixed",
	"Hourly",
	"Per Meal",
	"Per Customer",
	"Per Kg",
	"Percentage of Revenue",
].map((value) => ({ label: value, value }));
const recurrenceOptions = ["Once", "Weekly", "Monthly", "Per Period"].map((value) => ({
	label: value,
	value,
}));
const vatOptions = ["Inclusive", "Exclusive", "No VAT"].map((value) => ({ label: value, value }));
const expectedSaving = ref(false);
const expectedCost = reactive(newExpectedCost());
const expectedPreview = computed(
	() => Number(expectedCost.default_quantity || 0) * Number(expectedCost.rate || 0),
);

function newExpectedCost() {
	return {
		name: "",
		cost_name: "",
		cost_category: "Utilities",
		basis: "Fixed",
		rate: 0,
		employee_count: 1,
		hours_per_employee: 0,
		default_quantity: 1,
		recurrence: "Monthly",
		effective_from: today(),
		effective_to: "",
		vat_treatment: "Inclusive",
		accounting_category: "",
		payee: "",
		enabled: 1,
		notes: "",
	};
}
function resetExpectedCost() {
	Object.assign(expectedCost, newExpectedCost());
}
function editExpectedCost(row) {
	Object.assign(expectedCost, newExpectedCost(), row);
	window.setTimeout(
		() =>
			document
				.querySelector("[data-finance-form='expected']")
				?.scrollIntoView({ behavior: "smooth", block: "start" }),
		0,
	);
}

async function submitExpectedCost() {
	expectedSaving.value = true;
	clearMessages();
	try {
		await saveExpectedCostRule({ ...expectedCost });
		resetExpectedCost();
		await refreshFinance("Expected cost saved.");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		expectedSaving.value = false;
	}
}

// endregion 1. EXPECTED COST RULES

// region 1. MISCELLANEOUS ACTUAL COST

const miscSaving = ref(false);
const miscFiles = ref([]);
const miscellaneousCost = reactive(newMiscellaneousCost());
const miscTotal = computed(
	() =>
		Number(miscellaneousCost.amount || 0) ||
		Number(miscellaneousCost.quantity || 0) * Number(miscellaneousCost.unit_rate || 0),
);
const costRuleOptions = computed(() =>
	(finance.value?.expected_costs || [])
		.filter((row) => row.enabled)
		.map((row) => ({
			label: row.cost_name,
			value: row.name,
			cost_category: row.cost_category,
			rate: row.rate,
		})),
);
const expenseTypeOptions = computed(() =>
	(finance.value?.expense_types || [])
		.filter((row) => row.enabled)
		.map((row) => ({ label: row.expense_type_name, value: row.name, ...row })),
);

function newMiscellaneousCost() {
	return {
		cost_date: today(),
		expense_type: "",
		cost_rule: "",
		cost_category: "Other Production Overhead",
		payee: "",
		quantity: 1,
		unit_rate: 0,
		amount: 0,
		vat_amount: 0,
		currency: "ZAR",
		accounting_category: "",
		notes: "",
	};
}
function changeMiscCostRule(value) {
	miscellaneousCost.cost_rule = value;
	const rule = costRuleOptions.value.find((option) => option.value === value);
	if (rule) {
		miscellaneousCost.cost_category = rule.cost_category;
		miscellaneousCost.unit_rate = Number(rule.rate || 0);
		miscellaneousCost.amount = 0;
	}
}
function changeMiscExpenseType(value) {
	miscellaneousCost.expense_type = value;
	const type = expenseTypeOptions.value.find((option) => option.value === value);
	if (type) {
		miscellaneousCost.cost_category = type.cost_category;
		miscellaneousCost.accounting_category = type.accounting_category || "";
	}
}
function resetMiscellaneousCost() {
	Object.assign(miscellaneousCost, newMiscellaneousCost());
	miscFiles.value = [];
}

async function submitMiscellaneousCost() {
	miscSaving.value = true;
	clearMessages();
	try {
		await saveMiscellaneousCost({
			...miscellaneousCost,
			amount: miscTotal.value,
			evidence_files: miscFiles.value.map((file) => ({
				evidence_file: file.file_url,
				file_name: file.file_name,
			})),
		});
		resetMiscellaneousCost();
		await refreshFinance("Actual cost added.");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		miscSaving.value = false;
	}
}

// endregion 1. MISCELLANEOUS ACTUAL COST

// region 1. PRICE ADJUSTMENTS

const adjustmentSaving = ref(false);
const adjustment = reactive(newAdjustment());
const adjustmentTypeOptions = [
	"Percentage Discount",
	"Fixed Discount",
	"Rebate",
	"Delivery Fee",
	"Free Delivery",
	"Minimum Order",
	"Service Fee",
	"VAT Adjustment",
	"Other Saving",
	"Other Cost",
].map((value) => ({ label: value, value }));
const scopeOptions = [
	"Global",
	"Supplier",
	"Item Category",
	"Item",
	"Supplier Offer",
	"Basket",
].map((value) => ({ label: value, value }));
const calculationOptions = ["Pack Price", "Basket Subtotal", "Fixed"].map((value) => ({
	label: value,
	value,
}));
const adjustmentVatOptions = ["As Configured", "Inclusive", "Exclusive", "No VAT"].map(
	(value) => ({ label: value, value }),
);
const adjustmentTarget = computed(
	() =>
		({
			Supplier: {
				field: "supplier",
				label: "Supplier",
				options: finance.value?.options?.suppliers || [],
				doctype: "BulkBite Supplier",
			},
			"Item Category": {
				field: "item_category",
				label: "Item category",
				options: finance.value?.options?.item_categories || [],
				doctype: "BulkBite Item Category",
			},
			Item: {
				field: "item_code",
				label: "Item",
				options: finance.value?.options?.items || [],
				doctype: "BulkBite Item",
			},
			"Supplier Offer": {
				field: "supplier_offer",
				label: "Supplier offer",
				options: finance.value?.options?.supplier_offers || [],
				doctype: "BulkBite Supplier Offer",
			},
		})[adjustment.scope_type] || null,
);

function newAdjustment() {
	return {
		name: "",
		adjustment_name: "",
		scope_type: "Global",
		supplier_offer: "",
		supplier: "",
		item_code: "",
		item_category: "",
		adjustment_type: "Percentage Discount",
		calculation_basis: "Pack Price",
		value: 0,
		threshold_amount: 0,
		effective_from: today(),
		effective_to: "",
		priority: 100,
		stackable: 1,
		vat_treatment: "As Configured",
		enabled: 1,
		notes: "",
	};
}
function resetAdjustment() {
	Object.assign(adjustment, newAdjustment());
}
function editAdjustment(row) {
	Object.assign(adjustment, newAdjustment(), row);
	window.setTimeout(
		() =>
			document
				.querySelector("[data-finance-form='adjustment']")
				?.scrollIntoView({ behavior: "smooth", block: "start" }),
		0,
	);
}
async function submitAdjustment() {
	adjustmentSaving.value = true;
	clearMessages();
	try {
		await savePriceAdjustment({ ...adjustment });
		resetAdjustment();
		await refreshFinance("Discount or buying cost saved.");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		adjustmentSaving.value = false;
	}
}

// endregion 1. PRICE ADJUSTMENTS

// region 1. COST INVOICE REVIEW

const invoiceFiles = ref([]);
const invoiceBusy = ref(false);
const invoiceSaved = ref(null);
const invoiceExtraction = ref(null);
const invoiceExtractionStage = ref("");
const showInvoiceOcr = ref(false);
const invoice = reactive(newInvoice());
const invoiceLines = reactive([newCostLine()]);
const invoiceTotal = computed(
	() =>
		invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0) +
		Number(invoice.tax_amount || 0),
);

function newInvoice() {
	return {
		document_type: "General Supplier Invoice",
		payee: "",
		invoice_number: "",
		invoice_date: today(),
		due_date: "",
		currency: "ZAR",
		tax_amount: 0,
		review_notes: "",
	};
}
function newCostLine() {
	return {
		description: "",
		expense_type: "",
		proposed_expense_type: "",
		create_expense_type: 0,
		cost_rule: "",
		cost_category: "Other Production Overhead",
		quantity: 1,
		unit_rate: 0,
		amount: 0,
		vat_amount: 0,
		accounting_category: "",
		confidence: 0,
		source_quote: "",
		uncertainty: "",
		notes: "",
	};
}
function updateCostAmount(row) {
	row.amount = Math.round(Number(row.quantity || 0) * Number(row.unit_rate || 0) * 100) / 100;
}
function changeCostRule(row, value) {
	row.cost_rule = value;
	const rule = costRuleOptions.value.find((option) => option.value === value);
	if (rule) {
		row.cost_category = rule.cost_category;
		row.unit_rate = Number(rule.rate || 0);
		updateCostAmount(row);
	}
}
function changeExpenseType(row, value) {
	row.expense_type = value;
	row.create_expense_type = 0;
	const type = expenseTypeOptions.value.find((option) => option.value === value);
	if (type) {
		row.cost_category = type.cost_category;
		row.accounting_category = type.accounting_category || "";
	}
}
function addCostLine() {
	if (!invoiceSaved.value) invoiceLines.push(newCostLine());
}
function removeCostLine(index) {
	if (!invoiceSaved.value && invoiceLines.length > 1) invoiceLines.splice(index, 1);
}
function resetInvoice() {
	invoiceFiles.value = [];
	invoiceSaved.value = null;
	invoiceExtraction.value = null;
	invoiceExtractionStage.value = "";
	showInvoiceOcr.value = false;
	Object.assign(invoice, newInvoice());
	invoiceLines.splice(0, invoiceLines.length, newCostLine());
}

async function extractCostInvoice(files) {
	invoiceBusy.value = true;
	clearMessages();
	try {
		const job = await startCostInvoiceExtraction(files.map((file) => file.file_url));
		const extracted = await waitForCostExtraction(job.job_id);
		invoiceExtraction.value = extracted;
		if (extracted.payee) invoice.payee = extracted.payee;
		if (extracted.supplier_invoice_number)
			invoice.invoice_number = extracted.supplier_invoice_number;
		if (extracted.invoice_date) invoice.invoice_date = extracted.invoice_date;
		if (extracted.due_date) invoice.due_date = extracted.due_date;
		if (extracted.document_type) invoice.document_type = extracted.document_type;
		if (extracted.currency) invoice.currency = extracted.currency;
		if (extracted.tax_amount !== null && extracted.tax_amount !== undefined)
			invoice.tax_amount = Number(extracted.tax_amount);
		const rows = (extracted.cost_lines || []).map((row) => ({ ...newCostLine(), ...row }));
		invoiceLines.splice(0, invoiceLines.length, ...(rows.length ? rows : [newCostLine()]));
	} catch (exception) {
		error.value = exception.message;
	} finally {
		invoiceBusy.value = false;
	}
}

async function waitForCostExtraction(jobId) {
	const deadline = Date.now() + 10 * 60 * 1000;
	while (Date.now() < deadline) {
		const state = await getCostInvoiceExtractionStatus(jobId);
		invoiceExtractionStage.value = state.stage || state.status;
		if (state.status === "finished") return state.result;
		if (state.status === "failed")
			throw new Error(state.error || "Invoice extraction failed.");
		await new Promise((resolve) => window.setTimeout(resolve, 1500));
	}
	throw new Error("Invoice extraction took too long. Try again or enter the costs manually.");
}

async function saveCostInvoice() {
	if (
		!invoiceFiles.value.length ||
		!invoice.payee ||
		!invoice.invoice_date ||
		!invoiceLines.length
	)
		return (error.value =
			"Add invoice evidence, a payee, a date, and at least one cost line.");
	const unresolved = invoiceLines.find(
		(row) => !row.expense_type && !(row.create_expense_type && row.proposed_expense_type),
	);
	if (unresolved)
		return (error.value = `Choose an expense type for ${unresolved.description || "each invoice line"}, or approve its proposed new type.`);
	invoiceBusy.value = true;
	clearMessages();
	try {
		invoiceSaved.value = await createCostInvoice({
			...invoice,
			evidence_files: invoiceFiles.value.map((file) => ({
				evidence_file: file.file_url,
				file_name: file.file_name,
			})),
			costs: invoiceLines.map((row) => ({ ...row, document_type: invoice.document_type })),
			subtotal_amount: invoiceLines.reduce((sum, row) => sum + Number(row.amount || 0), 0),
			total_amount: invoiceTotal.value,
			status: "Reviewed",
		});
		emit("changed");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		invoiceBusy.value = false;
	}
}

async function postInvoice() {
	invoiceBusy.value = true;
	clearMessages();
	try {
		invoiceSaved.value = await postCostInvoice(invoiceSaved.value.name);
		await refreshFinance("The reviewed invoice was added to actual operating costs.");
	} catch (exception) {
		error.value = exception.message;
	} finally {
		invoiceBusy.value = false;
	}
}

// endregion 1. COST INVOICE REVIEW

onMounted(() => (props.mode === "finance" ? loadFinance() : loadCatalogue()));

// endregion FINANCE AND PRICE CATALOGUE WORKSPACE
</script>

<template>
	<section
		data-block="price-history"
		class="workflow-block"
		:class="{ 'finance-workflow': mode === 'finance' }"
	>
		<header class="workflow-header">
			<div>
				<p class="eyebrow">
					{{
						mode === "import"
							? "Data import"
							: mode === "catalogue"
								? "Stock setup"
								: "Finance"
					}}
				</p>
				<h1>
					{{
						mode === "import"
							? "Import and export"
							: mode === "catalogue"
								? "Price catalogue"
								: "Costs and finances"
					}}
				</h1>
				<p>
					{{
						mode === "import"
							? "Bring reviewed stock, recipe, and setup records into BulkBite through one controlled spreadsheet flow."
							: mode === "catalogue"
								? "Maintain the supplier prices used to calculate what stock should cost."
								: "Plan employee and operating costs, record what was paid, and track discounts in one place."
					}}
				</p>
			</div>
			<SystemBadge>{{
				mode === "import"
					? "Reviewed writes only"
					: mode === "catalogue"
						? "Does not change stock"
						: "Cost control"
			}}</SystemBadge>
		</header>
		<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
		<div v-if="success" class="state-message" role="status">{{ success }}</div>

		<template v-if="mode !== 'finance'">
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
		</template>

		<SystemTabs v-else default-value="overview" class="finance-tabs">
			<SystemTabsList class="finance-tabs__list"
				><SystemTabsTrigger value="overview">Overview</SystemTabsTrigger
				><SystemTabsTrigger value="expected">Expected costs</SystemTabsTrigger
				><SystemTabsTrigger value="actual">Actual costs</SystemTabsTrigger
				><SystemTabsTrigger value="discounts">Discounts</SystemTabsTrigger
				><SystemTabsTrigger value="history">History</SystemTabsTrigger
				><SystemTabsTrigger value="ledger">Ledger</SystemTabsTrigger></SystemTabsList
			>

			<SystemTabsContent value="overview" class="finance-tabs__content">
				<section class="finance-overview">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Theoretical forecast</p>
							<h2>What the current direction should earn and cost</h2>
							<p>
								Revenue uses configured customer-plan prices. Costs use the planned
								food basket, labour, delivery, packaging, and recurring rules for
								this month.
							</p>
						</div>
						<SystemBadge
							:theme="
								Number(finance?.forecast?.operating_profit || 0) >= 0
									? 'green'
									: 'red'
							"
							>{{ Number(finance?.forecast?.margin_percent || 0).toFixed(1) }}%
							margin</SystemBadge
						>
					</div>
					<div class="finance-metrics finance-metrics--forecast">
						<article>
							<span>Expected revenue</span
							><strong>{{ money(finance?.forecast?.revenue) }}</strong
							><small>Current customer plans</small>
						</article>
						<article>
							<span>Expected food cost</span
							><strong>{{ money(finance?.forecast?.food_cost) }}</strong
							><small>Recipe ingredients expected to be used</small>
						</article>
						<article>
							<span>Expected operating costs</span
							><strong>{{ money(finance?.forecast?.operating_cost) }}</strong
							><small>Labour and recurring costs</small>
						</article>
						<article>
							<span>Expected operating profit</span
							><strong>{{ money(finance?.forecast?.operating_profit) }}</strong
							><small>Revenue less food and operating costs</small>
						</article>
						<article>
							<span>Expected savings</span
							><strong>{{ money(finance?.forecast?.discounts_and_savings) }}</strong
							><small>Discounts, rebates, and avoided delivery</small>
						</article>
						<article>
							<span>Added buying costs</span
							><strong>{{ money(finance?.forecast?.added_buying_costs) }}</strong
							><small>Delivery, VAT additions, and fees</small>
						</article>
						<article>
							<span>Purchase spend</span
							><strong>{{ money(finance?.forecast?.purchase_spend) }}</strong
							><small>Reviewed receipts this month</small>
						</article>
						<article>
							<span>Actual operating result</span
							><strong>{{
								finance?.forecast?.actual_complete
									? money(finance?.forecast?.actual_operating_result)
									: "Incomplete"
							}}</strong
							><small>{{ finance?.forecast?.actual_qualification }}</small>
						</article>
					</div>
				</section>
				<section class="finance-overview">
					<div class="section-heading">
						<div>
							<p class="eyebrow">This month</p>
							<h2>Operating cost position</h2>
							<p v-if="finance">
								{{ finance.period.from_date }} to {{ finance.period.to_date }}
							</p>
						</div>
						<SystemOperationalButton
							variant="solid"
							@click="emit('open-workflow', 'export')"
							>Open Reports</SystemOperationalButton
						>
					</div>
					<div class="finance-metrics">
						<article>
							<span>Expected operating costs</span
							><strong>{{ money(finance?.summary?.expected_total) }}</strong
							><small>Employee and recurring rules</small>
						</article>
						<article>
							<span>Actual operating costs</span
							><strong>{{ money(finance?.summary?.actual_total) }}</strong
							><small>Posted invoices and direct costs</small>
						</article>
						<article>
							<span>Cost variance</span
							><strong>{{ money(finance?.summary?.variance) }}</strong
							><small>Actual less expected</small>
						</article>
						<article>
							<span>Expected savings</span
							><strong>{{ money(finance?.summary?.expected_savings) }}</strong
							><small
								>{{ finance?.summary?.active_adjustments || 0 }} active
								rules</small
							>
						</article>
					</div>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Where money is going</p>
							<h2>Cost categories</h2>
							<p>Expected and actual operating costs for the current month.</p>
						</div>
					</div>
					<div class="category-list">
						<article v-for="row in finance?.breakdown || []" :key="row.category">
							<strong>{{ row.category }}</strong
							><span>{{ money(row.expected) }} expected</span
							><span>{{ money(row.actual) }} actual</span
							><SystemBadge :theme="Number(row.variance) <= 0 ? 'green' : 'orange'"
								>{{ money(row.variance) }} variance</SystemBadge
							>
						</article>
						<p v-if="!finance?.breakdown?.length" class="empty-state">
							Add an expected cost or an actual cost to start the comparison.
						</p>
					</div>
				</section>
			</SystemTabsContent>

			<SystemTabsContent value="expected" class="finance-tabs__content">
				<section class="finance-workforce">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Employee capacity and cost</p>
							<h2>Expected workforce</h2>
							<p>
								Employee types and profiles are managed under Production. Finance
								shows the capacity and labour effect.
							</p>
						</div>
						<SystemOperationalButton
							variant="outline"
							@click="emit('open-workflow', 'employees')"
							>Manage employees</SystemOperationalButton
						>
					</div>
					<div class="category-list">
						<article v-for="row in finance?.workforce?.rows || []" :key="row.name">
							<strong>{{ row.employee_type_name }}</strong
							><span
								>{{ row.required_workers }} needed /
								{{ row.active_workers }} active</span
							><span>{{ money(row.expected_monthly_cost) }} expected</span
							><SystemBadge
								:theme="
									row.status === 'Under capacity'
										? 'orange'
										: row.status === 'At capacity'
											? 'green'
											: undefined
								"
								>{{ row.status }}</SystemBadge
							>
						</article>
						<p v-if="!finance?.workforce?.rows?.length" class="empty-state">
							Add employee types under Production to calculate workforce capacity and
							expected labour.
						</p>
					</div>
				</section>
				<section class="form-section" data-finance-form="expected">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Other expected costs</p>
							<h2>
								{{
									expectedCost.name
										? "Edit expected cost"
										: "Add an expected cost"
								}}
							</h2>
							<p>
								Add power, rent, utilities, packaging, delivery, and other
								configurable operating costs here.
							</p>
						</div>
						<SystemBadge v-if="expectedCost.name">Editing</SystemBadge>
					</div>
					<div class="field-grid field-grid--wide">
						<SystemFormControl
							v-model="expectedCost.cost_name"
							label="Cost type"
							placeholder="Kitchen electricity"
						/><SystemSelect
							v-model="expectedCost.cost_category"
							label="Cost category"
							:options="expectedCostCategoryOptions"
						/><SystemSelect
							v-model="expectedCost.basis"
							label="How it is calculated"
							:options="costBasisOptions"
						/><SystemFormControl
							v-model="expectedCost.rate"
							label="Rate (R)"
							type="number"
							step="0.1"
						/>
					</div>
					<div class="field-grid">
						<SystemFormControl
							v-model="expectedCost.default_quantity"
							label="Expected quantity"
							type="number"
							step="0.1"
						/>
						<div class="calculated-field">
							<span>Cost at expected quantity</span
							><strong>{{ money(expectedPreview) }}</strong
							><small
								>{{ quantity(expectedCost.default_quantity) }} ×
								{{ money(expectedCost.rate) }}</small
							>
						</div>
					</div>
					<div class="field-grid">
						<SystemSelect
							v-model="expectedCost.recurrence"
							label="Repeats"
							:options="recurrenceOptions"
						/><SystemDatePicker
							v-model="expectedCost.effective_from"
							label="Effective from"
							format="YYYY-MM-DD"
						/><SystemDatePicker
							v-model="expectedCost.effective_to"
							label="Effective to"
							format="YYYY-MM-DD"
						/><SystemFormControl
							v-model="expectedCost.payee"
							label="Usual employee or payee"
						/><SystemSelect
							v-model="expectedCost.vat_treatment"
							label="VAT treatment"
							:options="vatOptions"
						/><SystemFormControl v-model="expectedCost.notes" label="Notes" />
					</div>
					<label class="check-field"
						><SystemCheckboxShadcn v-model="expectedCost.enabled" /><span
							>Include this cost in planning</span
						></label
					>
					<div class="button-row">
						<SystemOperationalButton
							v-if="expectedCost.name"
							variant="outline"
							@click="resetExpectedCost"
							>Cancel edit</SystemOperationalButton
						><SystemOperationalButton
							variant="solid"
							:loading="expectedSaving"
							@click="submitExpectedCost"
							>{{
								expectedCost.name ? "Save changes" : "Add expected cost"
							}}</SystemOperationalButton
						>
					</div>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Current cost model</p>
							<h2>Recurring and miscellaneous costs</h2>
							<p>
								The period value uses the current month's dates and production
								drivers.
							</p>
						</div>
					</div>
					<div class="record-list">
						<article v-for="row in finance?.expected_costs || []" :key="row.name">
							<div>
								<strong>{{ row.cost_name }}</strong
								><small
									>{{ row.cost_category }} · {{ row.basis }} ·
									{{ row.recurrence }}</small
								><small
									>{{ quantity(row.default_quantity) }} expected ·
									{{ money(row.rate) }} rate</small
								>
							</div>
							<div>
								<b>{{ money(row.period_amount) }}</b
								><SystemBadge :theme="row.enabled ? 'green' : undefined">{{
									row.enabled ? "Active" : "Disabled"
								}}</SystemBadge
								><SystemOperationalButton
									variant="outline"
									@click="editExpectedCost(row)"
									>Edit</SystemOperationalButton
								>
							</div>
						</article>
						<p v-if="!finance?.expected_costs?.length" class="empty-state">
							No recurring or miscellaneous costs have been set.
						</p>
					</div>
				</section>
			</SystemTabsContent>

			<SystemTabsContent value="actual" class="finance-tabs__content">
				<section class="form-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Quick actual cost</p>
							<h2>Add a miscellaneous expense</h2>
							<p>Record one actual operating expense without an invoice workflow.</p>
						</div>
						<strong>{{ money(miscTotal) }}</strong>
					</div>
					<div class="field-grid">
						<SystemDatePicker
							v-model="miscellaneousCost.cost_date"
							label="Expense date"
							format="YYYY-MM-DD"
						/><SystemLinkedRecordField
							:model-value="miscellaneousCost.expense_type"
							label="Expense type"
							:options="expenseTypeOptions"
							@update:model-value="changeMiscExpenseType"
							@create="openRecords('BulkBite Expense Type', true)"
							@manage="openRecords('BulkBite Expense Type')"
						/><label class="field-shell"
							><span>Expected cost match</span
							><SystemSelect
								:model-value="miscellaneousCost.cost_rule"
								:options="costRuleOptions"
								placeholder="No expected match"
								@update:model-value="changeMiscCostRule" /></label
						><SystemFormControl
							v-model="miscellaneousCost.payee"
							label="Supplier or payee"
						/>
					</div>
					<div class="field-grid">
						<SystemFormControl
							v-model="miscellaneousCost.quantity"
							label="Quantity"
							type="number"
							step="0.1"
						/><SystemFormControl
							v-model="miscellaneousCost.unit_rate"
							label="Rate (R)"
							type="number"
							step="0.1"
						/><SystemFormControl
							v-model="miscellaneousCost.amount"
							label="Actual cost (R)"
							type="number"
							step="0.1"
							description="Leave at 0 to calculate quantity × rate."
						/><SystemFormControl
							v-model="miscellaneousCost.vat_amount"
							label="VAT included (R)"
							type="number"
							step="0.1"
						/><SystemFormControl v-model="miscellaneousCost.notes" label="Notes" />
					</div>
					<SystemMultiFileUploader v-model="miscFiles" label="Add expense evidence" />
					<div class="button-row">
						<SystemOperationalButton
							variant="solid"
							:loading="miscSaving"
							@click="submitMiscellaneousCost"
							>Post actual expense</SystemOperationalButton
						>
					</div>
				</section>
				<section class="form-section invoice-workflow">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Invoice to actual expenses</p>
							<h2>Upload, review, then post</h2>
							<p>
								Add all invoice pages together. The AI fills a review draft and
								never posts money without your approval.
							</p>
						</div>
						<div class="button-row">
							<SystemBadge
								v-if="invoiceSaved"
								:theme="invoiceSaved.costs_posted ? 'green' : undefined"
								>{{ invoiceSaved.status }}</SystemBadge
							><SystemOperationalButton
								v-if="invoiceSaved?.costs_posted"
								variant="outline"
								@click="resetInvoice"
								>Process another invoice</SystemOperationalButton
							>
						</div>
					</div>
					<div class="invoice-stage">
						<div>
							<strong>1. Evidence and extraction</strong
							><small>Private files are read in a background job.</small>
						</div>
						<SystemMultiFileUploader
							v-model="invoiceFiles"
							:disabled="Boolean(invoiceSaved)"
							label="Add invoice files"
							@complete="extractCostInvoice"
						/>
					</div>
					<p v-if="invoiceBusy" class="field-note" role="status">
						{{
							invoiceExtractionStage
								? `Invoice processing: ${invoiceExtractionStage.replaceAll("_", " ")}`
								: "Reading invoice files and suggesting expenses..."
						}}
					</p>
					<div v-if="invoiceExtraction" class="safety-note">
						<div class="extraction-summary">
							<div>
								<strong>{{
									invoiceExtraction.parser_mode || "Invoice extraction"
								}}</strong>
								<p>
									{{ invoiceExtraction.cost_lines?.length || 0 }} expense lines
									suggested at
									{{
										Math.round(
											Number(invoiceExtraction.confidence || 0) * 100,
										)
									}}% document confidence.
								</p>
							</div>
							<SystemOperationalButton
								variant="outline"
								@click="showInvoiceOcr = !showInvoiceOcr"
								>{{
									showInvoiceOcr ? "Hide OCR text" : "Show OCR text"
								}}</SystemOperationalButton
							>
						</div>
						<p v-for="warning in invoiceExtraction.warnings || []" :key="warning">
							{{ warning }}
						</p>
						<pre v-if="showInvoiceOcr" class="invoice-ocr">{{
							invoiceExtraction.ocr_text || "No text was extracted."
						}}</pre>
					</div>
					<div class="invoice-stage">
						<div>
							<strong>2. Invoice details</strong
							><small
								>Confirm the document facts before reviewing its expense
								lines.</small
							>
						</div>
					</div>
					<div class="field-grid">
						<label class="field-shell"
							><span>Invoice type</span
							><SystemSelect
								v-model="invoice.document_type"
								:options="invoiceTypeOptions"
								:disabled="Boolean(invoiceSaved)" /></label
						><SystemFormControl
							v-model="invoice.payee"
							label="Supplier or payee"
							:disabled="Boolean(invoiceSaved)"
						/><SystemFormControl
							v-model="invoice.invoice_number"
							label="Invoice or reference number"
							:disabled="Boolean(invoiceSaved)"
						/><SystemDatePicker
							v-model="invoice.invoice_date"
							label="Invoice date"
							format="YYYY-MM-DD"
							:disabled="Boolean(invoiceSaved)"
						/><SystemDatePicker
							v-model="invoice.due_date"
							label="Due date"
							format="YYYY-MM-DD"
							:disabled="Boolean(invoiceSaved)"
						/><SystemFormControl
							v-model="invoice.tax_amount"
							label="Document VAT (R)"
							type="number"
							step="0.1"
							:disabled="Boolean(invoiceSaved)"
						/>
					</div>
					<div class="invoice-stage">
						<div>
							<strong>3. Review actual expenses</strong
							><small
								>Each approved line becomes one miscellaneous actual expense and
								one immutable ledger event.</small
							>
						</div>
					</div>
					<div class="cost-line-list">
						<article v-for="(row, index) in invoiceLines" :key="index">
							<div class="cost-line-heading">
								<strong>Expense {{ index + 1 }}</strong
								><SystemOperationalButton
									v-if="!invoiceSaved && invoiceLines.length > 1"
									variant="ghost"
									@click="removeCostLine(index)"
									>Remove</SystemOperationalButton
								>
							</div>
							<SystemFormControl
								v-model="row.description"
								label="Expense description"
								:disabled="Boolean(invoiceSaved)"
							/><SystemLinkedRecordField
								:model-value="row.expense_type"
								label="Expense type"
								:options="expenseTypeOptions"
								:disabled="Boolean(invoiceSaved)"
								@update:model-value="changeExpenseType(row, $event)"
								@create="openRecords('BulkBite Expense Type', true)"
								@manage="openRecords('BulkBite Expense Type')"
							/><label class="field-shell"
								><span>Expected cost match</span
								><SystemSelect
									:model-value="row.cost_rule"
									:options="costRuleOptions"
									placeholder="No expected match"
									:disabled="Boolean(invoiceSaved)"
									@update:model-value="changeCostRule(row, $event)" /></label
							><SystemFormControl
								v-model="row.quantity"
								label="Quantity"
								type="number"
								step="0.1"
								:disabled="Boolean(invoiceSaved)"
								@update:model-value="updateCostAmount(row)"
							/><SystemFormControl
								v-model="row.unit_rate"
								label="Rate (R)"
								type="number"
								step="0.1"
								:disabled="Boolean(invoiceSaved)"
								@update:model-value="updateCostAmount(row)"
							/><SystemFormControl
								v-model="row.amount"
								label="Expense before document VAT (R)"
								type="number"
								step="0.1"
								:disabled="Boolean(invoiceSaved)"
							/>
							<div
								v-if="!row.expense_type && row.proposed_expense_type"
								class="expense-type-proposal"
							>
								<label class="check-field"
									><SystemCheckboxShadcn
										v-model="row.create_expense_type"
										:disabled="
											Boolean(invoiceSaved) ||
											!finance?.can_create_expense_types
										"
									/><span
										>Create expense type "{{ row.proposed_expense_type }}" when
										I save this reviewed invoice</span
									></label
								>
							</div>
							<div
								v-if="
									row.source_quote ||
									row.notes ||
									row.uncertainty ||
									row.confidence
								"
								class="cost-line-review"
							>
								<SystemBadge :theme="confidenceTheme(row.confidence)"
									>{{ Math.round(Number(row.confidence || 0)) }}%
									confidence</SystemBadge
								>
								<p v-if="row.source_quote">
									<strong>OCR:</strong> {{ row.source_quote }}
								</p>
								<p v-if="row.uncertainty">
									<strong>Check:</strong> {{ row.uncertainty }}
								</p>
								<p v-if="row.notes">{{ row.notes }}</p>
							</div>
						</article>
					</div>
					<div class="invoice-posting">
						<div>
							<span>Reviewed invoice total</span
							><strong>{{ money(invoiceTotal) }}</strong
							><small>{{ money(invoice.tax_amount) }} document VAT included</small>
						</div>
						<div class="button-row">
							<SystemOperationalButton
								variant="outline"
								:disabled="Boolean(invoiceSaved)"
								@click="addCostLine"
								>Add expense line</SystemOperationalButton
							><SystemOperationalButton
								v-if="!invoiceSaved"
								variant="solid"
								:loading="invoiceBusy"
								@click="saveCostInvoice"
								>Save reviewed invoice</SystemOperationalButton
							><SystemOperationalButton
								v-else-if="!invoiceSaved.costs_posted"
								variant="solid"
								:loading="invoiceBusy"
								@click="postInvoice"
								>Post actual expenses</SystemOperationalButton
							>
						</div>
					</div>
				</section>
			</SystemTabsContent>

			<SystemTabsContent value="discounts" class="finance-tabs__content">
				<section class="form-section" data-finance-form="adjustment">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Discounts and buying costs</p>
							<h2>
								{{
									adjustment.name
										? "Edit discount or cost"
										: "Add a discount or cost"
								}}
							</h2>
							<p>
								Model discounts, rebates, free delivery, fees, VAT changes, and
								other savings or costs.
							</p>
						</div>
						<SystemBadge v-if="adjustment.name">Editing</SystemBadge>
					</div>
					<div class="field-grid">
						<SystemFormControl
							v-model="adjustment.adjustment_name"
							label="Discount or cost name"
						/><SystemSelect
							v-model="adjustment.adjustment_type"
							label="Type"
							:options="adjustmentTypeOptions"
						/><SystemSelect
							v-model="adjustment.scope_type"
							label="Applies to"
							:options="scopeOptions"
						/><SystemLinkedRecordField
							v-if="adjustmentTarget"
							v-model="adjustment[adjustmentTarget.field]"
							:label="adjustmentTarget.label"
							:options="adjustmentTarget.options"
							@create="openRecords(adjustmentTarget.doctype, true)"
							@manage="openRecords(adjustmentTarget.doctype)"
						/>
					</div>
					<div class="field-grid">
						<SystemSelect
							v-model="adjustment.calculation_basis"
							label="Calculation basis"
							:options="calculationOptions"
						/><SystemFormControl
							v-model="adjustment.value"
							label="Rate or amount"
							type="number"
							step="0.1"
						/><SystemFormControl
							v-model="adjustment.threshold_amount"
							label="Minimum basket amount"
							type="number"
							step="0.1"
						/><SystemFormControl
							v-model="adjustment.priority"
							label="Priority"
							type="number"
							step="1"
						/><SystemDatePicker
							v-model="adjustment.effective_from"
							label="Effective from"
							format="YYYY-MM-DD"
						/><SystemDatePicker
							v-model="adjustment.effective_to"
							label="Effective to"
							format="YYYY-MM-DD"
						/><SystemSelect
							v-model="adjustment.vat_treatment"
							label="VAT treatment"
							:options="adjustmentVatOptions"
						/><SystemFormControl v-model="adjustment.notes" label="Notes or source" />
					</div>
					<div class="check-row">
						<label class="check-field"
							><SystemCheckboxShadcn v-model="adjustment.stackable" /><span
								>Can combine with other discounts</span
							></label
						><label class="check-field"
							><SystemCheckboxShadcn v-model="adjustment.enabled" /><span
								>Use this rule in planning</span
							></label
						>
					</div>
					<div class="button-row">
						<SystemOperationalButton
							v-if="adjustment.name"
							variant="outline"
							@click="resetAdjustment"
							>Cancel edit</SystemOperationalButton
						><SystemOperationalButton
							variant="solid"
							:loading="adjustmentSaving"
							@click="submitAdjustment"
							>{{
								adjustment.name ? "Save changes" : "Add discount or cost"
							}}</SystemOperationalButton
						>
					</div>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Current rules</p>
							<h2>Discounts, savings, and added costs</h2>
							<p>
								These rules feed theoretical buying costs and the saving analysis
								in Reports.
							</p>
						</div>
					</div>
					<div class="record-list">
						<article v-for="row in finance?.adjustments || []" :key="row.name">
							<div>
								<strong>{{ row.adjustment_name }}</strong
								><small
									>{{ row.adjustment_type }} · {{ row.scope_type }} ·
									{{ row.calculation_basis }}</small
								><small
									>{{ row.effective_from
									}}{{
										row.effective_to ? ` to ${row.effective_to}` : ""
									}}</small
								>
							</div>
							<div>
								<b>{{ money(row.value) }}</b
								><SystemBadge :theme="row.enabled ? 'green' : undefined">{{
									row.enabled ? "Active" : "Disabled"
								}}</SystemBadge
								><SystemOperationalButton
									variant="outline"
									@click="editAdjustment(row)"
									>Edit</SystemOperationalButton
								>
							</div>
						</article>
						<p v-if="!finance?.adjustments?.length" class="empty-state">
							No discount or buying-cost rules have been set.
						</p>
					</div>
				</section>
			</SystemTabsContent>

			<SystemTabsContent value="history" class="finance-tabs__content">
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Cost evidence</p>
							<h2>Recent cost invoices</h2>
							<p>
								Each row shows the reviewed document and whether it created actual
								cost entries.
							</p>
						</div>
					</div>
					<div class="history-list">
						<article
							v-for="row in snapshot?.recent_cost_invoices || []"
							:key="row.name"
						>
							<div>
								<strong>{{ row.payee }}</strong
								><small
									>{{ row.invoice_date }} ·
									{{ row.invoice_number || row.name }}</small
								><small
									>{{ row.line_count || 0 }} cost lines ·
									{{ row.cost_categories || "Uncategorised" }}</small
								>
							</div>
							<div>
								<b>{{ money(row.total_amount) }}</b
								><SystemBadge :theme="row.costs_posted ? 'green' : undefined">{{
									row.costs_posted
										? `${row.posted_entry_count || row.line_count || 0} actual costs created`
										: row.status
								}}</SystemBadge>
							</div>
						</article>
						<p v-if="!snapshot?.recent_cost_invoices?.length" class="empty-state">
							No cost invoices have been recorded.
						</p>
					</div>
				</section>
			</SystemTabsContent>

			<SystemTabsContent value="ledger" class="finance-tabs__content">
				<section class="finance-overview">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Immutable finance ledger</p>
							<h2>Accountant evidence chain</h2>
							<p>
								Every posted expense is hash-linked to the event before it.
								Corrections are new entries, never edits to history.
							</p>
						</div>
						<SystemBadge
							:theme="
								finance?.finance_ledger?.summary?.chain?.valid ? 'green' : 'red'
							"
							>{{
								finance?.finance_ledger?.summary?.chain?.valid
									? "Chain verified"
									: "Chain needs attention"
							}}</SystemBadge
						>
					</div>
					<div class="finance-metrics">
						<article>
							<span>Ledger entries</span
							><strong>{{
								finance?.finance_ledger?.summary?.entry_count || 0
							}}</strong
							><small
								>{{ finance?.finance_ledger?.summary?.chain?.checked || 0 }} hashes
								checked</small
							>
						</article>
						<article>
							<span>Gross expenses</span
							><strong>{{
								money(finance?.finance_ledger?.summary?.total_amount)
							}}</strong
							><small>Includes entered VAT</small>
						</article>
						<article>
							<span>VAT evidence</span
							><strong>{{
								money(finance?.finance_ledger?.summary?.vat_amount)
							}}</strong
							><small>From posted evidence</small>
						</article>
						<article>
							<span>Net before VAT</span
							><strong>{{
								money(finance?.finance_ledger?.summary?.net_amount)
							}}</strong
							><small>Accountant view</small>
						</article>
					</div>
				</section>
				<section class="data-section">
					<div class="section-heading">
						<div>
							<p class="eyebrow">Ledger</p>
							<h2>Chronological finance events</h2>
							<p>
								Invoice expenses, direct expenses, and posted labour costs appear
								in one verified trail.
							</p>
						</div>
						<SystemOperationalButton variant="solid" @click="downloadLedger"
							>Download ledger Excel</SystemOperationalButton
						>
					</div>
					<div class="price-table-wrap">
						<table class="price-table ledger-table">
							<thead>
								<tr>
									<th>Sequence</th>
									<th>Posting date</th>
									<th>Event</th>
									<th>Payee</th>
									<th>Category</th>
									<th>Gross</th>
									<th>VAT</th>
									<th>Reference</th>
									<th>Evidence</th>
									<th>Hash</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="row in finance?.finance_ledger?.rows || []"
									:key="row.event_sequence"
								>
									<td>#{{ row.event_sequence }}</td>
									<td>{{ row.posting_date }}</td>
									<td>{{ row.event_type }}</td>
									<td>{{ row.payee || "Not recorded" }}</td>
									<td>{{ row.expense_type || row.cost_category }}</td>
									<td>{{ money(row.amount) }}</td>
									<td>{{ money(row.vat_amount) }}</td>
									<td>{{ row.reference_doctype }} · {{ row.reference_name }}</td>
									<td>{{ row.evidence_file ? "Attached" : "None" }}</td>
									<td>
										<code>{{ row.event_hash.slice(0, 12) }}…</code>
									</td>
								</tr>
								<tr v-if="!finance?.finance_ledger?.rows?.length">
									<td colspan="10">
										No finance ledger events fall in this period.
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			</SystemTabsContent>
		</SystemTabs>
	</section>
</template>

<style scoped>
.finance-workflow {
	padding-top: var(--spacing-m);
	padding-bottom: var(--spacing-l);
}
.finance-workforce {
	display: grid;
	gap: var(--spacing-s);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-block);
	background: var(--theme-surface);
}
.invoice-workflow,
.invoice-stage,
.invoice-posting {
	display: grid;
	gap: var(--spacing-s);
}
.invoice-stage {
	grid-template-columns: minmax(0, 1fr) auto;
	align-items: center;
	padding: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-secondary);
}
.invoice-stage small,
.invoice-posting small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.invoice-posting {
	grid-template-columns: minmax(0, 1fr) auto;
	align-items: center;
	padding-top: var(--spacing-s);
	border-top: var(--border-width-1) solid var(--theme-border);
}
.invoice-posting > div:first-child {
	display: grid;
	gap: var(--spacing-3xs);
}
.invoice-posting strong {
	font-size: var(--font-size-2);
}
.cost-line-heading {
	grid-column: 1/-1;
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--spacing-s);
}
.expense-type-proposal {
	grid-column: 1/-1;
	padding: var(--spacing-xs) var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-field);
	background: var(--theme-secondary);
}
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
.mapping-list,
.review-list,
.history-list,
.record-list,
.category-list {
	display: grid;
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	overflow: hidden;
}
.mapping-list article,
.review-list article,
.history-list article,
.record-list article,
.category-list article {
	display: grid;
	grid-template-columns: minmax(0, 1fr) minmax(12rem, auto);
	align-items: center;
	gap: var(--spacing-s);
	padding: var(--spacing-s);
	border-bottom: var(--border-width-1) solid var(--theme-border);
	background: var(--theme-surface-raised);
}
.mapping-list article:last-child,
.review-list article:last-child,
.history-list article:last-child,
.record-list article:last-child,
.category-list article:last-child {
	border-bottom: 0;
}
.mapping-list small,
.review-list small,
.history-list small,
.record-list small {
	display: block;
	margin-top: var(--spacing-3xs);
	color: var(--theme-text-muted);
}
.review-list article {
	grid-template-columns: minmax(0, 1fr) auto;
}
.review-list p {
	grid-column: 1/-1;
	margin: 0;
	color: var(--theme-text-muted);
}
.finance-tabs {
	display: grid;
	gap: var(--spacing-xs);
}
.finance-tabs__list {
	justify-content: flex-start !important;
	width: fit-content;
	max-width: 100%;
	overflow-x: auto;
}
.finance-tabs__list :deep([role="tab"]) {
	min-height: 2.75rem;
}
.finance-tabs__content {
	display: grid;
	gap: var(--spacing-xs);
	margin-top: 0 !important;
	outline: none;
}
.finance-tabs__content > :first-child {
	margin-top: 0;
}
.finance-overview {
	display: grid;
	gap: var(--spacing-s);
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-block);
	background: var(--theme-surface-raised);
}
.finance-metrics {
	display: grid;
	grid-template-columns: repeat(4, minmax(0, 1fr));
	gap: var(--spacing-s);
}
.finance-metrics article {
	display: grid;
	align-content: start;
	gap: var(--spacing-2xs);
	min-width: 0;
	padding: var(--spacing-m);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-secondary);
}
.finance-metrics span,
.finance-metrics small {
	color: var(--theme-text-muted);
}
.finance-metrics strong {
	font-size: var(--font-size-2);
	line-height: 1.15;
	overflow-wrap: anywhere;
}
.category-list article {
	grid-template-columns: minmax(10rem, 1fr) repeat(2, minmax(9rem, 0.7fr)) auto;
}
.record-list article > div:last-child,
.history-list article > div:last-child {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	flex-wrap: wrap;
	gap: var(--spacing-xs);
}
.calculated-field {
	display: grid;
	align-content: center;
	gap: var(--spacing-3xs);
	min-height: 4.75rem;
	padding: var(--spacing-xs) var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-field);
	background: var(--theme-secondary);
}
.calculated-field span,
.calculated-field small {
	color: var(--theme-text-muted);
}
.calculated-field strong {
	font-size: var(--font-size-1);
}
.check-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: var(--spacing-s) var(--spacing-l);
}
.cost-line-list {
	display: grid;
	gap: var(--spacing-s);
}
.cost-line-list article {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: var(--spacing-xs);
	padding: var(--spacing-s);
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-card);
	background: var(--theme-surface-raised);
}
.cost-line-review {
	grid-column: 1/-1;
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: var(--spacing-3xs) var(--spacing-xs);
	color: var(--theme-text-muted);
	font-size: var(--font-size--2);
}
.cost-line-review p {
	margin: 0;
}
.cost-line-review strong {
	color: var(--theme-text);
}
.extraction-summary {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: var(--spacing-s);
}
.extraction-summary p {
	margin: 0.25rem 0 0;
}
.invoice-ocr {
	max-height: 20rem;
	margin: var(--spacing-s) 0 0;
	padding: var(--spacing-s);
	overflow: auto;
	border: var(--border-width-1) solid var(--theme-border);
	border-radius: var(--component-radius-field);
	background: var(--theme-field);
	color: var(--theme-text);
	font-family: var(--font-family-c);
	font-size: var(--font-size--2);
	line-height: 1.55;
	white-space: pre-wrap;
	overflow-wrap: anywhere;
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
.field-grid--wide {
	grid-template-columns: repeat(4, minmax(0, 1fr));
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
.finance-tabs {
	grid-template-columns: minmax(0, 1fr);
	min-width: 0;
}
.finance-tabs__content {
	grid-template-columns: minmax(0, 1fr);
	width: 100%;
	min-width: 0;
}
.finance-tabs__content > * {
	min-width: 0;
}
.finance-tabs__content[hidden] {
	display: none;
}
@media (max-width: 1100px) {
	.finance-metrics {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
	.cost-line-list article,
	.field-grid--wide,
	.review-field-grid--offer {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}
	.category-list article {
		grid-template-columns: minmax(9rem, 1fr) repeat(2, minmax(8rem, 0.7fr));
	}
	.category-list article > *:last-child {
		grid-column: 1/-1;
		width: fit-content;
	}
}
@media (max-width: 700px) {
	.field-choice-grid,
	.finance-metrics,
	.cost-line-list article,
	.field-grid--wide,
	.invoice-stage,
	.invoice-posting,
	.setup-review-list,
	.review-field-grid,
	.review-field-grid--offer,
	.recipe-ingredient-list article,
	.recipe-instruction-list article {
		grid-template-columns: 1fr;
	}
	.mapping-list article,
	.history-list article,
	.record-list article,
	.category-list article {
		grid-template-columns: 1fr;
	}
	.record-list article > div:last-child,
	.history-list article > div:last-child {
		justify-content: flex-start;
	}
	.finance-overview {
		padding: var(--spacing-m);
	}
	.extraction-summary,
	.apply-boundary {
		align-items: stretch;
		flex-direction: column;
	}
	.category-list article > *:last-child {
		grid-column: auto;
	}
	.recipe-ingredient-list .review-errors,
	.recipe-instruction-list .review-errors,
	.recipe-instruction-list .check-field {
		grid-column: auto;
	}
}
</style>
