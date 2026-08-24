from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate
from openpyxl import Workbook, load_workbook

from bulkbite.pricing import supplier_offer_key


# =============================================================================
# region FLAT PRICE CATALOGUE CONTRACT
# =============================================================================


PRICE_FIELDS = [
	{"fieldname": "offer_id", "label": "Offer ID", "aliases": ["id", "name", "record id"], "identity": True},
	{"fieldname": "offer_key", "label": "Offer Key", "aliases": ["key"], "identity": True},
	{"fieldname": "item_code", "label": "Item Code", "aliases": ["item id", "product code"], "identity": True},
	{"fieldname": "item_name", "label": "Item Name", "aliases": ["item", "product", "product name"], "identity": True},
	{"fieldname": "supplier", "label": "Supplier", "aliases": ["shop", "store", "vendor"]},
	{"fieldname": "supplier_item_code", "label": "Supplier Item Code", "aliases": ["supplier sku", "sku", "barcode"]},
	{"fieldname": "units_per_pack", "label": "Units per Pack", "aliases": ["pack count", "inner units"]},
	{"fieldname": "unit_size", "label": "Size per Unit", "aliases": ["unit size", "size"]},
	{"fieldname": "purchase_uom", "label": "Size Unit", "aliases": ["uom", "unit", "purchase unit"]},
	{"fieldname": "normal_pack_price", "label": "Normal Pack Price", "aliases": ["normal price", "base price", "price"]},
	{"fieldname": "discounted_pack_price", "label": "Discounted Pack Price", "aliases": ["discount price", "sale price"]},
	{"fieldname": "discount_from", "label": "Discount From", "aliases": ["sale from"]},
	{"fieldname": "discount_to", "label": "Discount To", "aliases": ["sale to"]},
	{"fieldname": "effective_from", "label": "Price Effective From", "aliases": ["effective from", "price date"]},
	{"fieldname": "effective_to", "label": "Price Effective To", "aliases": ["effective to"]},
	{"fieldname": "currency", "label": "Currency", "aliases": []},
	{"fieldname": "price_includes_vat", "label": "Price Includes VAT", "aliases": ["vat included", "includes vat"]},
	{"fieldname": "vat_rate", "label": "VAT Rate", "aliases": ["vat", "vat percent"]},
	{"fieldname": "price_source", "label": "Price Source", "aliases": ["source"]},
	{"fieldname": "source_date", "label": "Source Date", "aliases": []},
	{"fieldname": "last_verified_on", "label": "Last Verified On", "aliases": ["verified date", "checked on"]},
	{"fieldname": "preferred", "label": "Preferred Offer", "aliases": ["preferred"]},
	{"fieldname": "enabled", "label": "Enabled", "aliases": ["active"]},
	{"fieldname": "notes", "label": "Notes", "aliases": ["note", "comments"]},
]

DEFAULT_PRICE_FIELDS = [
	"offer_id", "item_code", "item_name", "supplier", "supplier_item_code", "units_per_pack",
	"unit_size", "purchase_uom", "normal_pack_price", "discounted_pack_price", "discount_from",
	"discount_to", "price_includes_vat", "vat_rate", "last_verified_on", "notes",
]

_FIELD_BY_NAME = {field["fieldname"]: field for field in PRICE_FIELDS}


def get_price_field_contract():
	"""Return selectable flat-catalogue fields for the Vue import and export workflow."""
	return {
		"fields": [{**field, "selected_by_default": field["fieldname"] in DEFAULT_PRICE_FIELDS} for field in PRICE_FIELDS],
		"default_fields": DEFAULT_PRICE_FIELDS,
		"matching_note": _("Keep Offer ID when updating existing offers. Item Code, Item Name, and Supplier can identify a new offer."),
	}


# endregion FLAT PRICE CATALOGUE CONTRACT


# =============================================================================
# region FLAT CATALOGUE EXPORT
# =============================================================================


def build_price_workbook(fields=None):
	"""Create one plain sheet containing only the selected columns and catalogue data."""
	selected = _selected_fields(fields)
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "Price Catalogue"
	sheet.append([_FIELD_BY_NAME[field]["label"] for field in selected])
	for row in _catalogue_rows():
		sheet.append([row.get(field) for field in selected])
	stream = BytesIO()
	workbook.save(stream)
	return stream.getvalue()


