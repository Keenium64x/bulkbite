<script setup>
import { computed, onMounted, ref } from "vue";
import { SystemBulkbiteAppShell, SystemPriceHistory } from "@/desyium";
import { getInventorySnapshot, getWorkspaceSnapshot, logOut } from "@/resources/api";

// =============================================================================
// region PRICE HISTORY PAGE
// =============================================================================

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
const snapshot = ref(null);
const inventory = ref(null);
const loading = ref(false);
const sessionBusy = ref(false);
const error = ref("");
const currentUser = computed(() => snapshot.value?.user || window.boot?.user || "");

async function loadPage() {
	loading.value = true;
	error.value = "";
	try {
		const [workspaceData, inventoryData] = await Promise.all([
			getWorkspaceSnapshot(),
			getInventorySnapshot("Ingredients"),
		]);
		snapshot.value = workspaceData;
		inventory.value = inventoryData;
	} catch (exception) {
		error.value = exception.message;
	} finally {
		loading.value = false;
	}
}

function navigate(id) {
	if (typeof id === "object") {
		if (id.mode === "workflow")
			return window.location.assign(
				id.id === "overview" ? "/bulkbite" : `/bulkbite?work=${encodeURIComponent(id.id)}`,
			);
		if (id.mode === "route") return window.location.assign(id.href);
		if (id.mode === "catalogue") return window.location.assign("/bulkbite/setup");
		if (id.mode === "list")
			return window.location.assign(`/bulkbite/setup/${encodeURIComponent(id.doctype)}`);
	}
	if (id === "prices") return;
	window.location.assign(
		id === "overview" ? "/bulkbite" : `/bulkbite?work=${encodeURIComponent(id)}`,
	);
}

async function handleLogout() {
	sessionBusy.value = true;
	try {
		await logOut();
		window.location.assign("/login?redirect-to=%2Fbulkbite%2Fprices");
	} finally {
		sessionBusy.value = false;
	}
}

onMounted(loadPage);

// endregion PRICE HISTORY PAGE
</script>

<template>
	<SystemBulkbiteAppShell
		:sections="sections"
		active-section="prices"
		:user="currentUser"
		:busy="loading"
		:session-busy="sessionBusy"
		@navigate="navigate"
		@refresh="loadPage"
		@logout="handleLogout"
	>
		<div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
		<SystemPriceHistory v-else :snapshot="snapshot" :inventory="inventory" />
	</SystemBulkbiteAppShell>
</template>
