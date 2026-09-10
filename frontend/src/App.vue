<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
	SystemAccountantExport,
	SystemAccordion,
	SystemAccordionContent,
	SystemAccordionItem,
	SystemAccordionTrigger,
	SystemAuxiliaryRecords,
	SystemBulkbiteAppShell,
	SystemBuyingPlan,
	SystemDocumentReview,
	SystemEmployeeManagement,
	SystemKitchenExecutionPlan,
	SystemMonthlyPlanning,
	SystemNativeAvailabilityState,
	SystemProductionMeasurement,
	SystemPriceHistory,
	SystemReceiptIntake,
	SystemStockOverview,
	SystemStockReconciliation,
} from "@/desyium";
import {
	assignScanCode,
	getInventorySnapshot,
	getProductionPlanSnapshot,
	getWorkspaceSnapshot,
	logOut,
	resolveScanCode,
} from "@/resources/api";
import { runtimeConfig } from "@/config/runtime";
import { nativeSession, restoreNativeSession } from "@/native/auth";
import NativeLoginPage from "@/pages/NativeLoginPage.vue";
import {
	checkNativeProductionAvailability,
	nativeAvailability,
	productionHost,
} from "@/native/availability";

const sections = [
	{ id: "overview", label: "Dashboard" },
	{ id: "receipts", label: "Receipts" },
	{ id: "production", label: "Production" },
	{ id: "planning", label: "Planning", group: "theoretical" },
	{ id: "forecasting", label: "Forecasting", group: "supporting" },
	{ id: "buying", label: "Buying", group: "theoretical" },
	{ id: "finance", label: "Finance", group: "supporting" },
	{ id: "export", label: "Reports", group: "supporting" },
	{ id: "import", label: "Import", group: "supporting" },
	{ id: "stock", label: "Stock", group: "theoretical" },
];
const auxiliarySections = ["employees", "documents", "history", "operations", "containers"];
const activeSectionStorageKey = "bulkbite-active-section";
const allowedSectionIds = new Set([
	...sections.map((section) => section.id),
	...auxiliarySections,
]);
const route = useRoute();
const router = useRouter();
const auxiliaryMode = computed(() => {
	if (route.meta.auxiliaryRecord)
		return route.name === "AuxiliaryRecordCreate" ? "create" : "edit";
	if (route.meta.auxiliaryList) return "list";
	if (route.meta.auxiliaryCatalogue) return "catalogue";
	return "";
});
const kitchenPlanMode = computed(() => route.name === "BulkBiteKitchenPlan");
const activeSection = ref(resolveInitialSection());
const employeeReturnSection = ref("production");
const snapshot = ref(null);
const inventory = ref(null);
const plan = ref(null);
const scanResult = ref(null);
const loading = ref(false);
const sessionBusy = ref(false);
const error = ref("");
const applicationInitialising = ref(false);
const currentUser = computed(
	() => snapshot.value?.user || nativeSession.user || window.boot?.user || "",
);

function navigate(id) {
	if (typeof id === "object") return navigateAuxiliary(id);
	if (route.path.startsWith("/bulkbite/setup") || kitchenPlanMode.value) router.push("/bulkbite");
	activeSection.value = id;
	window.localStorage.setItem(activeSectionStorageKey, id);
	const url = new URL(window.location.href);
	id === "overview" ? url.searchParams.delete("work") : url.searchParams.set("work", id);
	window.history.replaceState({}, "", url);
	requestAnimationFrame(() => document.querySelector(".app-shell__work")?.focus());
}

async function closeKitchenPlan() {
	activeSection.value = "production";
	window.localStorage.setItem(activeSectionStorageKey, "production");
	await router.push({ path: "/bulkbite", query: { work: "production" } });
	await loadAll();
}

function openEmployees(origin) {
	employeeReturnSection.value = ["planning", "forecasting"].includes(origin)
		? origin
		: "production";
	navigate("employees");
}

function resolveInitialSection() {
	const urlSection = new URLSearchParams(window.location.search).get("work");
	if (allowedSectionIds.has(urlSection)) return urlSection;
	const storedSection = window.localStorage.getItem(activeSectionStorageKey);
	return allowedSectionIds.has(storedSection) ? storedSection : "overview";
}

function navigateAuxiliary(target) {
	if (target.mode === "workflow") return navigate(target.id);
	if (target.mode === "route") return router.push(target.href);
	if (target.mode === "catalogue") return router.push({ name: "BulkBiteSetup" });
	if (target.mode === "list")
		return router.push({ name: "BulkBiteSetupList", params: { doctype: target.doctype } });
	if (target.mode === "create")
		return router.push({ name: "AuxiliaryRecordCreate", params: { doctype: target.doctype } });
	return router.push({
		name: "AuxiliaryRecordEdit",
		params: { doctype: target.doctype, name: target.name },
	});
}

