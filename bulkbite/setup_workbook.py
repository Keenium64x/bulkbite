from __future__ import annotations

import io
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime
from openpyxl import Workbook

from bulkbite.price_workbook import _read_flat_file


# =============================================================================
# region CONTROLLED SPREADSHEET WORKSPACE
# =============================================================================


RECIPE_FIELDS = [
	{"fieldname": "recipe_id", "label": "Recipe ID", "aliases": ["recipe", "id"]},
	{"fieldname": "recipe_name", "label": "Recipe Name", "required": True},
	{"fieldname": "version", "label": "Version"},
	{"fieldname": "status", "label": "Status"},
	{"fieldname": "finished_item", "label": "Finished Item Code", "required": True, "aliases": ["finished item"]},
	{"fieldname": "finished_item_name", "label": "Finished Item Name"},
	{"fieldname": "nominal_output_qty", "label": "Recipe Output (Kg)", "required": True, "aliases": ["yield", "output"]},
	{"fieldname": "ingredient_item", "label": "Ingredient Item Code", "required": True, "aliases": ["ingredient"]},
	{"fieldname": "ingredient_item_name", "label": "Ingredient Item Name"},
	{"fieldname": "ingredient_qty", "label": "Ingredient Quantity", "required": True, "aliases": ["quantity", "qty"]},
	{"fieldname": "notes", "label": "Notes"},
]

SETUP_TARGETS = OrderedDict({
	"BulkBite Item": {"label": "Items", "identity": "item_code", "fields": ["item_code", "item_name", "item_type", "item_category", "stock_uom", "track_stock", "purchasable", "enabled", "theory_valuation_rate", "description"]},
	"BulkBite Supplier": {"label": "Suppliers", "identity": "supplier_name", "fields": ["supplier_name", "enabled", "notes"]},
	"BulkBite Item Category": {"label": "Food categories", "identity": "category_name", "fields": ["category_name", "default_supplier", "enabled", "notes"]},
	"BulkBite Location": {"label": "Locations", "identity": "location_name", "fields": ["location_name", "location_type", "enabled", "notes"]},
	"BulkBite Customer Plan Type": {"label": "Customer plan types", "identity": "plan_name", "fields": ["plan_name", "serving_grams", "meals_per_day", "days_per_week", "enabled", "notes"]},
	"BulkBite Employee Type": {"label": "Employee types", "identity": "employee_type_name", "fields": ["employee_type_name", "description", "capacity_basis", "capacity_per_worker", "expected_hours_per_run", "working_assumptions", "payment_basis", "payment_rate", "enabled"]},
	"BulkBite Employee": {"label": "Employees", "identity": "full_name", "fields": ["full_name", "employee_type", "status", "available_for_production", "available_hours_per_run", "email_address", "phone_number", "start_date", "end_date", "use_payment_override", "payment_basis_override", "payment_rate_override", "notes"]},
	"BulkBite Expense Type": {"label": "Expense types", "identity": "expense_type_name", "fields": ["expense_type_name", "cost_category", "default_vat_treatment", "enabled", "notes"]},
})


def get_workspace_contract(target="catalogue", setup_doctype=None):
	"""Return the allowlisted target and field contract used by download and import."""
	if target == "recipes":
		return _contract("recipes", "Recipes", RECIPE_FIELDS, [field["fieldname"] for field in RECIPE_FIELDS])
	if target == "setup":
		return _setup_contract(setup_doctype)
	frappe.throw(_("The requested spreadsheet target is not available."))


def build_workspace_workbook(target, fields=None, setup_doctype=None):
	"""Build one plain worksheet for recipes or an allowlisted setup target."""
	contract = get_workspace_contract(target, setup_doctype)
	selected = _selected_fields(contract, fields)
	rows = _recipe_export_rows() if target == "recipes" else _setup_export_rows(setup_doctype, selected)
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = contract["label"][:31]
	sheet.append([_field_by_name(contract, field)["label"] for field in selected])
	for row in rows:
		sheet.append([row.get(field) for field in selected])
	stream = io.BytesIO()
	workbook.save(stream)
	return stream.getvalue()


def inspect_workspace_file(target, file_url, setup_doctype=None):
	"""Suggest column matches without changing records."""
	contract = get_workspace_contract(target, setup_doctype)
	headers, rows = _read_flat_file(file_url)
	return {
		"target": target,
		"setup_doctype": setup_doctype,
		"file_url": file_url,
		"source_columns": [{"column": header, "samples": [str(row.get(header)) for row in rows[:3] if row.get(header) not in (None, "")]} for header in headers],
		"target_fields": [{"label": field["label"], "value": field["fieldname"]} for field in contract["fields"]],
		"suggested_mapping": {header: _suggest_field(header, contract["fields"]) for header in headers},
		"row_count": len(rows),
	}


