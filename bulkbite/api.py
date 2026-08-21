from __future__ import annotations

import json
import csv
import io
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime
from openpyxl import load_workbook

from bulkbite.stock_ledger import append_stock_event, get_stock_balance, get_valuation_rate
from bulkbite.stock_production import derive_usage_from_remaining, get_available_stock, load_expected_usage
from bulkbite.document_extraction import extract_measurement_rows, resolve_private_source
from bulkbite.variance import calculate_output_variance, calculate_usage_variance


# =============================================================================
# region FRONTEND SNAPSHOT
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_workspace_snapshot():
	_require_app_user()
	return {
		"user": frappe.session.user,
		"company": "BulkBite",
		"setup_required": not bool(frappe.db.exists("BulkBite Location", "Ingredients")),
		"counts": {
			"ingredients": frappe.db.count("BulkBite Item", {"item_type": "Ingredient", "track_stock": 1, "enabled": 1}),
			"receipt_intakes": frappe.db.count("BulkBite Receipt Intake", {"status": ("!=", "Rejected")}),
			"received_receipts": frappe.db.count("BulkBite Receipt Intake", {"stock_events_posted": 1}),
			"draft_production_runs": frappe.db.count("BulkBite Production Run", {"docstatus": 0}),
			"posted_production_runs": frappe.db.count("BulkBite Production Run", {"docstatus": 1}),
		},
		"recent_runs": frappe.get_all(
			"BulkBite Production Run",
			fields=["name", "production_date", "finished_item", "planned_output_qty", "actual_output_qty", "material_cost_variance", "docstatus", "output_stock_event"],
			order_by="production_date desc, modified desc",
			limit=12,
		),
		"recent_receipts": frappe.get_all(
			"BulkBite Receipt Intake",
			fields=["name", "supplier", "invoice_date", "total_amount", "status", "stock_events_posted", "accountant_exported"],
			order_by="invoice_date desc, modified desc",
			limit=8,
		),
		"options": {
			"locations": frappe.get_all("BulkBite Location", filters={"enabled": 1}, pluck="name", order_by="name"),
			"recipes": frappe.get_all("BulkBite Recipe", filters={"status": "Approved"}, fields=["name", "recipe_name", "finished_item as item", "nominal_output_qty as quantity", "output_uom as uom"], order_by="recipe_name"),
			"suppliers": frappe.get_all("BulkBite Supplier", filters={"enabled": 1}, pluck="name", order_by="name"),
		},
	}


@frappe.whitelist(methods=["GET"])
def get_inventory_snapshot(location=None):
	"""Return ingredient balances and valuation for the worker Inventory view."""
	_require_app_user()
	location = location or "Ingredients"
	items = frappe.get_all(
		"BulkBite Item",
		filters={"item_type": "Ingredient", "track_stock": 1, "enabled": 1},
		fields=["item_code", "item_name", "stock_uom", "theory_valuation_rate"],
		order_by="item_name",
	)
	for item in items:
		item["location"] = location
		item["actual_qty"] = get_available_stock(item.item_code, location)
		item["valuation_rate"] = get_valuation_rate(item.item_code, location)
		item["stock_value"] = item["actual_qty"] * item["valuation_rate"]
	return {"location": location, "items": items}


# endregion FRONTEND SNAPSHOT


# =============================================================================
# region AUXILIARY RECORD FORMS
# =============================================================================

_AUXILIARY_FORM_DOCTYPES = {
	"BulkBite Item": {"label": "Items", "singular_label": "item", "description": "Ingredients, finished meals, packaging, units, scan codes, and theory rates."},
	"BulkBite Supplier": {"label": "Suppliers", "singular_label": "supplier", "description": "Supplier identity and accountant export references."},
	"BulkBite Location": {"label": "Locations", "singular_label": "location", "description": "The physical places where ingredients, meals, quarantine, and waste are measured."},
	"BulkBite Recipe": {"label": "Recipes", "singular_label": "recipe", "description": "Versioned meal theory and controlled ingredient quantities."},
	"BulkBite Production Plan": {"label": "Production plans", "singular_label": "plan", "description": "Planned recipes and meal quantities used by the production workflow."},
}
_AUXILIARY_FIELD_TYPES = {"Data", "Int", "Float", "Currency", "Date", "Select", "Check", "Small Text", "Text", "Long Text", "Link", "Table"}


