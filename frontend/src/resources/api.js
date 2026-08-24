// =============================================================================
// region FRAPPE TRANSPORT
// =============================================================================

export async function call(method, args = {}, httpMethod = "POST") {
  const headers = { "Content-Type": "application/json" }
  const csrfToken = window.csrf_token || window.boot?.csrf_token
  if (csrfToken) headers["X-Frappe-CSRF-Token"] = csrfToken
  const query = httpMethod === "GET" ? `?${new URLSearchParams(cleanArgs(args))}` : ""
  const response = await fetch(`/api/method/${method}${query}`, {
    method: httpMethod,
    headers,
    credentials: "same-origin",
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
export const logOut = () => call("logout")
export const getInventorySnapshot = (location) => call("bulkbite.api.get_inventory_snapshot", { location }, "GET")
export const getProductionPlanSnapshot = (planName, location) => call("bulkbite.api.get_production_plan_snapshot", { plan_name: planName, location }, "GET")
export const saveMonthlyProductionPlan = (payload) => call("bulkbite.api.save_monthly_production_plan", { payload })
export const cancelProductionPlan = (name) => call("bulkbite.api.cancel_production_plan", { name })
export const resolveScanCode = (code) => call("bulkbite.api.resolve_scan_code", { code }, "GET")
export const assignScanCode = (itemCode, code) => call("bulkbite.api.assign_scan_code", { item_code: itemCode, code })
export const getAuxiliaryCatalogue = () => call("bulkbite.api.get_auxiliary_form_catalogue", {}, "GET")
export const getAuxiliaryRecordList = (doctype) => call("bulkbite.api.get_auxiliary_record_list", { doctype }, "GET")
export const getAuxiliaryRecord = (doctype, name) => call("bulkbite.api.get_auxiliary_record", { doctype, name }, "GET")
export const saveAuxiliaryRecord = (doctype, name, values, tables) => call("bulkbite.api.save_auxiliary_record", { doctype, name, values, tables })
export const createRunFromPlan = (planName, planRowName, productionDate, sourceLocation, targetLocation) =>
  call("bulkbite.api.create_run_from_plan", {
    plan_name: planName,
    plan_row_name: planRowName,
    production_date: productionDate,
    source_location: sourceLocation,
    target_location: targetLocation,
  })
export const updateProductionActuals = (name, actualOutputQty, ingredients, notes) =>
  call("bulkbite.api.update_production_actuals", { name, actual_output_qty: actualOutputQty, ingredients, notes })
export const submitProductionRun = (name) => call("bulkbite.api.submit_production_run", { name })
export const discardProductionRun = (name) => call("bulkbite.api.discard_production_run", { name })
export const createReceiptIntake = (payload) => call("bulkbite.api.create_receipt_intake", { payload })
export const startReceiptExtraction = (fileUrl) => call("bulkbite.api.start_receipt_extraction", { file_url: fileUrl })
export const getReceiptExtractionStatus = (jobId) => call("bulkbite.api.get_receipt_extraction_status", { job_id: jobId }, "GET")
export const receiveStockFromReceipt = (receiptName) => call("bulkbite.api.receive_stock_from_receipt", { receipt_name: receiptName })
export const createStockCountDraft = (payload) => call("bulkbite.api.create_stock_count_draft", { payload })
export const approveStockAudit = (name) => call("bulkbite.api.approve_stock_audit", { name })
export const createDocumentExtractionDraft = (payload) => call("bulkbite.api.create_document_extraction_draft", { payload })
export const reviewDocumentExtraction = (name, rows) => call("bulkbite.api.review_document_extraction", { name, rows })
export const applyDocumentMeasurements = (name) => call("bulkbite.api.apply_document_measurements", { name })
export const getAccountantExport = (fromDate, toDate) => call("bulkbite.api.get_accountant_export", { from_date: fromDate, to_date: toDate }, "GET")
export const getSpendReport = (fromDate, toDate) => call("bulkbite.api.get_spend_report", { from_date: fromDate, to_date: toDate }, "GET")
export const getPurchasePriceHistory = (filters) => call("bulkbite.api.get_purchase_price_history", filters, "GET")

export function accountantExportUrl(fromDate, toDate, dataset) {
  return `/api/method/bulkbite.api.download_accountant_export?${new URLSearchParams({
    from_date: fromDate,
    to_date: toDate,
    dataset,
  })}`
}

// endregion FRAPPE TRANSPORT
