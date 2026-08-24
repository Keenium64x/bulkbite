<script setup>
import { onMounted, reactive, ref } from "vue"
import { SystemBadge, SystemDatePicker, SystemOperationalButton, SystemSelect } from "@/desyium"
import { accountantExportUrl, getAccountantExport, getSpendReport } from "@/resources/api"

// =============================================================================
// region REPORT PERIOD STATION
// =============================================================================

const today = new Date()
const localDate = value => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`
const firstDay = localDate(new Date(today.getFullYear(), today.getMonth(), 1))
const form = reactive({ from_date: firstDay, to_date: localDate(today), dataset: "receipts" })
const report = ref(null)
const exportPreview = ref(null)
const busy = ref(false)
const error = ref("")
const datasets = [{ label: "Receipts", value: "receipts" }, { label: "Operating costs", value: "operating_costs" }, { label: "Stock events", value: "stock_events" }, { label: "Closing stock", value: "closing_stock" }]

function validPeriod() {
  error.value = ""
  if (!form.from_date || !form.to_date) { error.value = "Choose both dates."; return false }
  if (form.from_date > form.to_date) { error.value = "From date must be on or before to date."; return false }
  return true
}

async function loadReport() {
  if (!validPeriod()) return
  busy.value = true
  try {
    const [reportData, exportData] = await Promise.all([getSpendReport(form.from_date, form.to_date), getAccountantExport(form.from_date, form.to_date)])
    report.value = reportData
    exportPreview.value = exportData
  } catch (exception) { error.value = exception.message }
  finally { busy.value = false }
}

function download() { if (validPeriod()) window.location.assign(accountantExportUrl(form.from_date, form.to_date, form.dataset)) }
function money(value) { return `R ${Number(value || 0).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` }
function variance(value) { return `${Number(value) > 0 ? "+" : ""}${money(value)}` }
function percentage(value) { return `${Number(value || 0).toLocaleString("en-ZA", { maximumFractionDigits: 1 })}%` }

onMounted(loadReport)

// endregion REPORT PERIOD STATION
</script>

<template>
  <section data-block="accountant-export" class="workflow-block">
    <header class="workflow-header"><div><p class="eyebrow">Reports</p><h1>Financial performance and savings</h1><p>Compare configured revenue, food purchasing, savings, and the operating costs involved in making and delivering meals.</p></div><SystemBadge>Read only</SystemBadge></header>
    <div v-if="error" class="state-message state-message--error" role="alert">{{ error }}</div>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Period</p><h2>Choose the reporting dates</h2><p>Receipt purchases can exceed one plan because full packs leave stock for later periods.</p></div></div>
      <div class="field-grid"><SystemDatePicker v-model="form.from_date" label="From date" format="YYYY-MM-DD" :clearable="false" /><SystemDatePicker v-model="form.to_date" label="To date" format="YYYY-MM-DD" :clearable="false" /></div>
      <div class="button-row"><SystemOperationalButton variant="outline" size="lg" :loading="busy" @click="loadReport">Update report</SystemOperationalButton></div>
    </section>
    <template v-if="report">
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">{{ report.period.from_date }} to {{ report.period.to_date }}</p><h2>Period result</h2></div></div>
        <div class="metric-board metric-board--paper"><div><strong>{{ money(report.summary.expected_spend) }}</strong><span>theoretical spend</span></div><div><strong>{{ money(report.summary.actual_spend) }}</strong><span>actual spend</span></div><div><strong>{{ variance(report.summary.variance) }}</strong><span>difference</span></div><div><strong>{{ report.summary.receipt_count }}</strong><span>reviewed receipts</span></div></div>
        <div v-if="report.summary.unassigned_receipt_count" class="safety-note"><strong>{{ report.summary.unassigned_receipt_count }} receipt(s) sit outside one clear plan period.</strong><p>Their actual spend remains in the report and is not discarded.</p></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Profit</p><h2>After food and operating costs</h2><p>{{ report.profit.actual_qualification }}</p></div></div>
        <div class="metric-board metric-board--paper"><div><strong>{{ money(report.profit.revenue) }}</strong><span>configured revenue</span></div><div><strong>{{ money(report.profit.expected_gross_profit) }}</strong><span>expected gross profit</span></div><div><strong>{{ money(report.profit.actual_gross_profit) }}</strong><span>actual gross profit</span></div><div><strong>{{ money(report.profit.actual_operating_result) }}</strong><span>result after entered costs</span></div></div>
        <p class="safety-note">Revenue basis: {{ report.profit.revenue_basis }}. Actual labour and overhead only count when entered as cost evidence.</p>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Operating costs</p><h2>What it costs to make and deliver the meals</h2><p>Expected rules use the selected period's customers, meals, kilograms, and revenue. Actual values come from entered cost records.</p></div></div>
        <div class="metric-board metric-board--paper"><div><strong>{{ money(report.operating_costs.expected_total) }}</strong><span>expected operating costs</span></div><div><strong>{{ money(report.operating_costs.actual_total) }}</strong><span>entered actual costs</span></div><div><strong>{{ report.operating_costs.drivers.meals }}</strong><span>planned meals</span></div><div><strong>{{ percentage(report.profit.revenue ? report.operating_costs.actual_total / report.profit.revenue * 100 : 0) }}</strong><span>actual costs of revenue</span></div></div>
        <div class="table-wrap"><table><thead><tr><th>Cost category</th><th>Expected</th><th>Actual entered</th><th>Difference</th></tr></thead><tbody><tr v-for="row in report.operating_costs.breakdown" :key="row.category"><td>{{ row.category }}</td><td class="money-cell">{{ money(row.expected) }}</td><td class="money-cell">{{ money(row.actual) }}</td><td class="money-cell">{{ variance(row.variance) }}</td></tr><tr v-if="!report.operating_costs.breakdown.length"><td colspan="4">No expected rules or actual operating costs overlap this period.</td></tr></tbody></table></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Savings bridge</p><h2>How discounts change the planned basket</h2><p>Every configured offer discount, rebate, or avoided delivery fee remains visible as its own financial effect.</p></div></div>
        <div class="metric-board metric-board--paper"><div><strong>{{ money(report.summary.expected_base_spend) }}</strong><span>base basket price</span></div><div><strong>{{ money(report.summary.expected_savings) }}</strong><span>planned savings</span></div><div><strong>{{ money(report.summary.expected_added_buying_costs) }}</strong><span>added buying costs</span></div><div><strong>{{ money(report.summary.expected_spend) }}</strong><span>planned landed cost</span></div></div>
        <div class="table-wrap"><table><thead><tr><th>Saving or cost</th><th>Type</th><th>Supplier</th><th>Effect</th><th>Expected</th><th>Actual receipt</th></tr></thead><tbody><tr v-for="row in report.savings" :key="`${row.name}-${row.type}`"><td>{{ row.name }}</td><td>{{ row.type }}</td><td>{{ row.suppliers.join(", ") || "All suppliers" }}</td><td>{{ row.effect === "saving" ? "Reduces cost" : row.effect === "included" ? "Included in price" : "Adds cost" }}</td><td class="money-cell">{{ money(row.expected_amount) }}</td><td class="money-cell">{{ money(row.actual_amount) }}</td></tr><tr v-if="!report.savings.length"><td colspan="6">No planned or receipt-proven savings and buying adjustments apply to this period.</td></tr></tbody></table></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Plans</p><h2>Monthly plan comparison</h2></div></div>
        <div class="table-wrap"><table><thead><tr><th>Plan</th><th>Dates</th><th>Theory</th><th>Actual in plan dates</th><th>Difference</th></tr></thead><tbody><tr v-for="row in report.plans" :key="row.name"><td><strong>{{ row.plan_title }}</strong><small>{{ row.name }}</small></td><td>{{ row.period_start }} to {{ row.period_end }}</td><td class="money-cell">{{ money(row.expected_spend) }}</td><td class="money-cell">{{ money(row.actual_spend) }}</td><td class="money-cell">{{ variance(row.variance) }}</td></tr><tr v-if="!report.plans.length"><td colspan="5">No saved plan overlaps this period.</td></tr></tbody></table></div>
      </section>
      <section class="data-section">
        <div class="section-heading"><div><p class="eyebrow">Breakdown</p><h2>Supplier and food category</h2></div></div>
        <div class="table-wrap"><table><thead><tr><th>Supplier</th><th>Food category</th><th>Theory</th><th>Actual</th><th>Difference</th></tr></thead><tbody><tr v-for="row in report.breakdown" :key="`${row.supplier}-${row.item_category}`"><td>{{ row.supplier }}</td><td>{{ row.item_category }}</td><td class="money-cell">{{ money(row.expected_spend) }}</td><td class="money-cell">{{ money(row.actual_spend) }}</td><td class="money-cell">{{ variance(row.variance) }}</td></tr><tr v-if="!report.breakdown.length"><td colspan="5">No theoretical or actual purchasing lines fall in this period.</td></tr></tbody></table></div>
      </section>
    </template>
    <section class="form-section">
      <div class="section-heading"><div><p class="eyebrow">Accountant export</p><h2>Download operational records</h2><p>Accounting dimensions stay outside worker flows. Choose a dataset for the accountant.</p></div></div>
      <div class="field-grid"><label class="field-shell"><span>Dataset</span><SystemSelect v-model="form.dataset" :options="datasets" size="lg" /></label></div>
      <div class="button-row"><SystemOperationalButton variant="solid" size="lg" :disabled="!exportPreview" @click="download">Download CSV</SystemOperationalButton></div>
      <p v-if="exportPreview" class="safety-note">{{ exportPreview.receipts.length }} receipts, {{ exportPreview.operating_costs.length }} operating costs, {{ exportPreview.stock_events.length }} stock events, and {{ exportPreview.closing_stock.length }} closing balances are available for this period.</p>
    </section>
  </section>
</template>