@frappe.whitelist(methods=["GET"])
def get_auxiliary_form_catalogue():
	"""Return the permission-aware supporting-record destinations used by linked fields."""
	_require_app_user()
	return [
		{
			"doctype": doctype,
			**copy,
			"can_create": frappe.has_permission(doctype, "create"),
			"can_read": frappe.has_permission(doctype, "read"),
		}
		for doctype, copy in _AUXILIARY_FORM_DOCTYPES.items()
		if frappe.has_permission(doctype, "read")
	]


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record_list(doctype):
	"""List one approved supporting DocType through ordinary Frappe permissions."""
	_require_auxiliary_doctype(doctype, "read")
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field or (meta.autoname.removeprefix("field:") if str(meta.autoname or "").startswith("field:") else None)
	fields = ["name"] + ([title_field] if title_field and title_field != "name" else [])
	rows = frappe.get_list(doctype, fields=fields, order_by=f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}", limit_page_length=200)
	return [{"name": row.name, "label": row.get(title_field) or row.name} for row in rows]


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record(doctype, name=None):
	"""Return one safe metadata contract plus values for create or edit."""
	_require_auxiliary_doctype(doctype, "read" if name else "create")
	contract = _auxiliary_form_contract(doctype)
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	if name:
		doc.check_permission("read")
	return {
		"contract": contract,
		"values": {field["name"]: doc.get(field["name"]) for section in contract["sections"] for field in section["fields"]},
		"tables": {table["name"]: [row.as_dict() for row in doc.get(table["name"])] for table in contract["tables"]},
	}


@frappe.whitelist(methods=["POST"])
def save_auxiliary_record(doctype, values, tables=None, name=None):
	"""Create or update only fields exposed by the approved auxiliary contract."""
	_require_auxiliary_doctype(doctype, "write" if name else "create")
	contract = _auxiliary_form_contract(doctype)
	allowed_values = {field["name"] for section in contract["sections"] for field in section["fields"] if not field["read_only"]}
	allowed_tables = {table["name"]: table for table in contract["tables"]}
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.check_permission("write" if name else "create")
	for fieldname, value in _as_dict(values).items():
		if fieldname in allowed_values:
			doc.set(fieldname, value)
	for fieldname, rows in _as_dict(tables).items():
		if fieldname not in allowed_tables:
			continue
		allowed_row_fields = {field["name"] for field in allowed_tables[fieldname]["fields"] if not field["read_only"]}
		doc.set(fieldname, [{key: value for key, value in row.items() if key in allowed_row_fields} for row in _as_list(rows)])
	doc.save()
	return {"doctype": doctype, "name": doc.name}


def _require_auxiliary_doctype(doctype, permission):
	if permission == "read":
		_require_app_user()
	else:
		_require_roles("BulkBite Manager")
	if doctype not in _AUXILIARY_FORM_DOCTYPES:
		frappe.throw(_("{0} is not an approved BulkBite setup record.").format(doctype), frappe.PermissionError)
	if not frappe.has_permission(doctype, permission):
		frappe.throw(_("You do not have permission to {0} {1}.").format(permission, doctype), frappe.PermissionError)


def _auxiliary_form_contract(doctype):
	meta = frappe.get_meta(doctype)
	sections = [{"label": _AUXILIARY_FORM_DOCTYPES[doctype]["singular_label"].title(), "fields": []}]
	tables = []
	for field in meta.fields:
		if field.fieldtype not in _AUXILIARY_FIELD_TYPES or field.hidden or field.fieldtype in {"Section Break", "Column Break"}:
			continue
		serialized = _serialize_auxiliary_field(field)
		if field.fieldtype == "Table":
			child_meta = frappe.get_meta(field.options)
			tables.append({
				"name": field.fieldname,
				"label": field.label,
				"description": field.description or "",
				"fields": [_serialize_auxiliary_field(child) for child in child_meta.fields if child.fieldtype in _AUXILIARY_FIELD_TYPES and child.fieldtype != "Table" and not child.hidden],
			})
		else:
			sections[0]["fields"].append(serialized)
	return {"doctype": doctype, "sections": sections, "tables": tables}