def _selected_fields(fields):
	if isinstance(fields, str):
		fields = frappe.parse_json(fields)
	selected = [field for field in (fields or DEFAULT_PRICE_FIELDS) if field in _FIELD_BY_NAME]
	if not selected:
		frappe.throw(_("Choose at least one catalogue field."))
	return list(dict.fromkeys(selected))


def _catalogue_rows():
	items = {row.item_code: row for row in frappe.get_all("BulkBite Item", filters={"purchasable": 1, "enabled": 1}, fields=["item_code", "item_name"], order_by="item_name asc")}
	offers = frappe.get_all("BulkBite Supplier Offer", fields=["*"], order_by="item_code asc, supplier asc, effective_from desc")
	rows = []
	for offer in offers:
		item = items.get(offer.item_code, frappe._dict())
		rows.append({
			"offer_id": offer.name,
			"offer_key": offer.offer_key or supplier_offer_key(offer.item_code, offer.supplier, offer.supplier_item_code),
			"item_code": offer.item_code,
			"item_name": item.item_name or offer.item_code,
			"supplier": offer.supplier,
			"supplier_item_code": offer.supplier_item_code,
			"units_per_pack": offer.units_per_pack,
			"unit_size": offer.unit_size,
			"purchase_uom": offer.purchase_uom,
			"normal_pack_price": offer.normal_price,
			"discounted_pack_price": offer.discounted_price,
			"discount_from": offer.discount_from,
			"discount_to": offer.discount_to,
			"effective_from": offer.effective_from,
			"effective_to": offer.effective_to,
			"currency": offer.currency or "ZAR",
			"price_includes_vat": bool(offer.price_includes_vat),
			"vat_rate": offer.vat_rate,
			"price_source": offer.price_source,
			"source_date": offer.source_date,
			"last_verified_on": offer.last_verified_on,
			"preferred": bool(offer.preferred),
			"enabled": bool(offer.enabled),
			"notes": offer.notes,
		})
	offer_items = {row.item_code for row in offers}
	for item in items.values():
		if item.item_code not in offer_items:
			rows.append({"item_code": item.item_code, "item_name": item.item_name, "currency": "ZAR", "enabled": True})
	return rows


# endregion FLAT CATALOGUE EXPORT


# =============================================================================
# region FIELD MAPPING AND IMPORT PREVIEW
# =============================================================================


def inspect_price_import(file_url):
	"""Read source columns and suggest field matches without writing catalogue records."""
	headers, rows = _read_flat_file(file_url)
	return {
		"file_url": file_url,
		"source_columns": [{"column": header, "samples": [_display(row.get(header)) for row in rows[:3] if row.get(header) not in (None, "")]} for header in headers],
		"target_fields": [{"label": field["label"], "value": field["fieldname"]} for field in PRICE_FIELDS],
		"suggested_mapping": {header: _suggest_field(header) for header in headers},
		"row_count": len(rows),
	}


def preview_price_import(file_url, mapping=None):
	"""Create an auditable supplier-offer preview from a reviewed source-to-target field map."""
	headers, source_rows = _read_flat_file(file_url)
	mapping = frappe.parse_json(mapping) if isinstance(mapping, str) else (mapping or {})
	valid_mapping = {source: target for source, target in mapping.items() if source in headers and target in _FIELD_BY_NAME}
	if not valid_mapping:
		frappe.throw(_("Match at least one spreadsheet column to a catalogue field."))
	rows = []
	for index, source in enumerate(source_rows, 2):
		mapped = {target: source.get(column) for column, target in valid_mapping.items()}
		if any(value not in (None, "") for value in mapped.values()):
			rows.append(_preview_offer(mapped, index))
	counts = {status: sum(1 for row in rows if row["status"] == status) for status in ("insert", "update", "unchanged", "error")}
	batch = frappe.get_doc({
		"doctype": "BulkBite Price Import Batch", "source_file": file_url, "status": "Previewed",
		"total_rows": len(rows), "insert_count": counts["insert"], "update_count": counts["update"],
		"unchanged_count": counts["unchanged"], "error_count": counts["error"],
		"preview_json": frappe.as_json({"offers": rows, "mapping": valid_mapping}),
	}).insert()
	return _batch_response(batch)