def preview_workspace_import(target, file_url, mapping=None, setup_doctype=None):
	"""Create a saved, editable proposal without applying any record changes."""
	contract = get_workspace_contract(target, setup_doctype)
	headers, source_rows = _read_flat_file(file_url)
	mapping = frappe.parse_json(mapping) if isinstance(mapping, str) else (mapping or {})
	valid_fields = {field["fieldname"] for field in contract["fields"]}
	valid_mapping = {source: field for source, field in mapping.items() if source in headers and field in valid_fields}
	if not valid_mapping:
		frappe.throw(_("Match at least one spreadsheet column before previewing."))
	mapped_rows = [
		{field: source.get(column) for column, field in valid_mapping.items()}
		for source in source_rows
		if any(source.get(column) not in (None, "") for column in valid_mapping)
	]
	proposal = _preview_recipes(mapped_rows, valid_mapping) if target == "recipes" else _preview_setup(setup_doctype, mapped_rows, valid_mapping)
	return _save_batch(file_url, target, setup_doctype, proposal)


def review_workspace_import(batch_name, proposal):
	"""Revalidate manager edits while keeping the write boundary closed."""
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		frappe.throw(_("An applied import cannot be changed."))
	current = frappe.parse_json(batch.preview_json)
	proposal = frappe.parse_json(proposal) if isinstance(proposal, str) else proposal
	target = current.get("target")
	validated = _review_recipe_proposal(proposal) if target == "recipes" else _review_setup_proposal(proposal)
	_save_review(batch, validated)
	return _batch_response(batch)


def apply_workspace_import(batch_name):
	"""Apply one reviewed setup proposal. It never posts stock, finance, or production events."""
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		return _batch_response(batch)
	proposal = frappe.parse_json(batch.preview_json)
	proposal = _review_recipe_proposal(proposal) if proposal.get("target") == "recipes" else _review_setup_proposal(proposal)
	if _counts(proposal)["error"]:
		frappe.throw(_("Fix the highlighted import errors before applying."))
	result = _apply_recipes(proposal) if proposal["target"] == "recipes" else _apply_setup(proposal)
	batch.db_set({"status": "Applied", "applied_on": now_datetime(), "applied_by": frappe.session.user, "result_json": frappe.as_json(result)})
	return _batch_response(frappe.get_doc(batch.doctype, batch.name))


# endregion CONTROLLED SPREADSHEET WORKSPACE


# =============================================================================
# region RECIPE IMPORT STATION
# =============================================================================


def _preview_recipes(rows, mapping):
	groups = OrderedDict()
	for index, row in enumerate(rows, 2):
		key = _text(row.get("recipe_id")) or _text(row.get("recipe_name"))
		key = f"row-{index}" if not key else key
		group = groups.setdefault(key, {"recipe_id": _text(row.get("recipe_id")), "recipe_name": _text(row.get("recipe_name")), "version": cint(row.get("version") or 1), "recipe_status": _text(row.get("status")) or "Approved", "finished_item": _text(row.get("finished_item")), "finished_item_name": _text(row.get("finished_item_name")), "nominal_output_qty": flt(row.get("nominal_output_qty")), "notes": _text(row.get("notes")), "ingredients": [], "errors": []})
		group["ingredients"].append({"row_number": index, "item_code": _text(row.get("ingredient_item")), "item_name": _text(row.get("ingredient_item_name")), "qty": flt(row.get("ingredient_qty")), "errors": []})
	return _review_recipe_proposal({"target": "recipes", "mapping": mapping, "recipes": list(groups.values())})


def _review_recipe_proposal(proposal):
	recipes = []
	seen_names = set()
	for raw in proposal.get("recipes") or []:
		row = {**raw, "errors": []}
		row["recipe_id"] = _text(row.get("recipe_id"))
		row["recipe_name"] = _text(row.get("recipe_name"))
		row["finished_item"] = _text(row.get("finished_item"))
		row["finished_item_name"] = _text(row.get("finished_item_name"))
		row["recipe_status"] = _text(row.get("recipe_status")) or "Approved"
		row["version"] = max(cint(row.get("version") or 1), 1)
		row["nominal_output_qty"] = flt(row.get("nominal_output_qty"))
		if not row["recipe_name"]: row["errors"].append("Recipe Name is required.")
		if not row["finished_item"]: row["errors"].append("Finished Item Code is required.")
		if row["nominal_output_qty"] <= 0: row["errors"].append("Recipe Output must be greater than zero.")
		identity = row["recipe_id"] if row["recipe_id"] and frappe.db.exists("BulkBite Recipe", row["recipe_id"]) else frappe.db.get_value("BulkBite Recipe", {"recipe_name": row["recipe_name"], "version": row["version"]}, "name")
		row["record_name"] = identity or ""
		row["recipe_id"] = identity or row["recipe_id"]
		unique = (row["recipe_name"].lower(), row["version"])
		if unique in seen_names: row["errors"].append("This recipe and version appears more than once.")
		seen_names.add(unique)
		ingredients, seen_items = [], set()
		for ingredient in row.get("ingredients") or []:
			item = {**ingredient, "item_code": _text(ingredient.get("item_code")), "item_name": _text(ingredient.get("item_name")), "qty": flt(ingredient.get("qty")), "errors": []}
			if not item["item_code"]: item["errors"].append("Ingredient Item Code is required.")
			if item["qty"] <= 0: item["errors"].append("Ingredient Quantity must be greater than zero.")
			if item["item_code"] in seen_items: item["errors"].append("The same ingredient appears twice in this recipe.")
			seen_items.add(item["item_code"])
			ingredients.append(item)
		if not ingredients: row["errors"].append("Add at least one ingredient.")
		row["ingredients"] = ingredients
		row["status"] = "error" if row["errors"] or any(item["errors"] for item in ingredients) else ("update" if identity else "insert")
		recipes.append(row)
	return {"target": "recipes", "mapping": proposal.get("mapping") or {}, "recipes": recipes}


