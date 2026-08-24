from __future__ import annotations

from io import BytesIO
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from bulkbite.pricing import supplier_offer_key


# =============================================================================
# region WORKBOOK EXPORT
# =============================================================================


OFFER_HEADERS = [
	"offer_id", "offer_key", "item_code", "item_name", "item_category", "stock_uom", "supplier",
	"supplier_item_code", "units_per_pack", "unit_size", "purchase_uom", "stock_qty_per_pack",
	"normal_pack_price", "discounted_pack_price", "discount_from", "discount_to", "effective_from",
	"effective_to", "currency", "price_includes_vat", "vat_rate", "price_source", "source_date",
	"last_verified_on", "preferred", "enabled", "notes",
]


def build_price_workbook():
	"""Create a ChatGPT-safe workbook with exact names and stable record identifiers."""
	workbook = Workbook()
	instructions = workbook.active
	instructions.title = "Instructions"
	instructions.append(["BulkBite price catalogue exchange"])
	instructions.append(["Edit price and pack fields only. Keep offer_id, offer_key, item_code, and exact item_name unchanged."])
	instructions.append(["Add a row for a new supplier offer using an existing item_code and exact supplier name. Leave offer_id blank."])
	instructions.append(["Uploading this workbook updates pricing theory only. It never changes stock or creates receipt evidence."])
	instructions.append(["All monetary values use ZAR. Enter VAT as a percentage, for example 15."])
	items = workbook.create_sheet("Items and Current Prices")
	items.append(OFFER_HEADERS)
	item_map = {row.item_code: row for row in frappe.get_all("BulkBite Item", fields=["item_code", "item_name", "item_category", "stock_uom"], order_by="item_name asc")}
	offers = frappe.get_all("BulkBite Supplier Offer", fields=["*"], order_by="item_code asc, supplier asc, effective_from desc")
	for offer in offers:
		item = item_map.get(offer.item_code, frappe._dict())
		items.append([
			offer.name, offer.offer_key or supplier_offer_key(offer.item_code, offer.supplier, offer.supplier_item_code),
			offer.item_code, item.item_name, item.item_category, item.stock_uom, offer.supplier,
			offer.supplier_item_code, offer.units_per_pack, offer.unit_size, offer.purchase_uom,
			offer.stock_qty_per_pack, offer.normal_price, offer.discounted_price, offer.discount_from,
			offer.discount_to, offer.effective_from, offer.effective_to, offer.currency or "ZAR",
			bool(offer.price_includes_vat), offer.vat_rate, offer.price_source, offer.source_date,
			offer.last_verified_on, bool(offer.preferred), bool(offer.enabled), offer.notes,
		])
	for item in item_map.values():
		if not any(row.item_code == item.item_code for row in offers):
			items.append([None, None, item.item_code, item.item_name, item.item_category, item.stock_uom])
	_suppliers_sheet(workbook)
	_adjustment_sheet(workbook)
	_cost_rules_sheet(workbook)
	_style_workbook(workbook)
	stream = BytesIO()
	workbook.save(stream)
	return stream.getvalue()


def _suppliers_sheet(workbook):
	sheet = workbook.create_sheet("Suppliers")
	sheet.append(["supplier", "enabled", "accountant_reference", "vat_or_tax_reference"])
	for row in frappe.get_all("BulkBite Supplier", fields=["name", "enabled", "accountant_reference", "tax_reference"], order_by="name asc"):
		sheet.append([row.name, bool(row.enabled), row.accountant_reference, row.tax_reference])


def _adjustment_sheet(workbook):
	sheet = workbook.create_sheet("Adjustments")
	fields = ["adjustment_code", "adjustment_name", "scope_type", "supplier_offer", "supplier", "item_code", "item_category", "adjustment_type", "calculation_basis", "value", "threshold_amount", "effective_from", "effective_to", "priority", "stackable", "vat_treatment", "enabled", "notes"]
	sheet.append(fields)
	for row in frappe.get_all("BulkBite Price Adjustment", fields=fields, order_by="priority asc, name asc"):
		sheet.append([row.get(field) for field in fields])