def _suggest_field(header):
	needle = _normalize_header(header)
	for field in PRICE_FIELDS:
		candidates = [field["fieldname"], field["label"], *field.get("aliases", [])]
		if needle in {_normalize_header(candidate) for candidate in candidates}:
			return field["fieldname"]
	return ""


def _preview_offer(row, row_number):
	errors = []
	offer_id = _text(row.get("offer_id"))
	existing = frappe.get_doc("BulkBite Supplier Offer", offer_id) if offer_id and frappe.db.exists("BulkBite Supplier Offer", offer_id) else None
	item_code = _text(row.get("item_code")) or (existing.item_code if existing else "")
	supplier = _text(row.get("supplier")) or (existing.supplier if existing else "")
	supplier_item_code = _text(row.get("supplier_item_code")) or (existing.supplier_item_code if existing else "")
	if not existing and item_code and supplier:
		key = supplier_offer_key(item_code, supplier, supplier_item_code)
		existing_name = frappe.db.get_value("BulkBite Supplier Offer", {"offer_key": key, "enabled": 1}, "name")
		existing = frappe.get_doc("BulkBite Supplier Offer", existing_name) if existing_name else None
		offer_id = existing_name or offer_id
	if not item_code or not frappe.db.exists("BulkBite Item", item_code):
		errors.append("Match Item Code to an existing BulkBite item.")
	exact_name = frappe.db.get_value("BulkBite Item", item_code, "item_name") if item_code else None
	if row.get("item_name") and exact_name and _text(row.get("item_name")) != exact_name:
		errors.append("Item Name does not match the selected Item Code.")
	if not existing and _is_item_reference_row(row):
		return {
			"kind": "Item Reference", "row_number": row_number, "status": "error" if errors else "unchanged",
			"record_name": item_code, "item_code": item_code, "item_name": exact_name or _text(row.get("item_name")),
			"supplier": "", "changes": [], "errors": errors, "values": {},
		}
	if not supplier or not frappe.db.exists("BulkBite Supplier", supplier):
		errors.append("Match Supplier to an existing BulkBite supplier.")
	values = _offer_values(row, existing)
	for field in ("units_per_pack", "unit_size", "normal_price"):
		if flt(values.get(field)) <= 0:
			errors.append(f"{field.replace('_', ' ').title()} must be greater than zero.")
	if values.get("purchase_uom") not in {"g", "Kg", "ml", "Litre", "Each"}:
		errors.append("Size Unit must be g, Kg, ml, Litre, or Each.")
	if existing and (existing.item_code != item_code or existing.supplier != supplier):
		errors.append("Offer ID belongs to a different item or supplier.")
	status = "error" if errors else ("insert" if not existing else ("unchanged" if not _changes(existing, values) else "update"))
	return {"kind": "Supplier Offer", "row_number": row_number, "status": status, "record_name": offer_id, "item_code": item_code, "item_name": exact_name or _text(row.get("item_name")), "supplier": supplier, "changes": _changes(existing, values), "errors": errors, "values": values}


def _is_item_reference_row(row):
	"""Return true when an exported item has no supplier-offer facts to import yet."""
	offer_fields = {
		"offer_id", "offer_key", "supplier", "supplier_item_code", "units_per_pack", "unit_size",
		"purchase_uom", "normal_pack_price", "discounted_pack_price", "discount_from", "discount_to",
		"effective_from", "effective_to", "price_source", "source_date",
	}
	return not any(row.get(field) not in (None, "") for field in offer_fields)


# endregion FIELD MAPPING AND IMPORT PREVIEW


# =============================================================================
# region REVIEWED APPLY
# =============================================================================


