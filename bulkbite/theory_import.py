from __future__ import annotations

import re
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import flt
from openpyxl import load_workbook


# =============================================================================
# region WORKBOOK MAPPING
# =============================================================================


EXPECTED_HEADERS = {
	"Ingredients": ["Ingredient", "Pack Size", "Pack Price", "R / kg or L", "Unit", "Supplier", "Notes"],
	"Recipe_Costing": ["Meal", "Ingredient", "Qty / 100 kg", "Unit", "Price / Unit", "Ingredient Cost", "% of Recipe Cost", "Suplier"],
	"Menu_Plan": ["Week", "Meal", "Loaded Cost / kg", "Planned Production kg", "Food Cost", "Cost / 600g"],
}


def import_master_sheet(workbook_path, company="BulkBite"):
	"""Import the approved workbook into custom items, recipes, and a relative plan."""
	path = Path(workbook_path)
	if not path.exists():
		frappe.throw(_("BulkBite workbook was not found at {0}.").format(path))
	workbook = load_workbook(path, data_only=True, read_only=True)
	_validate_workbook(workbook)
	_ensure_locations()
	ingredient_map = _import_ingredients(workbook["Ingredients"])
	meal_map = _import_meals(workbook["Recipe_Costing"])
	recipe_map = _import_recipes(workbook["Recipe_Costing"], ingredient_map, meal_map, path.name)
	plan = _import_relative_plan(workbook["Menu_Plan"], meal_map, recipe_map, company, path.name)
	return {
		"ingredients": len(ingredient_map),
		"meals": len(meal_map),
		"approved_recipes": len(recipe_map),
		"production_plan": plan.name,
		"plan_status": plan.status,
		"plan_rows": len(plan.plan_rows),
	}


def _validate_workbook(workbook):
	for sheet_name, expected in EXPECTED_HEADERS.items():
		if sheet_name not in workbook.sheetnames:
			frappe.throw(_("Required worksheet {0} is missing.").format(sheet_name))
		sheet = workbook[sheet_name]
		header_row = 3
		actual = [sheet.cell(header_row, column).value for column in range(1, len(expected) + 1)]
		if actual != expected:
			frappe.throw(_("Worksheet {0} headers changed. Review the importer before loading this workbook.").format(sheet_name))


# endregion WORKBOOK MAPPING


# =============================================================================
# region ITEM AND RECIPE MASTER DATA
# =============================================================================


def _ensure_locations():
	for name, location_type in (("Ingredients", "Ingredients"), ("Finished Meals", "Finished Meals")):
		if frappe.db.exists("BulkBite Location", name):
			continue
		frappe.get_doc(
			{"doctype": "BulkBite Location", "location_name": name, "location_type": location_type, "enabled": 1}
		).insert(ignore_permissions=True)


def _import_ingredients(sheet):
	result = {}
	for row in sheet.iter_rows(min_row=4, values_only=True):
		name, pack_size, pack_price, unit_rate, unit, supplier, notes = row[:7]
		if not name:
			continue
		if supplier and not frappe.db.exists("BulkBite Supplier", str(supplier).strip()):
			frappe.get_doc(
				{
					"doctype": "BulkBite Supplier",
					"supplier_name": str(supplier).strip(),
					"enabled": 1,
					"notes": _("Imported from Master Sheet.xlsx ingredient purchasing theory."),
				}
			).insert(ignore_permissions=True)
		stock_uom = _stock_uom(unit)
		item_code = f"BB-ING-{_slug(name)}"
		item = _upsert_item(
			item_code,
			name,
			"Ingredient",
			stock_uom,
			flt(unit_rate),
			f"Theory source: Master Sheet.xlsx. Pack {pack_size} {unit} at R{pack_price}. Supplier: {supplier}. {notes or ''}".strip(),
			is_stock_item=str(name).strip() != "Water",
		)
		result[str(name).strip()] = item.name
	return result


def _import_meals(sheet):
	result = {}
	for row in sheet.iter_rows(min_row=4, values_only=True):
		meal_name = row[0]
		if not meal_name or meal_name in result:
			continue
		item_code = f"BB-MEAL-{_slug(meal_name)}"
		item = _upsert_item(
			item_code,
			meal_name,
			"Finished Meal",
			"Kg",
			0,
			"Finished food output. Theory is stored in the linked approved BulkBite recipe version.",
		)
		result[str(meal_name).strip()] = item.name
	return result



def _upsert_item(item_code, item_name, item_type, stock_uom, valuation_rate, description, is_stock_item=True):
	if frappe.db.exists("BulkBite Item", item_code):
		item = frappe.get_doc("BulkBite Item", item_code)
		if item.stock_uom != stock_uom:
			frappe.throw(_("Existing item {0} uses {1}, but the workbook requires {2}.").format(item_code, item.stock_uom, stock_uom))
		item.item_name = item_name
		item.item_type = item_type
		item.track_stock = is_stock_item
		item.purchasable = is_stock_item
		item.theory_valuation_rate = valuation_rate
		item.description = description
		item.save(ignore_permissions=True)
		return item
	return frappe.get_doc(
		{
			"doctype": "BulkBite Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_type": item_type,
			"stock_uom": stock_uom,
			"track_stock": is_stock_item,
			"purchasable": is_stock_item,
			"theory_valuation_rate": valuation_rate,
			"description": description,
		}
	).insert(ignore_permissions=True)


