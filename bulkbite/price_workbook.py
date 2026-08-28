from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate
from openpyxl import Workbook, load_workbook

from bulkbite.price_import_ai import improve_price_proposal_with_gemini
from bulkbite.price_import_schema import PriceImportProposal
from bulkbite.pricing import supplier_offer_key


# =============================================================================
# region FLAT PRICE CATALOGUE CONTRACT
# =============================================================================


PRICE_FIELDS = [
	{"fieldname": "offer_id", "label": "Offer ID", "aliases": ["id", "name", "record id"], "identity": True},
	{"fieldname": "offer_key", "label": "Offer Key", "aliases": ["key"], "identity": True},
	{"fieldname": "item_code", "label": "Item Code", "aliases": ["item id", "product code"], "identity": True},
	{"fieldname": "item_name", "label": "Item Name", "aliases": ["item", "product", "product name"], "identity": True},
	{"fieldname": "item_category", "label": "Item Category", "aliases": ["category", "food category", "type"]},
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
		"ai_available": bool(frappe.conf.get("gemini_api_key") and frappe.conf.get("gemini_private_receipt_approved")),
		"known_setup": _known_price_setup(),
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
	proposal = _build_price_import_proposal(rows, valid_mapping)
	counts = _proposal_counts(proposal)
	batch = frappe.get_doc({
		"doctype": "BulkBite Price Import Batch", "source_file": file_url, "status": "Previewed",
		"total_rows": len(rows), "insert_count": counts["insert"], "update_count": counts["update"],
		"unchanged_count": counts["unchanged"], "error_count": counts["error"],
		"preview_json": frappe.as_json(proposal),
	}).insert()
	return _batch_response(batch)


def improve_price_import(batch_name, progress=None):
	"""Improve one saved proposal with Gemini while preserving the reviewed-write boundary."""
	_report_improvement_progress(progress, "loading saved review")
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		frappe.throw(_("An applied import cannot be changed."))
	proposal = PriceImportProposal.model_validate(frappe.parse_json(batch.preview_json)).model_dump()
	_report_improvement_progress(progress, "matching existing setup")
	known_setup = _known_price_setup()
	_report_improvement_progress(progress, "analysing ambiguous rows")
	ai_result = improve_price_proposal_with_gemini(_ai_offer_rows(proposal), known_setup)
	_report_improvement_progress(progress, "validating suggestions")
	suggestions = {row.row_number: row for row in ai_result.rows}
	for offer in proposal["offers"]:
		suggestion = suggestions.get(offer["row_number"])
		if not suggestion:
			continue
		for field in ("item_code", "item_name", "supplier", "item_category"):
			if getattr(suggestion, field):
				offer[field] = getattr(suggestion, field)
		for field in ("units_per_pack", "unit_size", "purchase_uom"):
			value = getattr(suggestion, field)
			if value not in (None, ""):
				offer["values"][field] = value
		offer["confidence"] = suggestion.confidence
		offer["reason"] = suggestion.reason
	proposal = _review_price_proposal(proposal)
	proposal["ai_used"] = True
	proposal["ai_notes"] = ai_result.notes
	_save_price_proposal(batch, proposal)
	_report_improvement_progress(progress, "ready for review")
	return _batch_response(frappe.get_doc(batch.doctype, batch.name))


def _report_improvement_progress(progress, stage):
	"""Report one optional background-job stage without coupling workbook logic to RQ."""
	if progress:
		progress(stage)


def review_price_import(batch_name, proposal):
	"""Validate and save the manager's editable proposal without writing setup or offers."""
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		frappe.throw(_("An applied import cannot be changed."))
	proposal = frappe.parse_json(proposal) if isinstance(proposal, str) else proposal
	reviewed = _review_price_proposal(PriceImportProposal.model_validate(proposal).model_dump())
	_save_price_proposal(batch, reviewed)
	return _batch_response(frappe.get_doc(batch.doctype, batch.name))


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
	item_name = _text(row.get("item_name"))
	supplier = _text(row.get("supplier")) or (existing.supplier if existing else "")
	item_category = _text(row.get("item_category"))
	supplier_item_code = _text(row.get("supplier_item_code")) or (existing.supplier_item_code if existing else "")
	if not existing and item_code and supplier:
		key = supplier_offer_key(item_code, supplier, supplier_item_code)
		existing_name = frappe.db.get_value("BulkBite Supplier Offer", {"offer_key": key, "enabled": 1}, "name")
		existing = frappe.get_doc("BulkBite Supplier Offer", existing_name) if existing_name else None
		offer_id = existing_name or offer_id
	item_exists = bool(item_code and frappe.db.exists("BulkBite Item", item_code))
	supplier_exists = bool(supplier and frappe.db.exists("BulkBite Supplier", supplier))
	if not item_code:
		errors.append("Item Code is required.")
	elif not item_exists and not item_name:
		errors.append("Item Name is required when creating a new item.")
	exact_name = frappe.db.get_value("BulkBite Item", item_code, "item_name") if item_code else None
	if item_name and exact_name and item_name != exact_name:
		errors.append("Item Name does not match the selected Item Code.")
	if not existing and _is_item_reference_row(row):
		return {
			"kind": "Item Reference", "row_number": row_number, "status": "error" if errors else "unchanged",
			"record_name": item_code, "item_code": item_code, "item_name": exact_name or _text(row.get("item_name")),
			"supplier": "", "changes": [], "errors": errors, "values": {},
		}
	if not supplier:
		errors.append("Supplier is required.")
	values = _offer_values(row, existing)
	for field in ("units_per_pack", "unit_size", "normal_price"):
		if flt(values.get(field)) <= 0:
			errors.append(f"{field.replace('_', ' ').title()} must be greater than zero.")
	if values.get("purchase_uom") not in {"g", "Kg", "ml", "Litre", "Each"}:
		errors.append("Size Unit must be g, Kg, ml, Litre, or Each.")
	if existing and (existing.item_code != item_code or existing.supplier != supplier):
		errors.append("Offer ID belongs to a different item or supplier.")
	status = "error" if errors else ("insert" if not existing else ("unchanged" if not _changes(existing, values) else "update"))
	setup_creations = []
	if not item_exists and item_code:
		setup_creations.append({"doctype": "BulkBite Item", "name": item_code, "label": item_name})
	if not supplier_exists and supplier:
		setup_creations.append({"doctype": "BulkBite Supplier", "name": supplier, "label": supplier})
	return {
		"kind": "Supplier Offer", "row_number": row_number, "status": status, "record_name": offer_id,
		"item_code": item_code, "item_name": exact_name or item_name, "supplier": supplier, "item_category": item_category,
		"changes": _changes(existing, values), "setup_creations": setup_creations,
		"confidence": 1, "reason": "Values came directly from matched spreadsheet columns.",
		"errors": errors, "values": values,
	}


def _build_price_import_proposal(offers, mapping):
	return _review_price_proposal({"mapping": mapping, "suppliers": [], "categories": [], "items": [], "offers": offers})


def _review_price_proposal(proposal):
	"""Normalize editable setup proposals and recalculate every offer outcome."""
	validated = PriceImportProposal.model_validate(proposal).model_dump()
	supplier_edits = {row["source_key"]: row["name"] for row in validated.get("suppliers", []) if row.get("source_key") and row.get("name")}
	category_edits = {row["source_key"]: row["name"] for row in validated.get("categories", []) if row.get("source_key") and row.get("name")}
	item_edits = {row["source_key"]: row for row in validated.get("items", []) if row.get("source_key")}
	suppliers, categories, items, offers = {}, {}, {}, []
	for raw in validated["offers"]:
		offer = dict(raw)
		if offer.get("kind") == "Item Reference":
			offer.update({"status": "unchanged", "confidence": 1, "reason": "Existing item reference has no supplier offer facts to import.", "errors": [], "changes": []})
			offers.append(offer)
			continue
		original_item_code = _text(offer.get("item_code"))
		item_edit = item_edits.get(original_item_code, {})
		offer["item_code"] = _text(item_edit.get("item_code") or original_item_code)
		offer["item_name"] = _text(item_edit.get("item_name") or offer.get("item_name"))
		offer["supplier"] = _text(supplier_edits.get(_text(offer.get("supplier"))) or offer.get("supplier"))
		offer["item_category"] = _text(item_edit.get("item_category") or category_edits.get(_text(offer.get("item_category"))) or offer.get("item_category"))
		offer["values"] = {**offer.get("values", {}), "item_code": offer["item_code"], "supplier": offer["supplier"]}
		_review_offer_errors(offer)
		if offer["supplier"]:
			suppliers.setdefault(offer["supplier"], _setup_proposal("supplier", offer["supplier"], offer["supplier"]))
		if offer["item_category"]:
			categories.setdefault(offer["item_category"], _setup_proposal("category", offer["item_category"], offer["item_category"], default_supplier=offer["supplier"]))
		if offer["item_code"]:
			items.setdefault(offer["item_code"], _setup_proposal(
				"item", offer["item_code"], offer["item_name"] or offer["item_code"], item_code=offer["item_code"],
				item_name=offer["item_name"], item_category=offer["item_category"], stock_uom=_stock_uom(offer["values"].get("purchase_uom")),
			))
		offers.append(offer)
	for kind, generated, supplied in (
		("supplier", suppliers, validated.get("suppliers", [])),
		("category", categories, validated.get("categories", [])),
		("item", items, validated.get("items", [])),
	):
		for setup in supplied:
			key = _text(setup.get("source_key") or setup.get("name") or setup.get("item_code"))
			if key in generated:
				generated[key].update(setup)
			elif key:
				identity = _text(setup.get("item_code") if kind == "item" else setup.get("name"))
				match_key = next((candidate_key for candidate_key, candidate in generated.items() if _text(candidate.get("item_code") if kind == "item" else candidate.get("name")) == identity), None)
				if match_key:
					generated[match_key].update(setup)
				else:
					generated[key] = setup
		for setup in generated.values():
			_validate_setup_proposal(kind, setup)
	return PriceImportProposal.model_validate({
		**validated, "suppliers": list(suppliers.values()), "categories": list(categories.values()),
		"items": list(items.values()), "offers": offers,
	}).model_dump()


def _setup_proposal(kind, source_key, name, **values):
	doctype = {"supplier": "BulkBite Supplier", "category": "BulkBite Item Category", "item": "BulkBite Item"}[kind]
	record_name = values.get("item_code") if kind == "item" else name
	exists = bool(record_name and frappe.db.exists(doctype, record_name))
	return {
		"kind": kind, "source_key": source_key, "name": name, "status": "unchanged" if exists else "insert",
		"confidence": 1, "reason": "Matched an existing record." if exists else "Missing setup record proposed from the spreadsheet.",
		"errors": [], **values,
	}


def _validate_setup_proposal(kind, setup):
	setup["errors"] = []
	if not _text(setup.get("name")):
		setup["errors"].append(f"{kind.title()} name is required.")
	if kind == "item":
		if not _text(setup.get("item_code")):
			setup["errors"].append("Item code is required.")
		if not _text(setup.get("item_name")):
			setup["errors"].append("Item name is required.")
		if setup.get("stock_uom") not in {"Kg", "Litre", "Each"}:
			setup["errors"].append("Stock unit must be Kg, Litre, or Each.")
	identity = _text(setup.get("item_code") if kind == "item" else setup.get("name"))
	setup["source_key"] = identity
	doctype = {"supplier": "BulkBite Supplier", "category": "BulkBite Item Category", "item": "BulkBite Item"}[kind]
	setup["status"] = "error" if setup["errors"] else ("unchanged" if identity and frappe.db.exists(doctype, identity) else "insert")


def _review_offer_errors(offer):
	errors = []
	values = offer["values"]
	if not offer["item_code"]:
		errors.append("Item code is required.")
	if not offer["item_name"]:
		errors.append("Item name is required.")
	if not offer["supplier"]:
		errors.append("Supplier is required.")
	existing_item_name = frappe.db.get_value("BulkBite Item", offer["item_code"], "item_name") if offer["item_code"] else None
	if existing_item_name and offer["item_name"] != existing_item_name:
		errors.append(f"Item code already belongs to {existing_item_name}.")
	for field in ("units_per_pack", "unit_size", "normal_price"):
		if flt(values.get(field)) <= 0:
			errors.append(f"{field.replace('_', ' ').title()} must be greater than zero.")
	if values.get("purchase_uom") not in {"g", "Kg", "ml", "Litre", "Each"}:
		errors.append("Size unit must be g, Kg, ml, Litre, or Each.")
	if flt(values.get("discounted_price")) and flt(values.get("discounted_price")) >= flt(values.get("normal_price")):
		errors.append("Discounted price must be lower than normal price.")
	if flt(values.get("discounted_price")) and not (values.get("discount_from") and values.get("discount_to")):
		errors.append("A discounted price needs both discount dates.")
	match_name = None
	if offer["record_name"] and frappe.db.exists("BulkBite Supplier Offer", offer["record_name"]):
		match_name = offer["record_name"]
	elif offer["item_code"] and offer["supplier"]:
		key = supplier_offer_key(offer["item_code"], offer["supplier"], values.get("supplier_item_code"))
		match_name = frappe.db.get_value("BulkBite Supplier Offer", {"offer_key": key, "enabled": 1}, "name")
	offer["record_name"] = match_name or ""
	existing = frappe.get_doc("BulkBite Supplier Offer", match_name) if match_name else None
	offer["changes"] = _changes(existing, values)
	offer["errors"] = errors
	offer["status"] = "error" if errors else ("insert" if not existing else ("update" if offer["changes"] else "unchanged"))


def _proposal_counts(proposal):
	entities = [*proposal.get("suppliers", []), *proposal.get("categories", []), *proposal.get("items", []), *proposal.get("offers", [])]
	return {status: sum(1 for row in entities if row.get("status") == status) for status in ("insert", "update", "unchanged", "error")}


def _save_price_proposal(batch, proposal):
	counts = _proposal_counts(proposal)
	batch.db_set({
		"total_rows": len(proposal.get("offers", [])), "insert_count": counts["insert"],
		"update_count": counts["update"], "unchanged_count": counts["unchanged"],
		"error_count": counts["error"], "preview_json": frappe.as_json(proposal),
	})


def _known_price_setup():
	return {
		"suppliers": frappe.get_all("BulkBite Supplier", fields=["name"], order_by="name"),
		"categories": frappe.get_all("BulkBite Item Category", fields=["name", "default_supplier"], order_by="name"),
		"items": frappe.get_all("BulkBite Item", filters={"item_type": "Ingredient"}, fields=["item_code", "item_name", "item_category", "stock_uom"], order_by="item_name"),
	}


def _ai_offer_rows(proposal):
	return [{
		"row_number": row["row_number"], "item_code": row["item_code"], "item_name": row["item_name"],
		"supplier": row["supplier"], "item_category": row.get("item_category"),
		"supplier_item_code": row["values"].get("supplier_item_code"), "units_per_pack": row["values"].get("units_per_pack"),
		"unit_size": row["values"].get("unit_size"), "purchase_uom": row["values"].get("purchase_uom"),
		"normal_price": row["values"].get("normal_price"), "notes": row["values"].get("notes"),
	} for row in proposal.get("offers", [])]


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
	preview = _review_price_proposal(frappe.parse_json(batch.preview_json))
	counts = _proposal_counts(preview)
	if counts["error"]:
		frappe.throw(_("The reviewed proposal no longer passes validation. Review it again before applying."))
	result = {"inserted": [], "updated": [], "unchanged": [], "suppliers": [], "categories": [], "items": [], "offers": []}
	_apply_reviewed_setup(preview, result)
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
	result["offers"].append(doc.name)


def _apply_reviewed_setup(proposal, result):
	"""Create only the manager-approved missing setup records in dependency order."""
	for row in proposal.get("suppliers", []):
		if not frappe.db.exists("BulkBite Supplier", row["name"]):
			frappe.get_doc({"doctype": "BulkBite Supplier", "supplier_name": row["name"], "enabled": 1, "notes": "Created from reviewed price catalogue evidence."}).insert()
			result["suppliers"].append(row["name"])
	for row in proposal.get("categories", []):
		if not frappe.db.exists("BulkBite Item Category", row["name"]):
			frappe.get_doc({"doctype": "BulkBite Item Category", "category_name": row["name"], "default_supplier": row.get("default_supplier") or None, "enabled": 1, "notes": "Created from reviewed price catalogue evidence."}).insert()
			result["categories"].append(row["name"])
	offers_by_item = {row["item_code"]: row for row in proposal.get("offers", [])}
	for row in proposal.get("items", []):
		if frappe.db.exists("BulkBite Item", row["item_code"]):
			continue
		offer = offers_by_item.get(row["item_code"], {})
		frappe.get_doc({
			"doctype": "BulkBite Item", "item_code": row["item_code"], "item_name": row["item_name"],
			"item_type": "Ingredient", "item_category": row.get("item_category") or None,
			"stock_uom": row["stock_uom"], "track_stock": 1, "purchasable": 1, "enabled": 1,
			"theory_valuation_rate": _offer_stock_unit_rate(offer.get("values", {})),
			"description": "Created from reviewed price catalogue evidence.",
		}).insert()
		result["items"].append(row["item_code"])


def _stock_uom(purchase_uom):
	"""Map a supplier pack unit to the item's stock unit."""
	return {"g": "Kg", "Kg": "Kg", "ml": "Litre", "Litre": "Litre", "Each": "Each"}.get(purchase_uom, purchase_uom)


def _offer_stock_unit_rate(values):
	"""Return the current pack price per Kg, Litre, or Each for a new item."""
	pack_quantity = flt(values["units_per_pack"]) * flt(values["unit_size"])
	if values["purchase_uom"] in {"g", "ml"}:
		pack_quantity /= 1000
	if pack_quantity <= 0:
		return 0
	price = flt(values["normal_price"])
	if flt(values.get("discounted_price")) > 0 and _date_active(values.get("discount_from"), values.get("discount_to"), getdate(nowdate())):
		price = flt(values["discounted_price"])
	return round(price / pack_quantity, 6)


def _date_active(effective_from, effective_to, on_date):
	return (not effective_from or getdate(effective_from) <= on_date) and (not effective_to or getdate(effective_to) >= on_date)


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
	preview = frappe.parse_json(batch.preview_json) if batch.preview_json else {"offers": [], "mapping": {}, "suppliers": [], "categories": [], "items": []}
	return {
		"name": batch.name, "status": batch.status,
		"counts": {"total": batch.total_rows, "insert": batch.insert_count, "update": batch.update_count, "unchanged": batch.unchanged_count, "error": batch.error_count},
		"rows": preview.get("offers", []), "offers": preview.get("offers", []),
		"suppliers": preview.get("suppliers", []), "categories": preview.get("categories", []), "items": preview.get("items", []),
		"mapping": preview.get("mapping", {}), "ai_used": preview.get("ai_used", False), "ai_notes": preview.get("ai_notes", ""),
		"result": frappe.parse_json(batch.result_json) if batch.result_json else None,
	}


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