def _cost_rules_sheet(workbook):
	sheet = workbook.create_sheet("Operating Costs")
	fields = ["cost_code", "cost_name", "cost_category", "basis", "rate", "default_quantity", "effective_from", "effective_to", "vat_treatment", "accounting_category", "payee", "enabled", "notes"]
	sheet.append(fields)
	for row in frappe.get_all("BulkBite Operating Cost Rule", fields=fields, order_by="cost_category asc, cost_name asc"):
		sheet.append([row.get(field) for field in fields])


def _style_workbook(workbook):
	for sheet in workbook.worksheets:
		sheet.freeze_panes = "A2"
		sheet.auto_filter.ref = sheet.dimensions if sheet.max_column > 1 else None
		for cell in sheet[1]:
			cell.font = Font(bold=True, color="FFFFFF")
			cell.fill = PatternFill("solid", fgColor="252522")
			cell.alignment = Alignment(wrap_text=True)
		for column in sheet.columns:
			letter = column[0].column_letter
			sheet.column_dimensions[letter].width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 32)


# endregion WORKBOOK EXPORT


# =============================================================================
# region WORKBOOK PREVIEW AND APPLY
# =============================================================================


def preview_price_workbook(file_url):
	"""Parse workbook changes into an auditable batch without changing catalogue records."""
	path = _private_file_path(file_url)
	workbook = load_workbook(path, read_only=True, data_only=True)
	if "Items and Current Prices" not in workbook.sheetnames:
		frappe.throw(_("The workbook needs an Items and Current Prices sheet."))
	rows = _sheet_dicts(workbook["Items and Current Prices"])
	preview_rows = [_preview_offer(row, index + 2) for index, row in enumerate(rows) if any(value not in (None, "") for value in row.values())]
	adjustments = _preview_named_rows(workbook, "Adjustments", "BulkBite Price Adjustment", "adjustment_code")
	cost_rules = _preview_named_rows(workbook, "Operating Costs", "BulkBite Operating Cost Rule", "cost_code")
	all_rows = preview_rows + adjustments + cost_rules
	counts = {status: sum(1 for row in all_rows if row["status"] == status) for status in ("insert", "update", "unchanged", "error")}
	batch = frappe.get_doc({
		"doctype": "BulkBite Price Import Batch", "source_file": file_url, "status": "Previewed",
		"total_rows": len(all_rows), "insert_count": counts["insert"], "update_count": counts["update"],
		"unchanged_count": counts["unchanged"], "error_count": counts["error"],
		"preview_json": frappe.as_json({"offers": preview_rows, "adjustments": adjustments, "cost_rules": cost_rules}),
	}).insert()
	return _batch_response(batch)


def apply_price_workbook(batch_name):
	"""Apply one reviewed batch idempotently, preserving supplier price history."""
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		return _batch_response(batch)
	preview = frappe.parse_json(batch.preview_json)
	if batch.error_count:
		frappe.throw(_("Fix workbook errors and upload a new preview before applying."))
	result = {"inserted": [], "updated": [], "unchanged": []}
	for row in preview.get("offers") or []:
		_apply_offer_row(row, result)
	for key, doctype in (("adjustments", "BulkBite Price Adjustment"), ("cost_rules", "BulkBite Operating Cost Rule")):
		for row in preview.get(key) or []:
			_apply_named_row(doctype, row, result)
	batch.db_set({"status": "Applied", "applied_on": frappe.utils.now_datetime(), "applied_by": frappe.session.user, "result_json": frappe.as_json(result)})
	return _batch_response(frappe.get_doc(batch.doctype, batch.name))