def _import_recipes(sheet, ingredient_map, meal_map, workbook_name):
	by_meal = {}
	for row in sheet.iter_rows(min_row=4, values_only=True):
		meal_name, ingredient_name, qty, unit, rate = row[:5]
		if not meal_name or not ingredient_name:
			continue
		if str(ingredient_name).strip() == "Water":
			continue
		by_meal.setdefault(str(meal_name).strip(), []).append(
			{
				"item_code": ingredient_map[str(ingredient_name).strip()],
				"qty": flt(qty),
				"uom": _stock_uom(unit),
				"theory_rate": flt(rate),
			}
		)
	result = {}
	for meal_name, ingredients in by_meal.items():
		meal_item = meal_map[meal_name]
		existing = frappe.db.get_value(
			"BulkBite Recipe", {"finished_item": meal_item, "status": "Approved"}, "name", order_by="version desc"
		)
		if existing and _recipe_matches(existing, ingredients):
			result[meal_name] = existing
			continue
		if existing:
			frappe.db.set_value("BulkBite Recipe", existing, "status", "Retired", update_modified=False)
		latest_version = frappe.db.get_value(
			"BulkBite Recipe", {"finished_item": meal_item}, "version", order_by="version desc"
		)
		version = (latest_version or 0) + 1
		recipe = frappe.get_doc(
			{
				"doctype": "BulkBite Recipe",
				"recipe_name": meal_name,
				"version": version,
				"status": "Approved",
				"finished_item": meal_item,
				"nominal_output_qty": 100,
				"output_uom": "Kg",
				"source_workbook": workbook_name,
				"source_sheet": "Recipe_Costing",
				"ingredients": ingredients,
			}
		).insert(ignore_permissions=True)
		result[meal_name] = recipe.name
	return result


def _recipe_matches(recipe_name, expected_items):
	existing = frappe.get_all(
		"BulkBite Recipe Ingredient", filters={"parent": recipe_name}, fields=["item_code", "qty", "uom"]
	)
	existing_signature = sorted((row.item_code, flt(row.qty), row.uom) for row in existing)
	expected_signature = sorted((row["item_code"], flt(row["qty"]), row["uom"]) for row in expected_items)
	return existing_signature == expected_signature


# endregion ITEM AND RECIPE MASTER DATA


# =============================================================================
# region RELATIVE PRODUCTION PLAN
# =============================================================================


def _import_relative_plan(sheet, meal_map, recipe_map, company, workbook_name):
	rows = []
	for row in sheet.iter_rows(min_row=4, max_row=7, values_only=True):
		week, meal_name, _loaded_cost, planned_output, expected_cost, _portion_cost = row[:6]
		rows.append(
			{
				"week_number": week,
				"finished_item": meal_map[str(meal_name).strip()],
				"recipe": recipe_map[str(meal_name).strip()],
				"planned_output_qty": flt(planned_output),
				"uom": "Kg",
				"expected_material_cost": flt(expected_cost),
			}
		)
	existing = frappe.db.get_value(
		"BulkBite Production Plan",
		{"source_workbook": workbook_name, "source_sheet": "Menu_Plan", "status": "Relative Draft"},
		"name",
	)
	if existing:
		plan = frappe.get_doc("BulkBite Production Plan", existing)
		plan.set("plan_rows", rows)
		plan.date_note = _("The workbook supplies Week 1 to Week 4 but no calendar start date. Set dates before activating this plan.")
		plan.save(ignore_permissions=True)
		return plan
	return frappe.get_doc(
		{
			"doctype": "BulkBite Production Plan",
			"plan_title": "Master Sheet four-week menu",
			"status": "Relative Draft",
			"business_name": company,
			"source_workbook": workbook_name,
			"source_sheet": "Menu_Plan",
			"date_note": _("The workbook supplies Week 1 to Week 4 but no calendar start date. Set dates before activating this plan."),
			"plan_rows": rows,
		}
	).insert(ignore_permissions=True)


def _stock_uom(value):
	mapping = {"kg": "Kg", "l": "Litre"}
	unit = mapping.get(str(value or "").strip().lower())
	if not unit:
		frappe.throw(_("Unsupported stock unit {0} in Master Sheet.xlsx.").format(value))
	return unit


def _slug(value):
	return re.sub(r"[^A-Z0-9]+", "-", str(value).upper()).strip("-")[:80]


# endregion RELATIVE PRODUCTION PLAN