async function loadAll() {
	loading.value = true;
	error.value = "";
	try {
		const [workspaceData, inventoryData, planData] = await Promise.all([
			getWorkspaceSnapshot(),
			getInventorySnapshot("Ingredients"),
			getProductionPlanSnapshot(null, "Ingredients"),
		]);
		snapshot.value = workspaceData;
		inventory.value = inventoryData;
		plan.value = planData;
		return true;
	} catch (exception) {
		error.value = exception.message;
		return false;
	} finally {
		loading.value = false;
	}
}

async function initialiseApplication() {
	if (applicationInitialising.value) return;
	applicationInitialising.value = true;
	if (runtimeConfig.isNative) {
		const productionAvailable = await checkNativeProductionAvailability();
		if (!productionAvailable) {
			applicationInitialising.value = false;
			return;
		}
		try {
			await restoreNativeSession();
		} catch {
			applicationInitialising.value = false;
			return;
		}
		if (!nativeSession.authenticated) {
			applicationInitialising.value = false;
			return;
		}
		if (route.path === "/" || !route.path.startsWith("/bulkbite"))
			await router.replace("/bulkbite");
	}
	await loadAll();
	applicationInitialising.value = false;
}

async function retryNativeAvailability() {
	const available = await checkNativeProductionAvailability({ force: true });
	if (available) await initialiseApplication();
}

async function handleNativeAuthenticated() {
	await router.replace("/bulkbite");
	await loadAll();
}

async function scan(code) {
	error.value = "";
	try {
		scanResult.value = await resolveScanCode(code);
	} catch (exception) {
		error.value = exception.message;
	}
}
async function mapScan(itemCode, code) {
	error.value = "";
	try {
		scanResult.value = await assignScanCode(itemCode, code);
		await loadAll();
	} catch (exception) {
		error.value = exception.message;
	}
}
async function handleLogout() {
	sessionBusy.value = true;
	error.value = "";
	try {
		await logOut();
		if (runtimeConfig.isNative) {
			snapshot.value = null;
			inventory.value = null;
			plan.value = null;
			await router.replace("/bulkbite");
			sessionBusy.value = false;
			return;
		}
		window.location.assign("/login?redirect-to=%2Fbulkbite");
	} catch (exception) {
		error.value = exception.message;
		sessionBusy.value = false;
	}
}
onMounted(initialiseApplication);
watch(
	() => nativeAvailability.status,
	(status) => {
		if (runtimeConfig.isNative && status === "available" && !nativeSession.authenticated)
			initialiseApplication();
	},
);
</script>