def _preview_offer(row, row_number):
	errors = []
	item_code = _text(row.get("item_code"))
	supplier = _text(row.get("supplier"))
	if not supplier and not any(row.get(field) not in (None, "") for field in ("units_per_pack", "unit_size", "purchase_uom", "normal_pack_price", "discounted_pack_price")):
		exact_name = frappe.db.get_value("BulkBite Item", item_code, "item_name") if item_code else None
		reference_errors = [] if exact_name and _text(row.get("item_name")) == exact_name else ["Keep the exported item_code and exact item_name together."]
		return {"kind": "Item Reference", "row_number": row_number, "status": "error" if reference_errors else "unchanged", "record_name": item_code, "item_code": item_code, "item_name": exact_name or _text(row.get("item_name")), "supplier": "", "changes": [], "errors": reference_errors, "values": {}}
	if not item_code or not frappe.db.exists("BulkBite Item", item_code):
		errors.append("Use an existing item_code from this workbook.")
	exact_name = frappe.db.get_value("BulkBite Item", item_code, "item_name") if item_code else None
	if exact_name and _text(row.get("item_name")) != exact_name:
		errors.append("item_name must stay exactly as exported.")
	if not supplier or not frappe.db.exists("BulkBite Supplier", supplier):
		errors.append("Use an existing supplier name from the Suppliers sheet.")
	for field in ("units_per_pack", "unit_size", "normal_pack_price"):
		if flt(row.get(field)) <= 0:
			errors.append(f"{field} must be greater than zero.")
	if row.get("purchase_uom") not in {"g", "Kg", "ml", "Litre", "Each"}:
		errors.append("purchase_uom must be g, Kg, ml, Litre, or Each.")
	offer_id = _text(row.get("offer_id"))
	existing = frappe.get_doc("BulkBite Supplier Offer", offer_id) if offer_id and frappe.db.exists("BulkBite Supplier Offer", offer_id) else None
	values = _offer_values(row)
	if existing and (existing.item_code != item_code or existing.supplier != supplier):
		errors.append("offer_id does not belong to this item and supplier.")
	status = "error" if errors else ("insert" if not existing else ("unchanged" if _same_values(existing, values) else "update"))
	return {"kind": "Supplier Offer", "row_number": row_number, "status": status, "record_name": offer_id, "item_code": item_code, "item_name": exact_name or _text(row.get("item_name")), "supplier": supplier, "changes": _changes(existing, values), "errors": errors, "values": values}


def _preview_named_rows(workbook, sheet_name, doctype, key_field):
	if sheet_name not in workbook.sheetnames:
		return []
	result = []
	meta = frappe.get_meta(doctype)
	allowed = {field.fieldname for field in meta.fields if field.fieldtype not in {"Section Break", "Column Break"} and not field.read_only}
	for index, row in enumerate(_sheet_dicts(workbook[sheet_name]), 2):
		if not any(value not in (None, "") for value in row.values()):
			continue
		key = _text(row.get(key_field))
		errors = [] if key else [f"{key_field} is required."]
		values = {field: row.get(field) for field in allowed if field in row}
		existing_name = frappe.db.get_value(doctype, {key_field: key}, "name") if key else None
		existing = frappe.get_doc(doctype, existing_name) if existing_name else None
		status = "error" if errors else ("insert" if not existing else ("unchanged" if _same_values(existing, values) else "update"))
		result.append({"kind": doctype.removeprefix("BulkBite "), "row_number": index, "status": status, "record_name": existing_name, "label": row.get(key_field), "changes": _changes(existing, values), "errors": errors, "values": values})
	return result


def _apply_offer_row(row, result):
	if row["status"] == "unchanged":
		result["unchanged"].append(row.get("record_name"))
		return
	values = row["values"]
	if row["status"] == "update":
		old = frappe.get_doc("BulkBite Supplier Offer", row["record_name"])
		material_fields = {"item_code", "supplier", "supplier_item_code", "effective_from", "effective_to", "units_per_pack", "unit_size", "purchase_uom", "normal_price", "discounted_price", "discount_from", "discount_to", "price_includes_vat", "vat_rate"}
		if not material_fields.intersection(change["field"] for change in row.get("changes") or []):
			old.update(values)
			old.save()
			result["updated"].append(old.name)
			return
		new_start = getdate(values["effective_from"])
		if not old.effective_to or getdate(old.effective_to) >= new_start:
			old.db_set({"effective_to": add_days(new_start, -1), "enabled": 0})
		values["notes"] = "Imported replacement for " + old.name + (f". {values.get('notes')}" if values.get("notes") else "")
	doc = frappe.get_doc({"doctype": "BulkBite Supplier Offer", **values}).insert()
	result["updated" if row["status"] == "update" else "inserted"].append(doc.name)