def _serialize_auxiliary_field(field):
	options = [line for line in str(field.options or "").splitlines() if line] if field.fieldtype == "Select" else field.options
	link_options = []
	if field.fieldtype == "Link" and field.options in _AUXILIARY_FORM_DOCTYPES and frappe.has_permission(field.options, "read"):
		link_options = [{"label": row["label"], "value": row["name"]} for row in get_auxiliary_record_list(field.options)]
	return {
		"name": field.fieldname,
		"label": field.label,
		"type": field.fieldtype,
		"options": options,
		"description": field.description or "",
		"required": bool(field.reqd),
		"read_only": bool(field.read_only),
		"non_negative": bool(field.non_negative),
		"default": field.default,
		"link_options": link_options,
	}


# endregion AUXILIARY RECORD FORMS


# =============================================================================
# region ITEM IDENTITY
# =============================================================================


@frappe.whitelist(methods=["GET"])
def resolve_scan_code(code):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	value = str(code or "").strip()
	if not value:
		frappe.throw(_("Scan or enter a QR code or barcode."))
	item_code = value if frappe.db.exists("BulkBite Item", value) else None
	if not item_code:
		for candidate in frappe.get_all(
			"BulkBite Item", filters={"enabled": 1}, fields=["item_code", "scan_codes", "stock_uom"]
		):
			if value in {code.strip() for code in str(candidate.scan_codes or "").splitlines() if code.strip()}:
				item_code = candidate.item_code
				break
	if not item_code:
		frappe.throw(_("No BulkBite item is mapped to code {0}.").format(value))
	item = frappe.db.get_value(
		"BulkBite Item", item_code, ["item_code", "item_name", "stock_uom", "track_stock", "enabled"], as_dict=True
	)
	if not item.enabled:
		frappe.throw(_("Item {0} is disabled.").format(item_code))
	return {**item, "is_stock_item": item.track_stock, "scan_code": value, "uom": item.stock_uom}


# endregion ITEM IDENTITY


# =============================================================================
# region PRODUCTION RUNS
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_recipe_expectation(recipe, planned_output_qty, source_location):
	_require_app_user()
	return load_expected_usage(recipe, planned_output_qty, source_location)


