// =============================================================================
// region FRAPPE TRANSPORT
// =============================================================================

import { clearNativeTokens } from "@/native/auth"
import { runtimeConfig } from "@/config/runtime"
import { authenticatedFetch, resolveRequestUrl } from "@/resources/transport"

export async function call(method, args = {}, httpMethod = "POST") {
  const query = httpMethod === "GET" ? `?${new URLSearchParams(cleanArgs(args))}` : ""
  const response = await authenticatedFetch(`/api/method/${method}${query}`, {
    method: httpMethod,
    body: httpMethod === "GET" ? undefined : JSON.stringify(args),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.exc_type || payload.exception) {
    throw new Error(readFrappeError(payload) || `Request failed with ${response.status}`)
  }
  return payload.message
}

function cleanArgs(args) {
  return Object.fromEntries(Object.entries(args).filter(([, value]) => value !== undefined && value !== null && value !== ""))
}

function readFrappeError(payload) {
  if (payload._server_messages) {
    try {
      return JSON.parse(payload._server_messages)
        .map((entry) => JSON.parse(entry).message)
        .filter(Boolean)
        .join(" ")
    } catch {
      return "The server could not complete this action."
    }
  }
  return payload.message || payload.exception
}

export const getWorkspaceSnapshot = () => call("bulkbite.api.get_workspace_snapshot", {}, "GET")
export const logOut = async () => {
  if (runtimeConfig.isNative) {
    await clearNativeTokens({ revoke: true })
    return { ok: true }
  }
  return call("logout")
}
export const getInventorySnapshot = (location) => call("bulkbite.api.get_inventory_snapshot", { location }, "GET")
export const getProductionPlanSnapshot = (planName, location) => call("bulkbite.api.get_production_plan_snapshot", { plan_name: planName, location }, "GET")
export const calculateCapacityScenario = (payload) => call("bulkbite.api.calculate_capacity_scenario", { payload })
export const saveMonthlyProductionPlan = (payload) => call("bulkbite.api.save_monthly_production_plan", { payload })
export const syncOfflineMutation = (mutation) => call("bulkbite.api.sync_offline_mutation", {
  client_mutation_id: mutation.clientMutationId,
  operation: mutation.operation,
  payload: mutation.payload,
  base_modified: mutation.baseModified,
  overwrite_conflict: Boolean(mutation.overwriteConflict),
})
export const cancelProductionPlan = (name) => call("bulkbite.api.cancel_production_plan", { name })
export const resolveScanCode = (code) => call("bulkbite.api.resolve_scan_code", { code }, "GET")
export const assignScanCode = (itemCode, code) => call("bulkbite.api.assign_scan_code", { item_code: itemCode, code })
export const getAuxiliaryCatalogue = () => call("bulkbite.api.get_auxiliary_form_catalogue", {}, "GET")
export const getAuxiliaryRecordList = (doctype) => call("bulkbite.api.get_auxiliary_record_list", { doctype }, "GET")
export const getAuxiliaryRecordWorkspace = (doctype, query = {}) => call("bulkbite.api.get_auxiliary_record_workspace", { doctype, ...query, filters: query.filters?.length ? JSON.stringify(query.filters) : undefined, sort: query.sort ? JSON.stringify(query.sort) : undefined }, "GET")
export const getAuxiliaryRecord = (doctype, name) => call("bulkbite.api.get_auxiliary_record", { doctype, name }, "GET")
export const saveAuxiliaryRecord = (doctype, name, values, tables) => call("bulkbite.api.save_auxiliary_record", { doctype, name, values, tables })
export const planAuxiliaryRecordDeletion = (doctype, names, defaultOutcome = "delete", outcomesByDoctype = {}) => call("bulkbite.api.plan_auxiliary_record_deletion", { doctype, names, default_outcome: defaultOutcome, outcomes_by_doctype: outcomesByDoctype })
export const deleteAuxiliaryRecords = (request) => call("bulkbite.api.delete_auxiliary_records", { doctype: request.doctype, names: request.names, plan_token: request.planToken, outcome: request.outcome, outcomes_by_doctype: request.outcomesByDoctype, approved: request.approved })
export const getRecipeExpectation = (recipe, plannedOutputQty, sourceLocation) => call("bulkbite.api.get_recipe_expectation", { recipe, planned_output_qty: plannedOutputQty, source_location: sourceLocation }, "GET")
export const getProductionInstructions = (recipe, outputQty, teamSize) => call("bulkbite.api.get_production_instructions", { recipe, output_qty: outputQty, team_size: teamSize }, "GET")
export const createAdHocProductionRun = (recipe, plannedOutputQty, productionDate, sourceLocation = "Ingredients", targetLocation = "Finished Meals") => call("bulkbite.api.create_ad_hoc_production_run", { recipe, planned_output_qty: plannedOutputQty, production_date: productionDate, source_location: sourceLocation, target_location: targetLocation })
export const getFinishedFoodPosition = (itemCode = "", location = "Finished Meals") => call("bulkbite.api.get_finished_food_position", { item_code: itemCode, location }, "GET")
export const getProductionHistorySnapshot = (planName = "") => call("bulkbite.api.get_production_history_snapshot", { plan_name: planName }, "GET")
export const getOperationalCalendar = (fromDate, toDate) => call("bulkbite.api.get_operational_calendar", { from_date: fromDate, to_date: toDate }, "GET")
export const getContainerPosition = () => call("bulkbite.api.get_container_position", {}, "GET")
export const getContainerSuggestion = (outputQty) => call("bulkbite.api.get_container_suggestion", { output_qty: outputQty }, "GET")
export const updateOperationalAction = (name, action, newDate, reason) => call("bulkbite.api.update_operational_action", { name, action, new_date: newDate, reason })
export const createCustomOperationalAction = (payload) => call("bulkbite.api.create_custom_operational_action", payload)
export const recordContainerMovement = (payload) => call("bulkbite.api.record_container_movement", { payload })
export const allocateFinishedFood = (payload) => call("bulkbite.api.allocate_finished_food", { payload })
export const getBuyingRecommendation = (planName, location = "Ingredients", horizonWeeks = 4) => call("bulkbite.api.get_buying_recommendation", { plan_name: planName, location, horizon_weeks: horizonWeeks }, "GET")
export const createRunFromPlan = (planName, planRowName, productionDate, sourceLocation, targetLocation, recipe, plannedOutputQty, directionAction) =>
  call("bulkbite.api.create_run_from_plan", {
    plan_name: planName,
    plan_row_name: planRowName,
    production_date: productionDate,
    source_location: sourceLocation,
    target_location: targetLocation,
    recipe,
    planned_output_qty: plannedOutputQty,
    direction_action: directionAction,
  })
export const updateProductionActuals = (name, actualOutputQty, ingredients, notes, finishedContainerCount = 0) =>
	call("bulkbite.api.update_production_actuals", { name, actual_output_qty: actualOutputQty, ingredients, notes, finished_container_count: finishedContainerCount })
export const submitProductionRun = (name) => call("bulkbite.api.submit_production_run", { name })
export const discardProductionRun = (name) => call("bulkbite.api.discard_production_run", { name })
export const createReceiptIntake = (payload) => call("bulkbite.api.create_receipt_intake", { payload })
export const startReceiptExtraction = (fileUrls) => call("bulkbite.api.start_receipt_extraction", { file_urls: fileUrls })
export const getReceiptExtractionStatus = (jobId) => call("bulkbite.api.get_receipt_extraction_status", { job_id: jobId }, "GET")
export const startCostInvoiceExtraction = (fileUrls) => call("bulkbite.api.start_cost_invoice_extraction", { file_urls: fileUrls })
export const getCostInvoiceExtractionStatus = (jobId) => call("bulkbite.api.get_cost_invoice_extraction_status", { job_id: jobId }, "GET")
export const receiveStockFromReceipt = (receiptName) => call("bulkbite.api.receive_stock_from_receipt", { receipt_name: receiptName })
export const createStockCountDraft = (payload) => call("bulkbite.api.create_stock_count_draft", { payload })
export const approveStockAudit = (name) => call("bulkbite.api.approve_stock_audit", { name })
export const createDocumentExtractionDraft = (payload) => call("bulkbite.api.create_document_extraction_draft", { payload })
export const reviewDocumentExtraction = (name, rows) => call("bulkbite.api.review_document_extraction", { name, rows })
export const applyDocumentMeasurements = (name) => call("bulkbite.api.apply_document_measurements", { name })
export const getAccountantExport = (fromDate, toDate) => call("bulkbite.api.get_accountant_export", { from_date: fromDate, to_date: toDate }, "GET")
export const getSpendReport = (fromDate, toDate) => call("bulkbite.api.get_spend_report", { from_date: fromDate, to_date: toDate }, "GET")
export const getPurchasePriceHistory = (filters) => call("bulkbite.api.get_purchase_price_history", filters, "GET")
export const getPriceImportFields = () => call("bulkbite.api.get_price_import_fields", {}, "GET")
export const inspectPriceFile = (fileUrl) => call("bulkbite.api.inspect_catalogue_price_file", { file_url: fileUrl })
export const previewPriceWorkbook = (fileUrl, mapping) => call("bulkbite.api.preview_catalogue_price_workbook", { file_url: fileUrl, mapping })
export const startPriceImportImprovement = (batchName) => call("bulkbite.api.start_catalogue_price_improvement", { batch_name: batchName })
export const getPriceImportImprovementStatus = (jobId) => call("bulkbite.api.get_catalogue_price_improvement_status", { job_id: jobId }, "GET")
export const reviewPriceWorkbook = (batchName, proposal) => call("bulkbite.api.review_catalogue_price_workbook", { batch_name: batchName, proposal })
export const applyPriceWorkbook = (batchName) => call("bulkbite.api.apply_catalogue_price_workbook", { batch_name: batchName })
export const getSpreadsheetWorkspaceContract = (target, setupDoctype) => call("bulkbite.api.get_spreadsheet_workspace_contract", { target, setup_doctype: setupDoctype }, "GET")
export const inspectSpreadsheetWorkspaceFile = (target, fileUrl, setupDoctype) => call("bulkbite.api.inspect_spreadsheet_workspace_file", { target, file_url: fileUrl, setup_doctype: setupDoctype })
export const previewSpreadsheetWorkspaceImport = (target, fileUrl, mapping, setupDoctype) => call("bulkbite.api.preview_spreadsheet_workspace_import", { target, file_url: fileUrl, mapping, setup_doctype: setupDoctype })
export const reviewSpreadsheetWorkspaceImport = (batchName, proposal) => call("bulkbite.api.review_spreadsheet_workspace_import", { batch_name: batchName, proposal })
export const applySpreadsheetWorkspaceImport = (batchName) => call("bulkbite.api.apply_spreadsheet_workspace_import", { batch_name: batchName })
export const createCostInvoice = (payload) => call("bulkbite.api.create_cost_invoice", { payload })
export const postCostInvoice = (name) => call("bulkbite.api.post_cost_invoice", { name })
export const getFinanceWorkspace = (fromDate, toDate) => call("bulkbite.api.get_finance_workspace", { from_date: fromDate, to_date: toDate }, "GET")
export const saveExpectedCostRule = (payload) => call("bulkbite.api.save_expected_cost_rule", { payload })
export const saveMiscellaneousCost = (payload) => call("bulkbite.api.save_miscellaneous_cost", { payload })
export const savePriceAdjustment = (payload) => call("bulkbite.api.save_price_adjustment", { payload })
export const getEmployeeWorkspace = () => call("bulkbite.api.get_employee_workspace", {}, "GET")
export const saveEmployeeType = (payload) => call("bulkbite.api.save_employee_type", { payload })
export const saveEmployee = (payload) => call("bulkbite.api.save_employee", { payload })
export const saveTeamTemplate = (payload) => call("bulkbite.api.save_team_template", { payload })
export const saveProductionEmployees = (name, employees, teamTemplate, actualElapsedHours, scheduledElapsedHours) => call("bulkbite.api.save_production_employees", {
  name,
  employees,
  team_template: teamTemplate,
  actual_elapsed_hours: actualElapsedHours,
  scheduled_elapsed_hours: scheduledElapsedHours,
})

export function priceWorkbookUrl(fields) {
  return resolveRequestUrl(`/api/method/bulkbite.api.download_price_workbook?fields=${encodeURIComponent(JSON.stringify(fields || []))}`)
}

export function spreadsheetWorkspaceUrl(target, fields, setupDoctype) {
  return resolveRequestUrl(`/api/method/bulkbite.api.download_spreadsheet_workspace?${new URLSearchParams({
    target,
    fields: JSON.stringify(fields || []),
    setup_doctype: setupDoctype || "",
  })}`)
}

export function accountantExportUrl(fromDate, toDate, dataset) {
  return resolveRequestUrl(`/api/method/bulkbite.api.download_accountant_export?${new URLSearchParams({
    from_date: fromDate,
    to_date: toDate,
    dataset,
  })}`)
}

export function financeLedgerWorkbookUrl(fromDate, toDate) {
  return resolveRequestUrl(`/api/method/bulkbite.api.download_finance_ledger_workbook?${new URLSearchParams({ from_date: fromDate, to_date: toDate })}`)
}

export async function downloadAuthenticatedFile(url, fallbackName) {
  if (!runtimeConfig.isNative) {
    window.location.assign(url)
    return
  }
  const response = await authenticatedFetch(url, { method: "GET" })
  if (!response.ok) throw new Error(`Download failed with ${response.status}`)
  const blob = await response.blob()
  const disposition = response.headers.get("content-disposition") || ""
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedName = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  const filename = decodeURIComponent(encodedName || quotedName || fallbackName)
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = objectUrl
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000)
}

// endregion FRAPPE TRANSPORT