def _apply_named_row(doctype, row, result):
	if row["status"] == "unchanged":
		result["unchanged"].append(row.get("record_name"))
		return
	doc = frappe.get_doc(doctype, row["record_name"]) if row["record_name"] else frappe.new_doc(doctype)
	doc.update(row["values"])
	doc.save()
	result["updated" if row["record_name"] else "inserted"].append(doc.name)


def _offer_values(row):
	return {
		"item_code": _text(row.get("item_code")), "supplier": _text(row.get("supplier")),
		"supplier_item_code": _text(row.get("supplier_item_code")), "effective_from": row.get("effective_from") or nowdate(),
		"effective_to": row.get("effective_to"), "units_per_pack": flt(row.get("units_per_pack")),
		"unit_size": flt(row.get("unit_size")), "purchase_uom": row.get("purchase_uom"),
		"normal_price": flt(row.get("normal_pack_price")), "discounted_price": flt(row.get("discounted_pack_price")),
		"discount_from": row.get("discount_from"), "discount_to": row.get("discount_to"),
		"currency": row.get("currency") or "ZAR", "price_includes_vat": _bool(row.get("price_includes_vat")),
		"vat_rate": flt(row.get("vat_rate")), "price_source": row.get("price_source"), "source_date": row.get("source_date"),
		"last_verified_on": row.get("last_verified_on") or nowdate(), "preferred": _bool(row.get("preferred")),
		"enabled": _bool(row.get("enabled"), True), "notes": row.get("notes"),
	}


def _same_values(doc, values):
	return not _changes(doc, values)


def _changes(doc, values):
	if not doc:
		return [{"field": field, "before": None, "after": value} for field, value in values.items() if value not in (None, "")]
	changes = []
	for field, value in values.items():
		before = doc.get(field)
		if _comparable(before) != _comparable(value):
			changes.append({"field": field, "before": before, "after": value})
	return changes


def _batch_response(batch):
	preview = frappe.parse_json(batch.preview_json) if batch.preview_json else {"offers": [], "adjustments": [], "cost_rules": []}
	return {"name": batch.name, "status": batch.status, "counts": {"total": batch.total_rows, "insert": batch.insert_count, "update": batch.update_count, "unchanged": batch.unchanged_count, "error": batch.error_count}, "rows": [*preview.get("offers", []), *preview.get("adjustments", []), *preview.get("cost_rules", [])], "result": frappe.parse_json(batch.result_json) if batch.result_json else None}


def _private_file_path(file_url):
	file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True)
	if not file_doc:
		frappe.throw(_("Upload the workbook before previewing it."))
	path = Path(frappe.get_site_path("private" if file_doc.is_private else "public", "files", file_doc.file_name))
	if path.suffix.lower() not in {".xlsx", ".xlsm"}:
		frappe.throw(_("Upload an .xlsx or .xlsm workbook."))
	return path


def _sheet_dicts(sheet):
	rows = sheet.iter_rows(values_only=True)
	headers = [_text(value) for value in next(rows, [])]
	return [{headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index]} for row in rows]


def _text(value):
	return str(value or "").strip()


def _bool(value, default=False):
	if value in (None, ""):
		return int(default)
	return int(str(value).strip().lower() in {"1", "true", "yes", "y"})


def _comparable(value):
	if hasattr(value, "isoformat"):
		return value.isoformat()
	if isinstance(value, float):
		return round(value, 6)
	return "" if value is None else str(value)


# endregion WORKBOOK PREVIEW AND APPLY