<template>
	<SystemNativeAvailabilityState
		v-if="runtimeConfig.isNative && nativeAvailability.status !== 'available'"
		:status="nativeAvailability.status"
		:checking="nativeAvailability.checking"
		:production-host="productionHost"
		@retry="retryNativeAvailability"
	/>
	<div v-else-if="!nativeSession.ready" class="native-login native-login--loading" role="status">
		Starting BulkBite
	</div>
	<NativeLoginPage
		v-else-if="runtimeConfig.isNative && !nativeSession.authenticated"
		@authenticated="handleNativeAuthenticated"
	/>
	<SystemBulkbiteAppShell
		v-else
		:sections="sections"
		:active-section="activeSection"
		:user="currentUser"
		:busy="loading"
		:session-busy="sessionBusy"
		:refresh-action="loadAll"
		@navigate="navigate"
		@refresh="loadAll"
		@logout="handleLogout"
	>
		<SystemAuxiliaryRecords
			v-if="auxiliaryMode"
			:mode="auxiliaryMode"
			:doctype="String(route.params.doctype || '')"
			:record-name="String(route.params.name || '')"
			@navigate="navigateAuxiliary"
		/>
		<SystemKitchenExecutionPlan
			v-else-if="kitchenPlanMode"
			:run-name="String(route.params.runName || '')"
			@close="closeKitchenPlan"
			@open-employees="navigate('employees')"
			@changed="loadAll"
		/>
		<SystemStockOverview
			v-else-if="activeSection === 'overview'"
			mode="dashboard"
			:snapshot="snapshot"
			:inventory="inventory"
			:plan="plan"
			:loading="loading"
			:error="error"
			@open-workflow="navigate"
		/>
		<SystemReceiptIntake
			v-else-if="activeSection === 'receipts'"
			:snapshot="snapshot"
			:inventory="inventory"
			:plan="plan"
			@changed="loadAll"
		/>
		<SystemProductionMeasurement
			v-else-if="activeSection === 'production'"
			:snapshot="snapshot"
			:plan="plan"
			@changed="loadAll"
			@open-worker-sheets="navigate('documents')"
			@open-employees="openEmployees('production')"
			@open-history="navigate('history')"
		/>
		<SystemProductionMeasurement
			v-else-if="activeSection === 'history'"
			mode="history"
			:snapshot="snapshot"
			:plan="plan"
			@close="navigate('production')"
		/>
		<SystemEmployeeManagement
			v-else-if="activeSection === 'employees'"
			@close="navigate(employeeReturnSection)"
			@changed="loadAll"
		/>
		<SystemMonthlyPlanning
			v-else-if="activeSection === 'planning'"
			:snapshot="snapshot"
			:plan="plan"
			@changed="loadAll"
			@open-employees="openEmployees('planning')"
		/>
		<SystemMonthlyPlanning
			v-else-if="activeSection === 'forecasting'"
			mode="forecasting"
			:snapshot="snapshot"
			:plan="plan"
			@changed="loadAll"
			@open-employees="openEmployees('forecasting')"
		/>
		<SystemBuyingPlan
			v-else-if="activeSection === 'buying'"
			:snapshot="snapshot"
			:plan="plan"
			@open-workflow="navigate"
			@changed="loadAll"
		/>
		<SystemDocumentReview
			v-else-if="activeSection === 'documents'"
			:snapshot="snapshot"
			:inventory="inventory"
			@changed="loadAll"
		/>
		<SystemPriceHistory
			v-else-if="activeSection === 'finance'"
			mode="finance"
			:snapshot="snapshot"
			:inventory="inventory"
			@open-workflow="navigate"
			@changed="loadAll"
		/>
		<SystemAccountantExport v-else-if="activeSection === 'export'" />
		<SystemPriceHistory
			v-else-if="activeSection === 'import'"
			mode="import"
			:snapshot="snapshot"
			:inventory="inventory"
			@changed="loadAll"
		/>
		<template v-else-if="activeSection === 'stock'">
			<SystemStockOverview
				mode="stock"
				:snapshot="snapshot"
				:inventory="inventory"
				:plan="plan"
				:scan-result="scanResult"
				:loading="loading"
				:error="error"
				@scan="scan"
				@map-scan="mapScan"
				@open-workflow="navigate"
			/>
			<SystemAccordion type="multiple" :default-value="['reconciliation']" class="stock-support-sections">
				<SystemAccordionItem value="reconciliation" class="stock-support-section">
					<SystemAccordionTrigger class="stock-support-section__trigger">
						<div><span>Physical count</span><strong>Stock reconciliation</strong></div>
					</SystemAccordionTrigger>
					<SystemAccordionContent class="stock-support-section__content">
						<SystemStockReconciliation :inventory="inventory" @changed="loadAll" />
					</SystemAccordionContent>
				</SystemAccordionItem>
				<SystemAccordionItem value="prices" class="stock-support-section">
					<SystemAccordionTrigger class="stock-support-section__trigger">
						<div><span>Cost evidence</span><strong>Price history</strong></div>
					</SystemAccordionTrigger>
					<SystemAccordionContent class="stock-support-section__content">
						<SystemPriceHistory
							mode="catalogue"
							:snapshot="snapshot"
							:inventory="inventory"
							@changed="loadAll"
						/>
					</SystemAccordionContent>
				</SystemAccordionItem>
			</SystemAccordion>
		</template>
		<SystemStockOverview
			v-else-if="activeSection === 'operations'"
			mode="operations"
			:snapshot="snapshot"
			:inventory="inventory"
			:plan="plan"
			@open-workflow="navigate"
			@changed="loadAll"
		/>
		<SystemStockOverview
			v-else-if="activeSection === 'containers'"
			mode="containers"
			:snapshot="snapshot"
			:inventory="inventory"
			:plan="plan"
			@open-workflow="navigate"
			@changed="loadAll"
		/>
	</SystemBulkbiteAppShell>
</template>

<style scoped>
.stock-support-sections {
	display: grid;
	gap: var(--spacing-s);
	margin-top: var(--spacing-m);
}

.stock-support-section {
	overflow: hidden;
}

.stock-support-section__trigger {
	width: 100%;
	text-align: left;
	text-decoration: none !important;
}

.stock-support-section__trigger > div {
	display: grid;
	gap: var(--spacing-3xs);
}

.stock-support-section__trigger span {
	color: var(--theme-text-muted);
	font-size: var(--font-size--2);
	font-weight: var(--font-weight-600);
	letter-spacing: var(--font-letter-spacing-2);
	text-transform: uppercase;
}

.stock-support-section__trigger strong {
	font-size: var(--font-size-1);
}

.stock-support-section__content {
}
</style>