def _apply_recipes(proposal):
	result = {"inserted": [], "updated": [], "items_created": []}
	for row in proposal["recipes"]:
		for item_code, item_name, item_type in [(row["finished_item"], row.get("finished_item_name"), "Finished Meal"), *[(ingredient["item_code"], ingredient.get("item_name"), "Ingredient") for ingredient in row["ingredients"]]]:
			if not frappe.db.exists("BulkBite Item", item_code):
				if not item_name:
					frappe.throw(_("Name the new item {0} before applying.").format(item_code))
				frappe.get_doc({"doctype": "BulkBite Item", "item_code": item_code, "item_name": item_name, "item_type": item_type, "stock_uom": "Kg", "track_stock": 1, "purchasable": int(item_type == "Ingredient"), "enabled": 1}).insert()
				result["items_created"].append(item_code)
		values = {"recipe_name": row["recipe_name"], "version": row["version"], "status": row["recipe_status"] if row["recipe_status"] in {"Draft", "Approved", "Retired"} else "Approved", "finished_item": row["finished_item"], "nominal_output_qty": row["nominal_output_qty"], "output_uom": "Kg", "notes": row.get("notes")}
		doc = frappe.get_doc("BulkBite Recipe", row["record_name"]) if row.get("record_name") else frappe.new_doc("BulkBite Recipe")
		doc.update(values)
		doc.set("ingredients", [])
		for ingredient in row["ingredients"]: doc.append("ingredients", {"item_code": ingredient["item_code"], "qty": ingredient["qty"]})
		doc.save() if doc.name else doc.insert()
		result["updated" if row.get("record_name") else "inserted"].append(doc.name)
	return result


def _recipe_export_rows():
	rows = []
	for recipe in frappe.get_all("BulkBite Recipe", fields=["name", "recipe_name", "version", "status", "finished_item", "nominal_output_qty", "notes"], order_by="recipe_name, version"):
		finished_name = frappe.db.get_value("BulkBite Item", recipe.finished_item, "item_name")
		for ingredient in frappe.get_all("BulkBite Recipe Ingredient", filters={"parent": recipe.name}, fields=["item_code", "qty"], order_by="idx"):
			rows.append({"recipe_id": recipe.name, "recipe_name": recipe.recipe_name, "version": recipe.version, "status": recipe.status, "finished_item": recipe.finished_item, "finished_item_name": finished_name, "nominal_output_qty": recipe.nominal_output_qty, "ingredient_item": ingredient.item_code, "ingredient_item_name": frappe.db.get_value("BulkBite Item", ingredient.item_code, "item_name"), "ingredient_qty": ingredient.qty, "notes": recipe.notes})
	return rows


# endregion RECIPE IMPORT STATION


# =============================================================================
# region ALLOWLISTED SETUP IMPORT STATION
# =============================================================================


def _setup_contract(doctype):
	if not doctype:
		return _contract("setup", "Other setup data", [], [], setup_doctype=None, setup_targets=[{"label": item["label"], "value": name} for name, item in SETUP_TARGETS.items()])
	if doctype not in SETUP_TARGETS:
		frappe.throw(_("Choose an approved setup record type."), frappe.PermissionError)
	definition = SETUP_TARGETS[doctype]
	meta = frappe.get_meta(doctype)
	fields = []
	for fieldname in definition["fields"]:
		field = meta.get_field(fieldname)
		if field and field.fieldtype not in {"Table", "Table MultiSelect", "Attach", "Attach Image", "HTML", "Section Break", "Column Break"}:
			fields.append({"fieldname": fieldname, "label": field.label or fieldname, "required": bool(field.reqd), "fieldtype": field.fieldtype, "options": field.options})
	return _contract("setup", definition["label"], fields, [field["fieldname"] for field in fields], setup_doctype=doctype, setup_targets=[{"label": item["label"], "value": name} for name, item in SETUP_TARGETS.items()])