def apply_price_import(batch_name):
	"""Apply one reviewed flat import idempotently while preserving supplier price history."""
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		return _batch_response(batch)
	if batch.error_count:
		frappe.throw(_("Fix import errors and create a new preview before applying."))
	preview = frappe.parse_json(batch.preview_json)
	result = {"inserted": [], "updated": [], "unchanged": []}
	for row in preview.get("offers") or []:
		_apply_offer_row(row, result)
	batch.db_set({"status": "Applied", "applied_on": frappe.utils.now_datetime(), "applied_by": frappe.session.user, "result_json": frappe.as_json(result)})
	return _batch_response(frappe.get_doc(batch.doctype, batch.name))


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


def _offer_values(row, existing=None):
	def value(source, target=None, default=None):
		if source in row and row.get(source) not in (None, ""):
			return row.get(source)
		return existing.get(target or source) if existing else default
	return {
		"item_code": _text(value("item_code")), "supplier": _text(value("supplier")), "supplier_item_code": _text(value("supplier_item_code")),
		"effective_from": value("effective_from", default=nowdate()) or nowdate(), "effective_to": value("effective_to"),
		"units_per_pack": flt(value("units_per_pack")), "unit_size": flt(value("unit_size")), "purchase_uom": value("purchase_uom"),
		"normal_price": flt(value("normal_pack_price", "normal_price")), "discounted_price": flt(value("discounted_pack_price", "discounted_price")),
		"discount_from": value("discount_from"), "discount_to": value("discount_to"), "currency": value("currency", default="ZAR") or "ZAR",
		"price_includes_vat": _bool(value("price_includes_vat"), True), "vat_rate": flt(value("vat_rate", default=15)),
		"price_source": value("price_source"), "source_date": value("source_date"), "last_verified_on": value("last_verified_on", default=nowdate()) or nowdate(),
		"preferred": _bool(value("preferred")), "enabled": _bool(value("enabled"), True), "notes": value("notes"),
	}


# endregion REVIEWED APPLY


# =============================================================================
# region FILE AND RESPONSE HELPERS
# =============================================================================


def _read_flat_file(file_url):
	path = _private_file_path(file_url)
	if path.suffix.lower() == ".csv":
		with path.open(encoding="utf-8-sig", newline="") as stream:
			reader = csv.DictReader(stream)
			headers, rows = list(reader.fieldnames or []), list(reader)
		return headers, rows
	workbook = load_workbook(path, read_only=True, data_only=True)
	sheet = workbook[workbook.sheetnames[0]]
	values = sheet.iter_rows(values_only=True)
	headers = [_text(value) for value in next(values, [])]
	rows = [{headers[index]: value for index, value in enumerate(row) if index < len(headers) and headers[index]} for row in values]
	return headers, rows


def _private_file_path(file_url):
	file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True)
	if not file_doc:
		frappe.throw(_("Upload the spreadsheet before continuing."))
	path = Path(frappe.get_site_path("private" if file_doc.is_private else "public", "files", file_doc.file_name))
	if path.suffix.lower() not in {".xlsx", ".xlsm", ".csv"}:
		frappe.throw(_("Upload an .xlsx, .xlsm, or .csv file."))
	return path


def _batch_response(batch):
	preview = frappe.parse_json(batch.preview_json) if batch.preview_json else {"offers": [], "mapping": {}}
	return {"name": batch.name, "status": batch.status, "counts": {"total": batch.total_rows, "insert": batch.insert_count, "update": batch.update_count, "unchanged": batch.unchanged_count, "error": batch.error_count}, "rows": preview.get("offers", []), "mapping": preview.get("mapping", {}), "result": frappe.parse_json(batch.result_json) if batch.result_json else None}


def _changes(doc, values):
	if not doc:
		return [{"field": field, "before": None, "after": value} for field, value in values.items() if value not in (None, "")]
	return [{"field": field, "before": doc.get(field), "after": value} for field, value in values.items() if _comparable(doc.get(field)) != _comparable(value)]


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


def _normalize_header(value):
	return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _text(value):
	return str(value or "").strip()


def _display(value):
	return "" if value is None else str(value)


preview_price_workbook = preview_price_import
apply_price_workbook = apply_price_import


# endregion FILE AND RESPONSE HELPERS