@frappe.whitelist(methods=["POST"])
def create_production_run(payload=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	run = frappe.get_doc({"doctype": "BulkBite Production Run", **data})
	run.insert()
	return _serialize_run(run)


@frappe.whitelist(methods=["POST"])
def update_production_actuals(name, actual_output_qty, ingredients, notes=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus != 0:
		frappe.throw(_("Only a draft production run can be measured."))
	actual_by_item = {row["item_code"]: row for row in _as_list(ingredients)}
	run.actual_output_qty = flt(actual_output_qty)
	run.notes = notes
	for row in run.ingredients:
		actual = actual_by_item.get(row.item_code)
		if actual:
			method = actual.get("measurement_method") or "Used"
			row.measurement_method = method
			if method == "Remaining":
				available = get_available_stock(row.item_code, row.source_location or run.source_location)
				remaining = flt(actual.get("remaining_qty"))
				row.available_before_measurement = available
				row.remaining_qty = remaining
				row.actual_qty = derive_usage_from_remaining(available, remaining)
			else:
				row.remaining_qty = None
				row.available_before_measurement = get_available_stock(row.item_code, row.source_location or run.source_location)
				row.actual_qty = flt(actual.get("actual_qty"))
			row.notes = actual.get("notes")
	run.save()
	return _serialize_run(run)


@frappe.whitelist(methods=["POST"])
def submit_production_run(name):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	run.submit()
	return _serialize_run(run.reload())


@frappe.whitelist(methods=["POST"])
def calculate_variance_preview(expected_qty, actual_qty, valuation_rate=0, planned_output_qty=None, actual_output_qty=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	result = {"usage": calculate_usage_variance(expected_qty, actual_qty, valuation_rate)}
	if planned_output_qty is not None:
		result["output"] = calculate_output_variance(planned_output_qty, actual_output_qty)
	return result


# endregion PRODUCTION RUNS


# =============================================================================
# region PRODUCTION PLANNING
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_production_plan_snapshot(plan_name=None, location=None):
	"""Return planned recipes, expected ingredients, current stock, and shortages."""
	_require_app_user()
	plan_name = plan_name or frappe.db.get_value(
		"BulkBite Production Plan",
		{"status": ("in", ["Relative Draft", "Dated Draft", "Active"])},
		"name",
		order_by="modified desc",
	)
	if not plan_name:
		return None
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	location = location or "Ingredients"
	rows = []
	aggregated = {}
	for plan_row in plan.plan_rows:
		expectation = load_expected_usage(plan_row.recipe, plan_row.planned_output_qty, location)
		ingredients = []
		for ingredient in expectation["ingredients"]:
			available = get_available_stock(ingredient["item_code"], ingredient["source_location"])
			required = flt(ingredient["expected_qty"])
			ingredient.update({"available_qty": available, "shortage_qty": max(required - available, 0)})
			ingredients.append(ingredient)
			total = aggregated.setdefault(
				ingredient["item_code"],
				{
					"item_code": ingredient["item_code"],
					"item_name": ingredient["item_name"],
					"uom": ingredient["uom"],
					"required_qty": 0,
					"available_qty": available,
				},
			)
			total["required_qty"] += required
		rows.append(
			{
				"name": plan_row.name,
				"week_number": plan_row.week_number,
				"planned_date": plan_row.planned_date,
				"finished_item": plan_row.finished_item,
				"finished_item_name": frappe.get_cached_value("BulkBite Item", plan_row.finished_item, "item_name"),
				"recipe": plan_row.recipe,
				"planned_output_qty": plan_row.planned_output_qty,
				"uom": plan_row.uom,
				"expected_material_cost": plan_row.expected_material_cost,
				"ingredients": ingredients,
			}
		)
	for item in aggregated.values():
		item["shortage_qty"] = max(item["required_qty"] - item["available_qty"], 0)
	return {
		"name": plan.name,
		"plan_title": plan.plan_title,
		"status": plan.status,
		"date_note": plan.date_note,
		"location": location,
		"rows": rows,
		"total_requirements": sorted(aggregated.values(), key=lambda item: item["item_name"]),
	}


@frappe.whitelist(methods=["POST"])
def create_run_from_plan(plan_name, plan_row_name, production_date, source_location, target_location):
	"""Turn one planned recipe row into a measurable production draft."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	plan_row = next((row for row in plan.plan_rows if row.name == plan_row_name), None)
	if not plan_row:
		frappe.throw(_("The selected recipe row is not part of production plan {0}.").format(plan.name))
	return create_production_run(
		{
			"production_date": getdate(production_date),
			"business_name": plan.business_name,
			"recipe": plan_row.recipe,
			"planned_output_qty": plan_row.planned_output_qty,
			"actual_output_qty": plan_row.planned_output_qty,
			"source_location": source_location,
			"target_location": target_location,
			"notes": _("Created from production plan {0}, week {1}.").format(plan.name, plan_row.week_number),
		}
	)


# endregion PRODUCTION PLANNING


# =============================================================================
# region PURCHASING AND STOCK DRAFTS
# =============================================================================


@frappe.whitelist(methods=["POST"])
def create_receipt_intake(payload=None):
	"""Store private purchase evidence and manually reviewed lines."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	file_doc = frappe.db.get_value("File", {"file_url": data.get("receipt_file")}, ["name", "is_private"], as_dict=True)
	if not file_doc or not file_doc.is_private:
		frappe.throw(_("Upload the receipt as a private file before saving it."))
	receipt = frappe.get_doc({"doctype": "BulkBite Receipt Intake", **data}).insert()
	frappe.db.set_value(
		"File",
		file_doc.name,
		{"attached_to_doctype": receipt.doctype, "attached_to_name": receipt.name},
		update_modified=False,
	)
	return {
		"name": receipt.name,
		"status": receipt.status,
		"total_amount": receipt.total_amount,
		"stock_events_posted": receipt.stock_events_posted,
	}


@frappe.whitelist(methods=["POST"])
def receive_stock_from_receipt(receipt_name):
	"""Add reviewed receipt quantities to stock exactly once."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	frappe.db.sql("select name from `tabBulkBite Receipt Intake` where name = %s for update", (receipt_name,))
	receipt = frappe.get_doc("BulkBite Receipt Intake", receipt_name)
	if receipt.stock_events_posted:
		return _serialize_received_receipt(receipt)
	if not receipt.items:
		frappe.throw(_("Review at least one receipt line before adding stock."))
	for row in receipt.items:
		event = append_stock_event(
			"Receipt",
			row.item_code,
			row.location or receipt.default_location,
			flt(row.qty),
			flt(row.rate),
			receipt.doctype,
			receipt.name,
			row.name,
		)
		row.db_set("stock_event", event.name, update_modified=False)
	receipt.db_set({"stock_events_posted": 1, "status": "Stock Received"})
	return _serialize_received_receipt(receipt.reload())


@frappe.whitelist(methods=["POST"])
def create_stock_count_draft(payload=None):
	"""Create a custom physical-count draft without changing stock."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	doc = frappe.get_doc(
		{
			"doctype": "BulkBite Stock Audit",
			"audit_date": getdate(data.get("posting_date")),
			"source_document": data.get("source_document"),
			"notes": data.get("notes"),
		}
	)
	for row in _as_list(data.get("items")):
		doc.append(
			"items",
			{
				"item_code": row.get("item_code"),
				"location": row.get("location"),
				"counted_qty": flt(row.get("qty")),
			},
		)
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus}


# endregion PURCHASING AND STOCK DRAFTS


# =============================================================================
# region AUDIT APPROVAL AND ACCOUNTANT EXPORT
# =============================================================================


@frappe.whitelist(methods=["POST"])
def approve_stock_audit(name):
	"""Approve one reviewed physical count and append only its variances."""
	_require_roles("BulkBite Manager")
	audit = frappe.get_doc("BulkBite Stock Audit", name)
	if audit.docstatus == 1:
		return {"doctype": audit.doctype, "name": audit.name, "docstatus": audit.docstatus}
	audit.status = "Approved"
	audit.submit()
	return {"doctype": audit.doctype, "name": audit.name, "docstatus": audit.docstatus}


@frappe.whitelist(methods=["GET"])
def get_accountant_export(from_date, to_date):
	"""Return approved operational truth for an accountant. This station never changes stock."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	start = getdate(from_date)
	end = getdate(to_date)
	if start > end:
		frappe.throw(_("From date must be on or before to date."))
	receipts = frappe.get_all(
		"BulkBite Receipt Intake",
		filters={"invoice_date": ["between", [start, end]], "stock_events_posted": 1},
		fields=[
			"name",
			"invoice_date",
			"supplier",
			"supplier_invoice_number",
			"currency",
			"subtotal_amount",
			"tax_amount",
			"total_amount",
			"accounting_category",
		],
		order_by="invoice_date asc, name asc",
	)
	stock_events = frappe.get_all(
		"BulkBite Stock Event",
		filters={"posting_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]},
		fields=[
			"event_sequence",
			"posting_datetime",
			"event_type",
			"item_code",
			"location",
			"quantity_delta",
			"uom",
			"unit_cost",
			"value_delta",
			"reference_doctype",
			"reference_name",
			"actor",
			"event_hash",
		],
		order_by="event_sequence asc",
	)
	balances = frappe.get_all(
		"BulkBite Stock Balance",
		fields=["item_code", "location", "actual_qty", "uom", "valuation_rate", "stock_value", "last_event"],
		order_by="item_code asc, location asc",
	)
	return {
		"period": {"from_date": start, "to_date": end, "currency": "ZAR"},
		"receipts": receipts,
		"stock_events": stock_events,
		"closing_stock": balances,
		"note": _("Operational export only. The accountant assigns accounts, tax treatment, and journal entries."),
	}


@frappe.whitelist(methods=["GET"])
def download_accountant_export(from_date, to_date, dataset="receipts"):
	"""Download one accountant dataset as CSV without altering export state."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	data = get_accountant_export(from_date, to_date)
	if dataset not in {"receipts", "stock_events", "closing_stock"}:
		frappe.throw(_("Choose receipts, stock_events, or closing_stock."))
	rows = data[dataset]
	stream = io.StringIO()
	fieldnames = list(rows[0].keys()) if rows else ["no_records"]
	writer = csv.DictWriter(stream, fieldnames=fieldnames)
	writer.writeheader()
	if rows:
		writer.writerows(rows)
	frappe.response.filename = f"bulkbite-{dataset}-{getdate(from_date)}-to-{getdate(to_date)}.csv"
	frappe.response.filecontent = stream.getvalue()
	frappe.response.type = "download"


# endregion AUDIT APPROVAL AND ACCOUNTANT EXPORT


# =============================================================================
# region SPREADSHEET INTAKE
# =============================================================================


@frappe.whitelist(methods=["POST"])
def preview_theory_workbook(file_url):
	"""Read workbook structure for mapping. This station never writes records."""
	_require_roles("BulkBite Manager")
	file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name", "is_private"], as_dict=True)
	if not file_doc:
		frappe.throw(_("Upload the spreadsheet before previewing it."))
	path = Path(frappe.get_site_path("private" if file_doc.is_private else "public", "files", file_doc.file_name))
	if path.suffix.lower() not in {".xlsx", ".xlsm"}:
		frappe.throw(_("Use an .xlsx or .xlsm workbook for the first import pass."))
	workbook = load_workbook(path, read_only=True, data_only=True)
	return {
		"file_name": file_doc.file_name,
		"sheets": [_preview_sheet(sheet) for sheet in workbook.worksheets],
		"next_step": "Map recipe, ingredient, quantity, unit, yield, and date columns before importing theory.",
	}


def _preview_sheet(sheet):
	rows = list(sheet.iter_rows(min_row=1, max_row=8, values_only=True))
	return {
		"name": sheet.title,
		"max_row": sheet.max_row,
		"max_column": sheet.max_column,
		"headers": [_cell(value) for value in (rows[0] if rows else [])],
		"sample_rows": [[_cell(value) for value in row] for row in rows[1:]],
	}


def _cell(value):
	return value.isoformat() if hasattr(value, "isoformat") else value


# endregion SPREADSHEET INTAKE


# =============================================================================
# region WORKER DOCUMENT INTAKE
# =============================================================================


@frappe.whitelist(methods=["POST"])
def create_document_extraction_draft(payload=None):
	"""Store source evidence and OCR-derived rows for human review only."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	file_doc, source_hash = resolve_private_source(data.get("source_file"))
	existing = frappe.db.get_value("BulkBite Document Intake", {"source_hash": source_hash}, "name")
	if existing:
		frappe.throw(_("This document was already uploaded as {0}.").format(existing))
	raw_text = str(data.get("raw_text") or "").strip()
	if not raw_text:
		frappe.throw(_("OCR text is required. The source document is retained, but image analysis is not enabled in this environment."))
	rows = extract_measurement_rows(raw_text)
	if not rows:
		frappe.throw(_("No measurement lines were found in the supplied text."))
	warnings = [row["warning"] for row in rows if row.get("warning")]
	doc = frappe.get_doc(
		{
			"doctype": "BulkBite Document Intake",
			"status": "Needs Review" if warnings else "Extracted Draft",
			"document_type": data.get("document_type"),
			"source_file": data.get("source_file"),
			"source_hash": source_hash,
			"business_name": data.get("business_name") or "BulkBite",
			"production_run": data.get("production_run"),
			"default_location": data.get("default_location"),
			"raw_text": raw_text,
			"rows": rows,
			"warnings": "\n".join(dict.fromkeys(warnings)),
		}
	).insert()
	frappe.db.set_value("File", file_doc.name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}, update_modified=False)
	return _serialize_document_intake(doc)


@frappe.whitelist(methods=["POST"])
def review_document_extraction(name, rows):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	doc = frappe.get_doc("BulkBite Document Intake", name)
	if doc.status == "Applied":
		frappe.throw(_("Applied document measurements cannot be reviewed again."))
	approved_rows = _as_list(rows)
	if not approved_rows:
		frappe.throw(_("Keep at least one reviewed measurement row."))
	doc.set("rows", approved_rows)
	doc.status = "Reviewed"
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = now_datetime()
	doc.save()
	return _serialize_document_intake(doc)


@frappe.whitelist(methods=["POST"])
def apply_document_measurements(name):
	"""Apply reviewed rows to a production draft or create an audit draft. Never submit an audit."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	doc = frappe.get_doc("BulkBite Document Intake", name)
	if doc.status != "Reviewed":
		frappe.throw(_("Review and approve the extracted rows before applying them."))
	rows = [row for row in doc.rows if row.accepted]
	if not rows:
		frappe.throw(_("Approve at least one extracted row."))
	if doc.document_type == "Stock Audit":
		result = create_stock_count_draft(
			{
				"posting_date": getdate(),
				"source_document": doc.name,
				"items": [
					{"item_code": row.item_code, "location": doc.default_location, "qty": row.qty}
					for row in rows
				],
			}
		)
	else:
		run = frappe.get_doc("BulkBite Production Run", doc.production_run)
		by_item = {row.item_code: row for row in rows}
		measurements = []
		for usage in run.ingredients:
			extracted = by_item.get(usage.item_code)
			method = (
				"Remaining"
				if extracted and doc.document_type == "Remaining Stock Sheet"
				else "Used"
				if extracted and doc.document_type == "Usage Sheet"
				else usage.measurement_method or "Used"
			)
			measurements.append(
				{
					"item_code": usage.item_code,
					"actual_qty": extracted.qty if extracted and doc.document_type == "Usage Sheet" else usage.actual_qty,
					"remaining_qty": extracted.qty if extracted and doc.document_type == "Remaining Stock Sheet" else usage.remaining_qty,
					"measurement_method": method,
					"notes": _("Reviewed from worker document {0}").format(doc.name) if extracted else usage.notes,
				}
			)
		result = update_production_actuals(run.name, run.actual_output_qty, measurements, run.notes)
		result = {"doctype": "BulkBite Production Run", "name": result["name"], "docstatus": result["docstatus"]}
	doc.db_set({"status": "Applied", "applied_reference_doctype": result["doctype"], "applied_reference": result["name"]})
	return result


def _serialize_document_intake(doc):
	return {
		"name": doc.name,
		"status": doc.status,
		"document_type": doc.document_type,
		"warnings": doc.warnings,
		"rows": [row.as_dict() for row in doc.rows],
		"applied_reference_doctype": doc.applied_reference_doctype,
		"applied_reference": doc.applied_reference,
	}


# endregion WORKER DOCUMENT INTAKE


# =============================================================================
# region API BOUNDARIES
# =============================================================================


def _require_app_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to use BulkBite."), frappe.PermissionError)
	allowed_roles = {"System Manager", "BulkBite Worker", "BulkBite Manager", "BulkBite Accountant"}
	if frappe.session.user != "Administrator" and not allowed_roles.intersection(frappe.get_roles()):
		frappe.throw(_("Your account does not have a BulkBite operations role."), frappe.PermissionError)


def _require_roles(*roles):
	"""Authorize one API station without broadening document permissions."""
	_require_app_user()
	if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
		return
	if not set(roles).intersection(frappe.get_roles()):
		frappe.throw(_("Your BulkBite role cannot perform this action."), frappe.PermissionError)


def _as_dict(value):
	if isinstance(value, str):
		value = json.loads(value)
	return frappe._dict(value or {})


def _as_list(value):
	if isinstance(value, str):
		value = json.loads(value)
	return value or []


def _serialize_run(run):
	return {
		"name": run.name,
		"docstatus": run.docstatus,
		"production_date": run.production_date,
		"business_name": run.business_name,
		"recipe": run.recipe,
		"finished_item": run.finished_item,
		"planned_output_qty": run.planned_output_qty,
		"actual_output_qty": run.actual_output_qty,
		"output_variance_qty": run.output_variance_qty,
		"output_variance_percent": run.output_variance_percent,
		"expected_material_cost": run.expected_material_cost,
		"actual_material_cost": run.actual_material_cost,
		"material_cost_variance": run.material_cost_variance,
		"output_stock_event": run.output_stock_event,
		"truth_event": run.truth_event,
		"ingredients": [row.as_dict() for row in run.ingredients],
	}


def _serialize_received_receipt(doc):
	return {
		"doctype": "BulkBite Receipt Intake",
		"name": doc.name,
		"docstatus": 1 if doc.stock_events_posted else 0,
		"total_qty": sum(flt(row.qty) for row in doc.items),
		"grand_total": doc.total_amount,
	}


def _current_valuation_rate(item_code, location):
	return get_valuation_rate(item_code, location)


# endregion API BOUNDARIES