def _preview_setup(doctype, rows, mapping):
	return _review_setup_proposal({"target": "setup", "setup_doctype": doctype, "mapping": mapping, "records": [{"values": row, "errors": []} for row in rows]})


def _review_setup_proposal(proposal):
	doctype = proposal.get("setup_doctype")
	contract = _setup_contract(doctype)
	definition = SETUP_TARGETS[doctype]
	records = []
	for raw in proposal.get("records") or []:
		values = {field["fieldname"]: raw.get("values", {}).get(field["fieldname"]) for field in contract["fields"]}
		errors = []
		for field in contract["fields"]:
			value = values.get(field["fieldname"])
			if field.get("required") and value in (None, ""): errors.append(f'{field["label"]} is required.')
			if field.get("fieldtype") == "Link" and value and not frappe.db.exists(field.get("options"), value): errors.append(f'{field["label"]} does not match an existing {field.get("options")}.')
		identity = _text(values.get(definition["identity"]))
		existing = frappe.db.get_value(doctype, {definition["identity"]: identity}, "name") if identity else None
		status = "error" if errors else ("update" if existing else "insert")
		records.append({"record_name": existing or "", "identity": identity, "status": status, "values": values, "errors": errors})
	return {"target": "setup", "setup_doctype": doctype, "mapping": proposal.get("mapping") or {}, "records": records}


def _apply_setup(proposal):
	result = {"inserted": [], "updated": []}
	for row in proposal["records"]:
		doc = frappe.get_doc(proposal["setup_doctype"], row["record_name"]) if row.get("record_name") else frappe.new_doc(proposal["setup_doctype"])
		doc.update(row["values"])
		doc.save() if doc.name else doc.insert()
		result["updated" if row.get("record_name") else "inserted"].append(doc.name)
	return result


def _setup_export_rows(doctype, fields):
	_setup_contract(doctype)
	return frappe.get_all(doctype, fields=fields, order_by="modified desc", limit_page_length=0)


# endregion ALLOWLISTED SETUP IMPORT STATION


# =============================================================================
# region SHARED WORKBOOK HELPERS
# =============================================================================


def _contract(target, label, fields, defaults, **extra):
	return {"target": target, "label": label, "fields": fields, "default_fields": defaults, **extra}


def _selected_fields(contract, fields):
	fields = frappe.parse_json(fields) if isinstance(fields, str) else (fields or contract["default_fields"])
	allowed = {field["fieldname"] for field in contract["fields"]}
	selected = [field for field in fields if field in allowed]
	if not selected: frappe.throw(_("Choose at least one column."))
	return selected


def _field_by_name(contract, fieldname):
	return next(field for field in contract["fields"] if field["fieldname"] == fieldname)


def _suggest_field(header, fields):
	needle = _normalize(header)
	for field in fields:
		if needle in {_normalize(value) for value in [field["fieldname"], field["label"], *field.get("aliases", [])]}: return field["fieldname"]
	return ""


def _save_batch(file_url, target, setup_doctype, proposal):
	counts = _counts(proposal)
	batch = frappe.get_doc({"doctype": "BulkBite Price Import Batch", "source_file": file_url, "status": "Previewed", "total_rows": counts["total"], "insert_count": counts["insert"], "update_count": counts["update"], "unchanged_count": counts["unchanged"], "error_count": counts["error"], "preview_json": frappe.as_json(proposal)}).insert()
	return _batch_response(batch)


def _save_review(batch, proposal):
	counts = _counts(proposal)
	batch.db_set({"preview_json": frappe.as_json(proposal), "total_rows": counts["total"], "insert_count": counts["insert"], "update_count": counts["update"], "unchanged_count": counts["unchanged"], "error_count": counts["error"]})


def _counts(proposal):
	rows = proposal.get("recipes") or proposal.get("records") or []
	return {"total": len(rows), **{status: sum(row.get("status") == status for row in rows) for status in ("insert", "update", "unchanged", "error")}}


def _batch_response(batch):
	proposal = frappe.parse_json(batch.preview_json)
	return {"name": batch.name, "status": batch.status, "target": proposal.get("target"), "setup_doctype": proposal.get("setup_doctype"), "mapping": proposal.get("mapping") or {}, "recipes": proposal.get("recipes") or [], "records": proposal.get("records") or [], "counts": _counts(proposal), "result": frappe.parse_json(batch.result_json) if batch.result_json else None}


def _normalize(value):
	return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _text(value):
	return str(value or "").strip()


# endregion SHARED WORKBOOK HELPERS
