from __future__ import annotations

import json

import frappe
from frappe.utils import add_days, flt, getdate
from frappe.utils.file_manager import save_file

from bulkbite.api import (
	approve_stock_audit,
	allocate_finished_food,
	create_stock_count_draft,
	post_cost_invoice,
	receive_stock_from_receipt,
	save_monthly_production_plan,
	save_production_employees,
	submit_production_run,
	update_production_actuals,
)
from bulkbite.finance_ledger import verify_finance_event_chain
from bulkbite.planning import build_plan_snapshot
from bulkbite.stock_ledger import get_stock_balance, verify_stock_balances, verify_stock_event_chain
from bulkbite.stock_production import round_operational_quantity
from bulkbite.truth_ledger import verify_truth_event_chain
from bulkbite.operational_actions import materialize_operational_actions


# =============================================================================
# region DEMO ORCHESTRATION
# =============================================================================


DEMO_MARKER = "DEMO FULL OPERATIONS V1"
DEMO_PERIOD_START = getdate("2026-08-01")
DEMO_PERIOD_END = getdate("2026-08-28")


@frappe.whitelist()
def load_full_demo_data():
	"""Load one repeatable, connected operating story through the app's posting workflows."""
	frappe.set_user("Administrator")
	try:
		master = ensure_demo_master_data()
		workforce = ensure_demo_workforce()
		finance_setup = ensure_demo_finance_setup(master)
		plan = ensure_demo_direction(master, workforce)
		receipts = ensure_demo_receipts(master)
		production = ensure_demo_production(plan, workforce)
		containers = ensure_demo_containers(production)
		operations = ensure_demo_operational_actions()
		invoices = ensure_demo_cost_invoices(plan, finance_setup)
		audit = ensure_demo_reconciliation()
		supporting = ensure_demo_supporting_history(audit, master)
		frappe.db.commit()
		return {
			"loaded": True,
			"master": master,
			"workforce": workforce,
			"plan": plan,
			"receipts": receipts,
			"production": production,
			"containers": containers,
			"operations": operations,
			"cost_invoices": invoices,
			"stock_audit": audit,
			"supporting_history": supporting,
			"summary": get_demo_data_summary(),
		}
	except Exception:
		frappe.db.rollback()
		raise


@frappe.whitelist()
def get_demo_data_summary():
	"""Return the visible demo coverage and immutable-ledger checks without changing data."""
	plan_name = frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")
	if not plan_name:
		plan_name = frappe.db.get_value(
			"BulkBite Production Plan", {"notes": ["like", f"%{DEMO_MARKER}%"]}, "name", order_by="modified desc"
		)
	requirements = []
	if plan_name:
		_plan_rows, requirements = build_plan_snapshot(frappe.get_doc("BulkBite Production Plan", plan_name), "Ingredients")
	covered = [row for row in requirements if flt(row["shortage_qty"]) <= 0]
	short = [row for row in requirements if flt(row["shortage_qty"]) > 0]
	stock_rows = frappe.get_all(
		"BulkBite Stock Balance",
		filters={"location": "Ingredients", "actual_qty": [">", 0]},
		fields=["item_code", "actual_qty", "uom", "stock_value"],
	)
	return {
		"plan": plan_name,
		"planned_ingredient_count": len(requirements),
		"covered_ingredient_count": len(covered),
		"coverage_percent": round(len(covered) / len(requirements) * 100) if requirements else 0,
		"covered_items": [row["item_name"] for row in covered],
		"short_items": [
			{
				"item": row["item_name"],
				"available_qty": row["available_qty"],
				"required_qty": row["required_qty"],
				"shortage_qty": row["shortage_qty"],
				"uom": row["uom"],
			}
			for row in short
		],
		"positive_stock_balances": len(stock_rows),
		"stock_value": round(sum(flt(row.stock_value) for row in stock_rows), 2),
		"reviewed_receipts": frappe.db.count("BulkBite Receipt Intake", {"supplier_invoice_number": ["like", "DEMO-OPS-%"]}),
		"posted_demo_runs": frappe.db.count(
			"BulkBite Production Run", {"notes": ["like", f"%{DEMO_MARKER}%"], "docstatus": 1}
		),
		"draft_demo_runs": frappe.db.count(
			"BulkBite Production Run", {"notes": ["like", f"%{DEMO_MARKER}%"], "docstatus": 0}
		),
		"posted_cost_invoices": frappe.db.count(
			"BulkBite Cost Invoice", {"invoice_number": ["like", "DEMO-OPS-%"], "costs_posted": 1}
		),
		"finance_ledger_entries": frappe.db.count("BulkBite Finance Event"),
		"stock_ledger_entries": frappe.db.count("BulkBite Stock Event"),
		"ledger_checks": {
			"stock_balances": verify_stock_balances(),
			"stock_chain": verify_stock_event_chain(),
			"truth_chain": verify_truth_event_chain(),
			"finance_chain": verify_finance_event_chain(),
		},
	}


# endregion DEMO ORCHESTRATION


# =============================================================================
# region MASTER DATA
# =============================================================================


def ensure_demo_master_data():
	"""Ensure suppliers, categories, locations, scan identities, offers, and price rules."""
	for values in (
		{"supplier_name": "Makro", "accountant_reference": "SUP-MAKRO", "delivery_lead_time_days": 4, "order_safety_days": 1, "notes": f"{DEMO_MARKER}. Dry-goods route with a four-day delivery assumption."},
		{"supplier_name": "Checkers", "accountant_reference": "SUP-CHECKERS", "delivery_lead_time_days": 1, "order_safety_days": 1, "notes": f"{DEMO_MARKER}. Fresh-food route with a one-day delivery assumption."},
		{"supplier_name": "Cape Food Packaging", "accountant_reference": "SUP-PACK", "notes": f"{DEMO_MARKER}. Packaging route."},
	):
		_ensure_named_doc("BulkBite Supplier", values["supplier_name"], values)

	for values in (
		{"category_name": "Dry", "default_supplier": "Makro", "notes": f"{DEMO_MARKER}. Shelf-stable ingredients."},
		{"category_name": "Fresh", "default_supplier": "Checkers", "notes": f"{DEMO_MARKER}. General fresh ingredients."},
		{"category_name": "Vegetables", "default_supplier": "Checkers", "notes": f"{DEMO_MARKER}. Fresh produce route."},
		{"category_name": "Protein", "default_supplier": "Checkers", "notes": f"{DEMO_MARKER}. Meat and protein route."},
		{"category_name": "Packaging", "default_supplier": "Cape Food Packaging", "notes": f"{DEMO_MARKER}. Meal packing supplies."},
	):
		_ensure_named_doc("BulkBite Item Category", values["category_name"], values)

	for values in (
		{"location_name": "Ingredients", "location_type": "Ingredients", "notes": f"{DEMO_MARKER}. Main ingredient store."},
		{"location_name": "Finished Meals", "location_type": "Finished Meals", "notes": f"{DEMO_MARKER}. Packed meal store."},
		{"location_name": "Quarantine", "location_type": "Quarantine", "notes": f"{DEMO_MARKER}. Stock awaiting review."},
		{"location_name": "Waste", "location_type": "Waste", "notes": f"{DEMO_MARKER}. Measured production waste."},
	):
		_ensure_named_doc("BulkBite Location", values["location_name"], values)

	for values in (
		{"equipment_type_name": "Rice Pot", "capacity_qty": 25, "capacity_uom": "Kg", "quantity_available": 1, "concurrent_batch_limit": 1, "enabled": 1, "notes": f"{DEMO_MARKER}. Rice cooking vessel."},
		{"equipment_type_name": "Curry Pot", "capacity_qty": 35, "capacity_uom": "Kg", "quantity_available": 1, "concurrent_batch_limit": 1, "enabled": 1, "notes": f"{DEMO_MARKER}. Main curry cooking vessel."},
		{"equipment_type_name": "Prep Station", "capacity_qty": 20, "capacity_uom": "Kg", "quantity_available": 2, "concurrent_batch_limit": 1, "enabled": 1, "notes": f"{DEMO_MARKER}. Separate ingredient preparation surface."},
	):
		_ensure_named_doc("BulkBite Equipment Type", values["equipment_type_name"], values)

	_ensure_demo_recipe_instructions()

	item_updates = {
		"BB-ING-POTATOES": ("Vegetables", "6001000000011", 1, 175, "medium potatoes", "Count is an estimate only. Weigh the raw potatoes before preparation."),
		"BB-ING-ONIONS": ("Vegetables", "6001000000028", 1, 150, "medium onions", "Count is an estimate only. Weigh the raw onions before preparation."),
		"BB-ING-CRUSHED-GARLIC": ("Vegetables", "6001000000035", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-CHICKEN-BREAST": ("Protein", "6001000000042", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-VALUE-BEEF-MINCE": ("Protein", "6001000000059", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-PARBOILED-RICE": ("Dry", "6001000000066", 2.8, 0, "", "Demo planning assumption: 1 kg dry rice yields about 2.8 kg cooked. Buying still uses the dry weight."),
		"BB-ING-DRY-BEANS": ("Dry", "6001000000073", 2.4, 0, "", "Demo planning assumption: 1 kg dry beans yields about 2.4 kg cooked. Buying still uses the dry weight."),
		"BB-ING-LENTILS": ("Dry", "6001000000080", 2.5, 0, "", "Demo planning assumption: 1 kg dry lentils yields about 2.5 kg cooked. Buying still uses the dry weight."),
		"BB-ING-BASIC-PASTA": ("Dry", "6001000000097", 2.25, 0, "", "Demo planning assumption: 1 kg dry pasta yields about 2.25 kg cooked. Buying still uses the dry weight."),
		"BB-ING-TOMATO-ONION-MIX": ("Dry", "6001000000103", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-TOMATO-PUREE": ("Dry", "6001000000110", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-SUNFLOWER-OIL": ("Dry", "6001000000127", 1, 0, "", "Use the saved raw volume."),
		"BB-ING-CURRY-POWDER": ("Dry", "6001000000134", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-STOCK-CUBES": ("Dry", "6001000000141", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-SALT": ("Dry", "6001000000158", 1, 0, "", "Use the saved raw weight."),
		"BB-ING-MIXED-HERBS": ("Dry", "6001000000165", 1, 0, "", "Use the saved raw weight."),
	}
	for item_code, (category, scan_code, yield_factor, piece_weight, piece_label, yield_note) in item_updates.items():
		if not frappe.db.exists("BulkBite Item", item_code):
			continue
		item = frappe.get_doc("BulkBite Item", item_code)
		item.item_category = category
		item.prepared_yield_factor = yield_factor
		item.average_piece_weight_g = piece_weight
		item.piece_count_label = piece_label
		item.preparation_yield_note = yield_note
		if not item.scan_codes:
			item.scan_codes = scan_code
		item.save(ignore_permissions=True)

	if not frappe.db.exists("BulkBite Item", "BB-PACK-MEAL-CONTAINER-750"):
		frappe.get_doc(
			{
				"doctype": "BulkBite Item",
				"item_code": "BB-PACK-MEAL-CONTAINER-750",
				"item_name": "750 ml Meal Container and Lid",
				"item_type": "Packaging",
				"item_category": "Packaging",
				"stock_uom": "Each",
				"track_stock": 1,
				"purchasable": 1,
				"enabled": 1,
				"scan_codes": "6001000000172",
				"theory_valuation_rate": 3.25,
				"description": f"{DEMO_MARKER}. Standard packed-meal container.",
			}
		).insert(ignore_permissions=True)
	if frappe.db.exists("BulkBite Container Type", "Standard 750 ml Reusable Container"):
		frappe.db.set_value("BulkBite Container Type", "Standard 750 ml Reusable Container", "stock_item", "BB-PACK-MEAL-CONTAINER-750", update_modified=False)

	offers = _ensure_supplier_offers()
	adjustments = _ensure_price_adjustments()
	return {
		"suppliers": ["Makro", "Checkers", "Cape Food Packaging"],
		"categories": ["Dry", "Fresh", "Vegetables", "Protein", "Packaging"],
		"locations": ["Ingredients", "Finished Meals", "Quarantine", "Waste"],
		"supplier_offers": offers,
		"price_adjustments": adjustments,
	}


def _ensure_demo_recipe_instructions():
	"""Keep four realistic demo methods available for scaled worker-instruction testing."""
	recipe_steps = {
		"BB-RECIPE-00001": [
			(1, "Soak and start beans", "Rinse the beans under cold water and remove any damaged beans. Crumble the saved stock portion into the curry pot, add the saved water quantity, bring it to a controlled boil, then reduce to a steady simmer. Stir and check the liquid level until the beans are tender.", "BB-ING-DRY-BEANS", "Curry Pot", "", 1, 15, 0.2, 1, "Cook", "Beans are clean, tender, and the water quantity matches the scaled batch."),
			(2, "Start rice", "Rinse the rice and start it in the rice pot.", "BB-ING-PARBOILED-RICE", "Rice Pot", "", 1, 10, 0.2, 1, "Cook", "Rice and water are measured before heating."),
			(3, "Prepare stew vegetables", "Weigh the potatoes and onions before preparation. Wash the potatoes, remove damaged parts, cut them into even pieces, then peel and dice the onions. Measure the garlic and keep each prepared ingredient separate until the stew base is ready.", "BB-ING-POTATOES, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC", "Prep Station", "", 1, 15, 0.3, 1, "Prep", "Prepared vegetables are even enough to cook consistently."),
			(4, "Finish bean stew", "Build the seasoned base, add the prepared vegetables and cooked beans, then simmer to the approved texture.", "BB-ING-POTATOES, BB-ING-ONIONS, BB-ING-CURRY-POWDER, BB-ING-STOCK-CUBES", "Curry Pot", "1, 3", 0, 25, 0.35, 1, "Cook", "Beans and potatoes are tender and the batch is evenly seasoned."),
			(5, "Weigh and portion", "Confirm finished weight, record any variance, and portion the stew and rice.", "BB-ING-PARBOILED-RICE", "Prep Station", "2, 4", 0, 10, 0.15, 2, "Portioning", "Recorded food weight and container count match the finished batch."),
		],
		"BB-RECIPE-00002": [
			(1, "Start rice", "Rinse and start the scaled rice batch.", "BB-ING-PARBOILED-RICE", "Rice Pot", "", 1, 10, 0.2, 1, "Cook", "Rice and water are measured."),
			(2, "Prepare vegetables", "Prepare potatoes, onions, and garlic for the curry.", "BB-ING-POTATOES, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC", "Prep Station", "", 1, 15, 0.3, 1, "Prep", "Vegetables are evenly prepared."),
			(3, "Build lentil curry", "Rinse the lentils under cold water until the runoff is mostly clear. Soften the onions in the curry pot without browning them, stir in the seasoning, then add lentils, potatoes, tomato, crumbled stock, and the saved water quantity. Bring to a controlled boil, reduce to a simmer, stir from the bottom, and cook until the lentils and potatoes are tender.", "BB-ING-LENTILS, BB-ING-POTATOES, BB-ING-TOMATO-ONION-MIX, BB-ING-CURRY-POWDER", "Curry Pot", "2", 0, 25, 0.4, 1, "Cook", "The base is mixed without scorching and the lentils are tender."),
			(4, "Finish and portion", "Cook to the approved texture, confirm total weight, and portion with rice.", "BB-ING-PARBOILED-RICE", "Prep Station", "1, 3", 0, 12, 0.2, 2, "Portioning", "Lentils and potatoes are tender and final weight is recorded."),
		],
		"BB-RECIPE-00003": [
			(1, "Start pasta water", "Bring the scaled cooking water to temperature and prepare the pasta batch.", "BB-ING-BASIC-PASTA", "Rice Pot", "", 1, 10, 0.15, 1, "Cook", "Water and pasta quantities match the batch."),
			(2, "Prepare sauce base", "Prepare onions and garlic, then soften them with the seasoning and tomato base.", "BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-TOMATO-ONION-MIX", "Curry Pot", "", 1, 15, 0.25, 1, "Cook", "The tomato base is evenly mixed."),
			(3, "Cook lentils and pasta", "Cook the lentil sauce and pasta concurrently, following the saved batch quantities.", "BB-ING-LENTILS, BB-ING-BASIC-PASTA", "Curry Pot", "1, 2", 0, 25, 0.35, 2, "Cook", "Pasta and lentils reach the approved texture."),
			(4, "Combine and portion", "Combine as specified, confirm the finished weight, and portion the meal.", "BB-ING-BASIC-PASTA, BB-ING-LENTILS", "Prep Station", "3", 0, 10, 0.15, 2, "Portioning", "Final weight and container count are recorded."),
		],
		"BB-RECIPE-00004": [
			(1, "Prepare rice", "Rinse the rice, measure the cooking water, and start the rice batch.", "BB-ING-PARBOILED-RICE", "Rice Pot", "", 1, 10, 0.25, 1, "Cook", "Rice is rinsed and water is measured against the scaled batch."),
			(2, "Prepare vegetables and chicken", "Prepare potatoes and onions, then prepare the chicken separately using clean tools and surfaces.", "BB-ING-CHICKEN-BREAST, BB-ING-POTATOES, BB-ING-ONIONS", "Prep Station", "", 1, 15, 0.35, 1, "Prep", "Raw chicken remains separate from ready-to-eat surfaces and prepared vegetables."),
			(3, "Start curry base", "Heat the oil, soften the onions, then add garlic and curry powder to form the curry base.", "BB-ING-SUNFLOWER-OIL, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-CURRY-POWDER", "Curry Pot", "2", 0, 12, 0.15, 1, "Cook", "Onions are softened and the spice base is evenly mixed without scorching."),
			(4, "Cook the curry", "Add chicken, potatoes, tomato and onion mix, stock, and scaled water. Cook until the batch reaches the recipe texture and the chicken is fully cooked according to the kitchen's verified food-safety procedure.", "BB-ING-CHICKEN-BREAST, BB-ING-POTATOES, BB-ING-TOMATO-ONION-MIX, BB-ING-STOCK-CUBES", "Curry Pot", "3", 0, 25, 0.4, 1, "Cook", "Use the kitchen's approved temperature and texture checks, then record any deviation."),
			(5, "Finish and portion", "Combine the completed components as specified, confirm the total finished weight, and portion the batch into containers.", "BB-ING-PARBOILED-RICE", "Prep Station", "1, 4", 0, 10, 0.2, 2, "Portioning", "Finished weight and container count match what the team records for this run."),
		],
	}
	for recipe_name, steps in recipe_steps.items():
		if not frappe.db.exists("BulkBite Recipe", recipe_name):
			continue
		recipe = frappe.get_doc("BulkBite Recipe", recipe_name)
		recipe.instruction_guidance = "Run independent cooking and preparation steps concurrently where the assigned team and clean equipment allow it. Review finished weight before portioning."
		recipe.set("instruction_steps", [])
		for step in steps:
			recipe.append("instruction_steps", dict(zip(("step_number", "step_name", "instruction", "ingredient_items", "equipment_type", "depends_on_steps", "can_run_concurrently", "duration_minutes", "duration_per_kg_minutes", "minimum_workers", "worker_role", "quality_checkpoint"), step)))
		recipe.save(ignore_permissions=True)


def _ensure_supplier_offers():
	"""Create one current supplier pack offer for every purchased demo item."""
	offer_rows = [
		("BB-ING-PARBOILED-RICE", "Makro", "DEMO-RICE-10KG", 1, 10, "Kg", 149.95, 139.95),
		("BB-ING-DRY-BEANS", "Makro", "DEMO-BEANS-10KG", 1, 10, "Kg", 529.90, 0),
		("BB-ING-LENTILS", "Makro", "DEMO-LENTILS-10KG", 1, 10, "Kg", 579.90, 549.90),
		("BB-ING-BASIC-PASTA", "Makro", "DEMO-PASTA-10KG", 1, 10, "Kg", 699.90, 0),
		("BB-ING-TOMATO-ONION-MIX", "Makro", "DEMO-TOMATO-MIX-6X410", 6, 410, "g", 119.00, 109.00),
		("BB-ING-TOMATO-PUREE", "Makro", "DEMO-PUREE-410", 1, 410, "g", 39.95, 0),
		("BB-ING-SUNFLOWER-OIL", "Makro", "DEMO-OIL-2L", 1, 2, "Litre", 79.95, 72.95),
		("BB-ING-CURRY-POWDER", "Makro", "DEMO-CURRY-800G", 1, 800, "g", 169.95, 0),
		("BB-ING-STOCK-CUBES", "Makro", "DEMO-STOCK-24X10G", 24, 10, "g", 31.95, 28.95),
		("BB-ING-SALT", "Makro", "DEMO-SALT-1KG", 1, 1, "Kg", 15.95, 0),
		("BB-ING-MIXED-HERBS", "Makro", "DEMO-HERBS-500G", 1, 500, "g", 139.95, 0),
		("BB-ING-POTATOES", "Checkers", "DEMO-POTATO-10KG", 1, 10, "Kg", 109.99, 99.99),
		("BB-ING-ONIONS", "Checkers", "DEMO-ONION-10KG", 1, 10, "Kg", 179.99, 159.99),
		("BB-ING-CRUSHED-GARLIC", "Checkers", "DEMO-GARLIC-500G", 1, 500, "g", 52.99, 0),
		("BB-ING-CHICKEN-BREAST", "Checkers", "DEMO-CHICKEN-5KG", 1, 5, "Kg", 524.95, 499.95),
		("BB-ING-VALUE-BEEF-MINCE", "Checkers", "DEMO-MINCE-5KG", 1, 5, "Kg", 599.95, 0),
		("BB-PACK-MEAL-CONTAINER-750", "Cape Food Packaging", "DEMO-CONTAINER-100", 100, 1, "Each", 325.00, 299.00),
	]
	names = []
	for item, supplier, supplier_code, units, size, uom, normal, discounted in offer_rows:
		name = frappe.db.get_value("BulkBite Supplier Offer", {"supplier_item_code": supplier_code}, "name")
		if not name:
			doc = frappe.get_doc(
				{
					"doctype": "BulkBite Supplier Offer",
					"item_code": item,
					"supplier": supplier,
					"supplier_item_code": supplier_code,
					"effective_from": DEMO_PERIOD_START,
					"units_per_pack": units,
					"unit_size": size,
					"purchase_uom": uom,
					"normal_price": normal,
					"discounted_price": discounted,
					"discount_from": DEMO_PERIOD_START if discounted else None,
					"discount_to": DEMO_PERIOD_END if discounted else None,
					"currency": "ZAR",
					"price_includes_vat": 1,
					"vat_rate": 15,
					"price_source": "DEMO August supplier catalogue",
					"source_date": DEMO_PERIOD_START,
					"last_verified_on": DEMO_PERIOD_START,
					"preferred": 1,
					"enabled": 1,
					"notes": f"{DEMO_MARKER}. Theoretical supplier price.",
				}
			).insert(ignore_permissions=True)
			name = doc.name
		names.append(name)
	return names


def _ensure_price_adjustments():
	rows = [
		{
			"adjustment_code": "DEMO-MAKRO-FREE-DELIVERY",
			"adjustment_name": "Makro free delivery over R5 000",
			"scope_type": "Basket",
			"supplier": "Makro",
			"adjustment_type": "Free Delivery",
			"calculation_basis": "Fixed",
			"value": 350,
			"threshold_amount": 5000,
		},
		{
			"adjustment_code": "DEMO-CHECKERS-DELIVERY",
			"adjustment_name": "Checkers delivery charge",
			"scope_type": "Supplier",
			"supplier": "Checkers",
			"adjustment_type": "Delivery Fee",
			"calculation_basis": "Fixed",
			"value": 99,
		},
		{
			"adjustment_code": "DEMO-TOMATO-REBATE",
			"adjustment_name": "Bulk tomato mix rebate",
			"scope_type": "Item",
			"item_code": "BB-ING-TOMATO-ONION-MIX",
			"adjustment_type": "Percentage Discount",
			"calculation_basis": "Pack Price",
			"value": 5,
		},
	]
	names = []
	for values in rows:
		values.update(
			{
				"effective_from": DEMO_PERIOD_START,
				"effective_to": DEMO_PERIOD_END,
				"priority": 100,
				"stackable": 1,
				"vat_treatment": "As Configured",
				"enabled": 1,
				"notes": f"{DEMO_MARKER}. Buying-cost scenario.",
			}
		)
		names.append(_ensure_named_doc("BulkBite Price Adjustment", values["adjustment_code"], values).name)
	return names


# endregion MASTER DATA


# =============================================================================
# region WORKFORCE AND DIRECTION
# =============================================================================


def ensure_demo_workforce():
	"""Ensure employee profiles and one reusable production team."""
	types = [
		("DEMO Cook", "Kg per Production Run", 80, 5, "Per Production Run", 350),
		("DEMO Kitchen Assistant", "Kg per Production Run", 65, 5, "Hourly", 45),
		("DEMO Packing Assistant", "Meals per Production Run", 350, 5, "Monthly", 6500),
	]
	for name, basis, capacity, hours, payment_basis, rate in types:
		_ensure_named_doc(
			"BulkBite Employee Type",
			name,
			{
				"employee_type_name": name,
				"description": f"{DEMO_MARKER}. Operational capacity role.",
				"capacity_basis": basis,
				"capacity_per_worker": capacity,
				"expected_hours_per_run": hours,
				"payment_basis": payment_basis,
				"payment_rate": rate,
				"working_assumptions": "One planned shift is five elapsed hours. Actual run attendance replaces this theory.",
				"enabled": 1,
			},
		)

	employee_rows = [
		("DEMO Thandi Mokoena", "DEMO Cook", 5, "thandi.demo@bulkbite.co.za", "0710001001", "Active"),
		("DEMO Sipho Dlamini", "DEMO Kitchen Assistant", 5, "sipho.demo@bulkbite.co.za", "0710001002", "Active"),
		("DEMO Lerato Nkosi", "DEMO Kitchen Assistant", 5, "lerato.demo@bulkbite.co.za", "0710001003", "Active"),
		("DEMO Musa Khumalo", "DEMO Packing Assistant", 5, "musa.demo@bulkbite.co.za", "0710001004", "Active"),
		("DEMO Ayesha Patel", "DEMO Kitchen Assistant", 0, "ayesha.demo@bulkbite.co.za", "0710001005", "On Leave"),
	]
	employees = []
	for full_name, employee_type, hours, email, phone, status in employee_rows:
		name = frappe.db.get_value("BulkBite Employee", {"full_name": full_name}, "name")
		values = {
			"full_name": full_name,
			"employee_type": employee_type,
			"status": status,
			"available_for_production": status == "Active",
			"available_hours_per_run": hours,
			"email_address": email,
			"phone_number": phone,
			"start_date": "2026-07-01",
			"notes": f"{DEMO_MARKER}. Training and operational profile.",
		}
		if name:
			doc = frappe.get_doc("BulkBite Employee", name)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "BulkBite Employee", **values}).insert(ignore_permissions=True)
		employees.append(doc.name)

	template_name = "DEMO Standard Production Team"
	template = frappe.get_doc("BulkBite Team Template", template_name) if frappe.db.exists("BulkBite Team Template", template_name) else frappe.new_doc("BulkBite Team Template")
	template.update(
		{
			"template_name": template_name,
			"enabled": 1,
			"default_elapsed_hours": 5,
			"notes": f"{DEMO_MARKER}. Normal four-person production crew.",
		}
	)
	template.set("members", [{"employee": employee, "enabled": 1} for employee in employees[:4]])
	template.save(ignore_permissions=True)
	return {"employee_types": [row[0] for row in types], "employees": employees, "team_template": template.name}


def ensure_demo_direction(master, workforce):
	"""Freeze the four-meal direction and its theoretical buying position before demo receipts."""
	plan_name = frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")

	recipes = frappe.get_all(
		"BulkBite Recipe", filters={"status": "Approved"}, fields=["name", "recipe_name", "finished_item"], order_by="name"
	)
	preferred_order = [
		"Bean & Potato Stew + Rice",
		"Chicken & Potato Curry + Rice",
		"Lentil & Potato Curry + Rice",
		"Lentil Tomato Macaroni",
	]
	recipe_by_title = {row.recipe_name: row for row in recipes}
	selected = [recipe_by_title[title] for title in preferred_order if title in recipe_by_title]
	if len(selected) != 4:
		frappe.throw("The full demo loader needs the four approved BulkBite recipes.")

	routes = [
		{
			"item_category": category,
			"supplier": frappe.get_cached_value("BulkBite Item Category", category, "default_supplier"),
			"use_discounted_price": category in {"Dry", "Vegetables", "Protein", "Packaging"},
		}
		for category in master["categories"]
	]
	payload = {
		"name": plan_name,
		"plan_title": "August operating direction, 45 customers",
		"period_start": DEMO_PERIOD_START,
		"period_end": DEMO_PERIOD_END,
		"customer_mix": [
			{"plan_type": "Lite", "customer_count": 18},
			{"plan_type": "Standard", "customer_count": 20},
			{"plan_type": "Full", "customer_count": 7},
		],
		"purchase_routes": routes,
		"plan_rows": [{"recipe": row.name, "finished_item": row.finished_item} for row in selected],
		"forecast_weeks": 8,
		"default_team_template": workforce["team_template"],
		"capacity_windows": [
			{"scheduled_elapsed_hours": 5, "runs_per_week": 2, "team_template": workforce["team_template"]},
			{"scheduled_elapsed_hours": 5, "runs_per_week": 2, "team_template": workforce["team_template"]},
			{"scheduled_elapsed_hours": 4, "runs_per_week": 1, "team_template": workforce["team_template"]},
			{"scheduled_elapsed_hours": 6, "runs_per_week": 2, "team_template": workforce["team_template"]},
		],
		"capacity_runs": [
			{"week_number": 1, "run_number": 1, "day_of_week": "Saturday", "scheduled_elapsed_hours": 5, "team_template": workforce["team_template"], "planned_people": 4},
			{"week_number": 1, "run_number": 2, "day_of_week": "Saturday", "scheduled_elapsed_hours": 5, "team_template": workforce["team_template"], "planned_people": 4},
			{"week_number": 2, "run_number": 1, "day_of_week": "Saturday", "scheduled_elapsed_hours": 5, "team_template": workforce["team_template"], "planned_people": 4},
			{"week_number": 2, "run_number": 2, "day_of_week": "Saturday", "scheduled_elapsed_hours": 5, "team_template": workforce["team_template"], "planned_people": 4},
			{"week_number": 3, "run_number": 1, "day_of_week": "Saturday", "scheduled_elapsed_hours": 4, "team_template": workforce["team_template"], "planned_people": 3},
			{"week_number": 4, "run_number": 1, "day_of_week": "Saturday", "scheduled_elapsed_hours": 6, "team_template": workforce["team_template"], "planned_people": 4},
			{"week_number": 4, "run_number": 2, "day_of_week": "Saturday", "scheduled_elapsed_hours": 6, "team_template": workforce["team_template"], "planned_people": 4},
		],
		"forecast_customer_mix": [
			{"plan_type": "Lite", "target_customers": 26, "target_week": 8},
			{"plan_type": "Standard", "target_customers": 29, "target_week": 8},
			{"plan_type": "Full", "target_customers": 10, "target_week": 8},
		],
		"location": "Ingredients",
		"notes": f"{DEMO_MARKER}. Current theory for buying, capacity, production, and reporting tests.",
	}
	return save_monthly_production_plan(payload)["name"]


# endregion WORKFORCE AND DIRECTION


# =============================================================================
# region RECEIPTS AND STOCK
# =============================================================================


def ensure_demo_receipts(master):
	"""Post reviewed supplier receipts with pack quantities and actual price variance."""
	evidence = _ensure_private_file("DEMO-OPS-purchase-evidence.txt", "BulkBite demo purchase evidence for August 2026.")
	receipts = [
		{
			"supplier": "Makro",
			"supplier_invoice_number": "DEMO-OPS-MAKRO-20260802",
			"invoice_date": "2026-08-02",
			"accounting_category": "Food purchases, dry goods",
			"lines": [
				("BB-ING-PARBOILED-RICE", 26, 1, 10, "Kg", 147.50),
				("BB-ING-DRY-BEANS", 9, 1, 10, "Kg", 539.90),
				("BB-ING-LENTILS", 10, 1, 10, "Kg", 539.90),
				("BB-ING-BASIC-PASTA", 13, 1, 10, "Kg", 704.90),
				("BB-ING-TOMATO-ONION-MIX", 65, 6, 410, "g", 111.00),
				("BB-ING-TOMATO-PUREE", 12, 1, 410, "g", 37.50),
				("BB-ING-SUNFLOWER-OIL", 20, 1, 2, "Litre", 74.95),
				("BB-ING-CURRY-POWDER", 13, 1, 800, "g", 164.95),
				("BB-ING-STOCK-CUBES", 15, 24, 10, "g", 29.95),
				("BB-ING-SALT", 2, 1, 1, "Kg", 14.95),
				("BB-ING-MIXED-HERBS", 2, 1, 500, "g", 144.95),
			],
			"adjustments": [
				{"adjustment_type": "Rebate", "description": "Makro bulk-order rebate", "effect": "Saving", "amount": 425},
				{"adjustment_type": "Free Delivery", "description": "Free scheduled delivery", "effect": "Saving", "amount": 350},
			],
		},
		{
			"supplier": "Checkers",
			"supplier_invoice_number": "DEMO-OPS-CHECKERS-20260803",
			"invoice_date": "2026-08-03",
			"accounting_category": "Food purchases, fresh goods",
			"lines": [
				("BB-ING-POTATOES", 14, 1, 10, "Kg", 104.99),
				("BB-ING-ONIONS", 7, 1, 10, "Kg", 169.99),
				("BB-ING-CRUSHED-GARLIC", 12, 1, 500, "g", 55.99),
				("BB-ING-CHICKEN-BREAST", 13, 1, 5, "Kg", 509.95),
				("BB-ING-VALUE-BEEF-MINCE", 4, 1, 5, "Kg", 619.95),
			],
			"adjustments": [
				{"adjustment_type": "Delivery Fee", "description": "Cold-chain delivery", "effect": "Cost", "amount": 99},
			],
		},
		{
			"supplier": "Cape Food Packaging",
			"supplier_invoice_number": "DEMO-OPS-PACK-20260804",
			"invoice_date": "2026-08-04",
			"accounting_category": "Food packaging",
			"lines": [("BB-PACK-MEAL-CONTAINER-750", 12, 100, 1, "Each", 312.50)],
			"adjustments": [],
		},
	]
	names = []
	for spec in receipts:
		name = frappe.db.get_value(
			"BulkBite Receipt Intake", {"supplier_invoice_number": spec["supplier_invoice_number"]}, "name"
		)
		if not name:
			items = [
				{
					"item_code": item,
					"description": frappe.get_cached_value("BulkBite Item", item, "item_name"),
					"supplier_description": f"{DEMO_MARKER}. Reviewed supplier line.",
					"purchase_qty": packs,
					"units_per_pack": units,
					"unit_size": size,
					"purchase_uom": uom,
					"amount": round(packs * price_per_pack, 2),
					"location": "Ingredients" if item != "BB-PACK-MEAL-CONTAINER-750" else "Ingredients",
				}
				for item, packs, units, size, uom, price_per_pack in spec["lines"]
			]
			doc = frappe.get_doc(
				{
					"doctype": "BulkBite Receipt Intake",
					"receipt_file": evidence,
					"evidence_files": [{"evidence_file": evidence, "file_name": "DEMO purchase evidence"}],
					"business_name": "BulkBite",
					"supplier": spec["supplier"],
					"supplier_invoice_number": spec["supplier_invoice_number"],
					"invoice_date": spec["invoice_date"],
					"currency": "ZAR",
					"default_location": "Ingredients",
					"items": items,
					"adjustments": spec["adjustments"],
					"tax_amount": 0,
					"accounting_category": spec["accounting_category"],
					"review_notes": f"{DEMO_MARKER}. Reviewed pack quantities and actual supplier prices.",
				}
			).insert(ignore_permissions=True)
			name = doc.name
		if not frappe.db.get_value("BulkBite Receipt Intake", name, "stock_events_posted"):
			receive_stock_from_receipt(name)
		names.append(name)
	return names


# endregion RECEIPTS AND STOCK


# =============================================================================
# region PRODUCTION ACTUALS
# =============================================================================


def ensure_demo_production(plan_name, workforce):
	"""Post one complete meal cycle with attendance, takt evidence, usage variance, and labour cost."""
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	active_employees = workforce["employees"][:4]
	run_specs = [
		(1, "2026-08-05", 0.94, 1.04, 5.5, active_employees[:3]),
		(2, "2026-08-12", 1.02, 0.97, 4.8, active_employees),
		(3, "2026-08-19", 0.98, 1.08, 8.5, active_employees[:3]),
		(4, "2026-08-25", 1.05, 0.95, 4.4, active_employees),
	]
	posted = []
	for week, production_date, output_factor, usage_factor, elapsed, employees in run_specs:
		marker = f"{DEMO_MARKER} RUN WEEK {week}"
		name = frappe.db.get_value("BulkBite Production Run", {"notes": ["like", f"%{marker}%"]}, "name")
		row = next(item for item in plan.plan_rows if int(item.week_number) == week)
		if not name:
			if week == 1:
				name = frappe.db.get_value(
					"BulkBite Production Run",
					{"production_plan": plan.name, "plan_week_number": week, "cycle_number": 1, "docstatus": 0},
					"name",
					order_by="modified desc",
				)
			if name:
				run = frappe.get_doc("BulkBite Production Run", name)
				run.update(
					{
						"production_date": production_date,
						"production_plan_row": row.name,
						"plan_week_number": week,
						"cycle_number": 1,
						"direction_action": "Advance Direction",
						"recipe": row.recipe,
						"planned_output_qty": row.planned_output_qty,
						"actual_output_qty": row.planned_output_qty,
						"source_location": "Ingredients",
						"target_location": "Finished Meals",
						"team_template": workforce["team_template"],
						"scheduled_elapsed_hours": 5,
						"planned_takt_minutes_per_kg": 4.8,
						"notes": marker,
					}
				)
				run.save(ignore_permissions=True)
			else:
				run = frappe.get_doc(
					{
						"doctype": "BulkBite Production Run",
						"production_date": production_date,
						"business_name": "BulkBite",
						"production_plan": plan.name,
						"production_plan_row": row.name,
						"plan_week_number": week,
						"cycle_number": 1,
						"direction_action": "Advance Direction",
						"recipe": row.recipe,
						"planned_output_qty": row.planned_output_qty,
						"actual_output_qty": row.planned_output_qty,
						"source_location": "Ingredients",
						"target_location": "Finished Meals",
						"team_template": workforce["team_template"],
						"scheduled_elapsed_hours": 5,
						"planned_takt_minutes_per_kg": 4.8,
						"notes": marker,
					}
				).insert(ignore_permissions=True)
				name = run.name
		run = frappe.get_doc("BulkBite Production Run", name)
		if run.docstatus == 0:
			attendance = [
				{
					"employee": employee,
					"available_hours": 5,
					"custom_hours": employee == employees[-1] and week in {1, 3},
					"hours_worked": elapsed - 0.5 if employee == employees[-1] and week in {1, 3} else elapsed,
					"completion_status": "Completed",
				}
				for employee in employees
			]
			save_production_employees(name, attendance, workforce["team_template"], elapsed, 5)
			run = frappe.get_doc("BulkBite Production Run", name)
			measurements = [
				{
					"item_code": ingredient.item_code,
					"measurement_method": "Used",
					"actual_qty": round_operational_quantity(flt(ingredient.expected_qty) * usage_factor),
					"notes": "Measured after production. Includes normal preparation variance.",
				}
				for ingredient in run.ingredients
			]
			update_production_actuals(
				name,
				round_operational_quantity(flt(run.planned_output_qty) * output_factor),
				measurements,
				marker,
				max(int(round(flt(run.planned_output_qty) * output_factor / 0.75)), 1),
			)
			submit_production_run(name)
		posted.append(name)
		run = frappe.get_doc("BulkBite Production Run", name)
		allocation_specs = [
			("Current Customers", min(flt(run.actual_output_qty), 20), f"Demo week {week} customers"),
			("Internal Consumption", min(max(flt(run.actual_output_qty) - 20, 0), 2), f"Demo week {week} team meal"),
		]
		for allocation_type, quantity, reference in allocation_specs:
			if quantity <= 0 or frappe.db.exists("BulkBite Finished Food Allocation", {"source_production_run": name, "allocation_type": allocation_type, "demand_period": reference}):
				continue
			allocate_finished_food({
				"posting_date": production_date,
				"finished_item": run.finished_item,
				"source_location": "Finished Meals",
				"source_production_run": name,
				"allocation_type": allocation_type,
				"demand_period": reference,
				"quantity": quantity,
				"notes": f"{DEMO_MARKER}. Finished-food allocation example.",
			})

	draft_marker = f"{DEMO_MARKER} NEXT CYCLE DRAFT"
	draft = frappe.db.get_value("BulkBite Production Run", {"notes": ["like", f"%{draft_marker}%"]}, "name")
	if not draft:
		row = next(item for item in plan.plan_rows if int(item.week_number) == 1)
		doc = frappe.get_doc(
			{
				"doctype": "BulkBite Production Run",
				"production_date": "2026-08-26",
				"business_name": "BulkBite",
				"production_plan": plan.name,
				"production_plan_row": row.name,
				"plan_week_number": 1,
				"cycle_number": 2,
				"direction_action": "Advance Direction",
				"recipe": row.recipe,
				"planned_output_qty": row.planned_output_qty,
				"actual_output_qty": row.planned_output_qty,
				"source_location": "Ingredients",
				"target_location": "Finished Meals",
				"team_template": workforce["team_template"],
				"scheduled_elapsed_hours": 5,
				"planned_takt_minutes_per_kg": 4.8,
				"notes": draft_marker,
			}
		).insert(ignore_permissions=True)
		draft = doc.name
	return {"posted": posted, "draft": draft}


# endregion PRODUCTION ACTUALS


# =============================================================================
# region CONTAINERS AND RECURRING WORK
# =============================================================================


def ensure_demo_containers(production):
	"""Create a visible container fleet with clean, filled, customer, overdue, and maintenance examples."""
	container_type = _ensure_named_doc(
		"BulkBite Container Type",
		"Standard 750 ml Reusable Container",
		{
			"container_type_name": "Standard 750 ml Reusable Container",
			"stock_item": "BB-PACK-MEAL-CONTAINER-750",
			"enabled": 1,
			"default_for_production": 1,
			"capacity_qty": 0.75,
			"capacity_uom": "Kg",
			"replacement_price": 35,
			"non_return_charge_multiplier": 2,
			"expected_return_days": 7,
			"notes": f"{DEMO_MARKER}. Default reusable customer container.",
		},
	)
	states = [
		("BB-CONT-001", "Clean", None, None),
		("BB-CONT-002", "Clean", None, None),
		("BB-CONT-003", "Filled", None, None),
		("BB-CONT-004", "With Customer", "DEMO-CUSTOMER-04", "2026-09-03"),
		("BB-CONT-005", "With Customer", "DEMO-CUSTOMER-05", "2026-08-20"),
		("BB-CONT-006", "Maintenance", None, None),
		("BB-CONT-007", "Lost", None, None),
	]
	assets = []
	for code, state, customer, return_date in states:
		asset = _ensure_named_doc(
			"BulkBite Container Asset",
			code,
			{
				"asset_code": code,
				"container_type": container_type.name,
				"lifecycle_state": state,
				"current_customer_reference": customer,
				"expected_return_date": return_date,
				"acquisition_date": "2026-08-01",
				"enabled": 1,
				"notes": f"{DEMO_MARKER}. Container lifecycle example.",
			},
		)
		assets.append(asset.name)
	for code, movement, date, customer, run in [
		("BB-CONT-003", "Filled for Production", "2026-08-25", None, production["posted"][-1]),
		("BB-CONT-004", "Issued to Customer", "2026-08-27", "DEMO-CUSTOMER-04", production["posted"][-1]),
		("BB-CONT-005", "Issued to Customer", "2026-08-13", "DEMO-CUSTOMER-05", production["posted"][1]),
		("BB-CONT-006", "Sent to Maintenance", "2026-08-24", None, None),
		("BB-CONT-007", "Marked Lost", "2026-08-29", "DEMO-CUSTOMER-07", production["posted"][-1]),
	]:
		if frappe.db.exists("BulkBite Container Movement", {"container_asset": code, "movement_type": movement, "posting_date": date}):
			existing = frappe.db.get_value("BulkBite Container Movement", {"container_asset": code, "movement_type": movement, "posting_date": date}, ["name", "target_state"], as_dict=True)
			target = {"Filled for Production": "Filled", "Issued to Customer": "With Customer", "Sent to Maintenance": "Maintenance", "Marked Lost": "Lost"}[movement]
			frappe.db.set_value("BulkBite Container Movement", existing.name, "target_state", target, update_modified=False)
			if movement == "Marked Lost":
				frappe.db.set_value("BulkBite Container Movement", existing.name, "replacement_charge", 70, update_modified=False)
			frappe.db.set_value("BulkBite Container Asset", code, {"lifecycle_state": target, "current_customer_reference": customer if target == "With Customer" else None, "expected_return_date": add_days(date, 7) if target == "With Customer" else None}, update_modified=False)
			continue
		asset = frappe.get_doc("BulkBite Container Asset", code)
		source = {"Filled for Production": "Clean", "Issued to Customer": "Filled", "Sent to Maintenance": "Clean", "Marked Lost": "With Customer"}[movement]
		asset.db_set({"lifecycle_state": source, "current_customer_reference": None, "expected_return_date": None}, update_modified=False)
		doc = frappe.get_doc({
			"doctype": "BulkBite Container Movement",
			"posting_date": date,
			"container_asset": code,
			"movement_type": movement,
			"customer_reference": customer,
			"production_run": run,
			"notes": f"{DEMO_MARKER}. Container movement example.",
		}).insert(ignore_permissions=True)
		doc.submit()
	return {"type": container_type.name, "assets": assets}


def ensure_demo_operational_actions():
	"""Create repeating duties plus completed, missed, upcoming, and rescheduled examples."""
	settings = frappe.get_single("BulkBite Settings")
	settings.kitchen_default_slack_minutes = 10
	settings.use_ai_kitchen_instructions = 1
	settings.kitchen_settings_note = f"{DEMO_MARKER}. AI proposes method detail; recipe quantities and CPM scheduling remain deterministic."
	settings.save(ignore_permissions=True)
	schedules = [
		("Monthly stock reconciliation", "Stock Reconciliation", "Monthly", None, 28, "stock", "Count physical stock and approve any correcting stock event."),
		("Monthly accountant export", "Accountant Export", "Monthly", None, 2, "export", "Export the prior period for accountant review."),
		("Weekly container return review", "Container Reconciliation", "Weekly", "Friday", None, "operations", "Review overdue returns and record each return, loss, or maintenance issue."),
	]
	for name, action_type, recurrence, weekday, month_day, section, notes in schedules:
		_ensure_named_doc("BulkBite Operational Schedule", name, {
			"schedule_name": name,
			"enabled": 1,
			"action_type": action_type,
			"recurrence": recurrence,
			"interval": 1,
			"day_of_week": weekday,
			"day_of_month": month_day,
			"lead_days": 4,
			"default_section": section,
			"start_date": "2026-08-01",
			"notes": f"{DEMO_MARKER}. {notes}",
		})
	materialize_operational_actions(from_date="2026-08-01", to_date="2026-10-31")
	completed = frappe.db.get_value("BulkBite Operational Action", {"schedule": "Monthly stock reconciliation", "due_date": "2026-08-28"}, "name")
	if completed:
		frappe.db.set_value("BulkBite Operational Action", completed, {"status": "Completed", "completed_on": "2026-08-28"}, update_modified=False)
	rescheduled = frappe.db.get_value("BulkBite Operational Action", {"schedule": "Monthly accountant export", "due_date": "2026-09-02"}, "name")
	if rescheduled:
		frappe.db.set_value("BulkBite Operational Action", rescheduled, {"status": "Rescheduled", "rescheduled_to": "2026-09-04", "notes": f"{DEMO_MARKER}. Accountant requested a later handoff."}, update_modified=False)
	return [row.name for row in frappe.get_all("BulkBite Operational Action", filters={"schedule": ["in", [row[0] for row in schedules]]}, fields=["name"])]


# endregion CONTAINERS AND RECURRING WORK


# =============================================================================
# region FINANCE AND RECONCILIATION
# =============================================================================


def ensure_demo_finance_setup(master):
	"""Ensure expected overhead rules and invoice expense classifications."""
	expense_types = [
		("Production labour", "Labour", "Other", "Wages and production labour"),
		("Electricity and utilities", "Utilities", "Utilities", "Utilities"),
		("Rent and property", "Rent", "Rent and Property", "Premises"),
		("Delivery and logistics", "Delivery", "Delivery and Logistics", "Distribution"),
		("Packaging", "Packaging", "General Supplier Invoice", "Packaging"),
		("Cleaning and sanitation", "Kitchen Consumables", "General Supplier Invoice", "Kitchen consumables"),
		("Software subscriptions", "Other Production Overhead", "Telecoms and Software", "Software"),
	]
	resolved = {}
	for label, category, document_type, accounting in expense_types:
		name = frappe.db.get_value("BulkBite Expense Type", {"expense_type_name": label}, "name")
		if not name:
			name = frappe.get_doc(
				{
					"doctype": "BulkBite Expense Type",
					"expense_type_name": label,
					"cost_category": category,
					"document_type": document_type,
					"default_vat_treatment": "Inclusive",
					"accounting_category": accounting,
					"enabled": 1,
					"notes": f"{DEMO_MARKER}. Finance classification.",
				}
			).insert(ignore_permissions=True).name
		resolved[label] = name

	rules = [
		("DEMO-RENT", "Kitchen rent", "Rent", "Fixed", 12000, 1, "Monthly", "Cape Kitchen Properties"),
		("DEMO-UTILITIES", "Electricity, water and gas", "Utilities", "Fixed", 3500, 1, "Monthly", "City Utilities"),
		("DEMO-DELIVERY", "Weekly customer delivery", "Delivery", "Fixed", 450, 1, "Weekly", "Local Courier Network"),
		("DEMO-PACKAGING", "Packaging per meal", "Packaging", "Per Meal", 2.2, 1, "Per Period", "Cape Food Packaging"),
		("DEMO-CLEANING", "Cleaning consumables", "Kitchen Consumables", "Fixed", 950, 1, "Monthly", "Kitchen Hygiene Supplies"),
		("DEMO-SOFTWARE", "Ordering and finance software", "Other Production Overhead", "Fixed", 799, 1, "Monthly", "Cloud Software"),
	]
	for code, name, category, basis, rate, quantity, recurrence, payee in rules:
		_ensure_named_doc(
			"BulkBite Operating Cost Rule",
			code,
			{
				"cost_code": code,
				"cost_name": name,
				"cost_category": category,
				"basis": basis,
				"rate": rate,
				"employee_count": 1,
				"hours_per_employee": 0,
				"default_quantity": quantity,
				"recurrence": recurrence,
				"effective_from": DEMO_PERIOD_START,
				"vat_treatment": "Inclusive",
				"accounting_category": category,
				"payee": payee,
				"enabled": 1,
				"notes": f"{DEMO_MARKER}. Expected operating-cost assumption.",
			},
		)
	return {"expense_types": resolved, "rules": [row[0] for row in rules]}


def ensure_demo_cost_invoices(plan_name, finance_setup):
	"""Post reviewed overhead invoices into the immutable finance ledger."""
	evidence = _ensure_private_file("DEMO-OPS-cost-invoice-evidence.txt", "BulkBite demo overhead invoice evidence for August 2026.")
	expense_types = finance_setup["expense_types"]
	specs = [
		{
			"invoice_number": "DEMO-OPS-UTIL-202608",
			"document_type": "Utilities",
			"payee": "City Utilities",
			"invoice_date": "2026-08-08",
			"tax_amount": 495,
			"costs": [("August electricity, water and gas", "Electricity and utilities", "Utilities", 3300, "DEMO-UTILITIES")],
		},
		{
			"invoice_number": "DEMO-OPS-RENT-202608",
			"document_type": "Rent and Property",
			"payee": "Cape Kitchen Properties",
			"invoice_date": "2026-08-01",
			"tax_amount": 0,
			"costs": [("August kitchen rental", "Rent and property", "Rent", 12250, "DEMO-RENT")],
		},
		{
			"invoice_number": "DEMO-OPS-HYGIENE-202608",
			"document_type": "General Supplier Invoice",
			"payee": "Kitchen Hygiene Supplies",
			"invoice_date": "2026-08-18",
			"tax_amount": 180,
			"costs": [("Cleaning chemicals and disposable gloves", "Cleaning and sanitation", "Kitchen Consumables", 1200, "DEMO-CLEANING")],
		},
	]
	names = []
	for spec in specs:
		name = frappe.db.get_value("BulkBite Cost Invoice", {"invoice_number": spec["invoice_number"]}, "name")
		if not name:
			costs = [
				{
					"description": description,
					"expense_type": expense_types[expense_label],
					"cost_rule": rule,
					"cost_category": category,
					"quantity": 1,
					"unit_rate": amount,
					"amount": amount,
					"vat_amount": 0,
					"accounting_category": category,
					"confidence": 97,
					"source_quote": description,
					"notes": f"{DEMO_MARKER}. Reviewed invoice line.",
				}
				for description, expense_label, category, amount, rule in spec["costs"]
			]
			doc = frappe.get_doc(
				{
					"doctype": "BulkBite Cost Invoice",
					"document_type": spec["document_type"],
					"payee": spec["payee"],
					"invoice_number": spec["invoice_number"],
					"invoice_date": spec["invoice_date"],
					"currency": "ZAR",
					"evidence_files": [{"evidence_file": evidence, "file_name": "DEMO overhead invoice evidence"}],
					"costs": costs,
					"tax_amount": spec["tax_amount"],
					"production_plan": plan_name,
					"review_notes": f"{DEMO_MARKER}. Reviewed against the source invoice.",
				}
			).insert(ignore_permissions=True)
			name = doc.name
		if not frappe.db.get_value("BulkBite Cost Invoice", name, "costs_posted"):
			post_cost_invoice(name)
		names.append(name)
	return names


def ensure_demo_reconciliation():
	"""Approve one physical count with both a small gain and a small loss."""
	marker = f"{DEMO_MARKER}. Month-end physical count"
	name = frappe.db.get_value("BulkBite Stock Audit", {"notes": ["like", f"%{marker}%"]}, "name")
	if name:
		return name
	items = []
	for item_code, variance in (
		("BB-ING-PARBOILED-RICE", -1.2),
		("BB-ING-POTATOES", 2.5),
		("BB-ING-SUNFLOWER-OIL", -0.2),
	):
		current = get_stock_balance(item_code, "Ingredients")
		items.append({"item_code": item_code, "location": "Ingredients", "qty": max(current + variance, 0)})
	audit = create_stock_count_draft({"posting_date": "2026-08-26", "notes": marker, "items": items})
	approve_stock_audit(audit["name"])
	return audit["name"]


# endregion FINANCE AND RECONCILIATION


# =============================================================================
# region SUPPORTING HISTORY
# =============================================================================


def ensure_demo_supporting_history(audit_name, master):
	"""Add worker-sheet and price-import history records that point back to the connected demo."""
	worker_file = _ensure_private_file(
		"DEMO-OPS-worker-stock-count.txt",
		"Parboiled Rice counted after production\nPotatoes counted after production\nSunflower Oil counted after production",
	)
	intake_name = frappe.db.get_value("BulkBite Document Intake", {"source_file": worker_file}, "name")
	if not intake_name:
		intake = frappe.get_doc(
			{
				"doctype": "BulkBite Document Intake",
				"status": "Reviewed",
				"document_type": "Stock Audit",
				"source_file": worker_file,
				"source_hash": "DEMO-OPS-WORKER-COUNT-20260826",
				"business_name": "BulkBite",
				"default_location": "Ingredients",
				"text_provider": "DEMO reviewed transcription",
				"parser_mode": "Reviewed structured extraction",
				"processed_at": "2026-08-26 15:30:00",
				"raw_text": "Parboiled Rice, Potatoes and Sunflower Oil counted after production.",
				"extraction_evidence": json.dumps({"source": "worker sheet", "reviewed": True}),
				"rows": [
					{
						"source_line": "Parboiled Rice counted after production",
						"source_quote": "Parboiled Rice",
						"proposed_item_name": "Parboiled Rice",
						"item_code": "BB-ING-PARBOILED-RICE",
						"qty": get_stock_balance("BB-ING-PARBOILED-RICE", "Ingredients"),
						"uom": "Kg",
						"confidence": 96,
						"accepted": 1,
					},
					{
						"source_line": "Potatoes counted after production",
						"source_quote": "Potatoes",
						"proposed_item_name": "Potatoes",
						"item_code": "BB-ING-POTATOES",
						"qty": get_stock_balance("BB-ING-POTATOES", "Ingredients"),
						"uom": "Kg",
						"confidence": 94,
						"accepted": 1,
					},
				],
				"warnings": "One oil quantity was checked manually before the reconciliation was approved.",
				"reviewed_by": "Administrator",
				"reviewed_at": "2026-08-26 15:40:00",
				"applied_reference_doctype": "BulkBite Stock Audit",
				"applied_reference": audit_name,
			}
		).insert(ignore_permissions=True)
		intake.db_set(
			{
				"status": "Applied",
				"applied_reference_doctype": "BulkBite Stock Audit",
				"applied_reference": audit_name,
			},
			update_modified=False,
		)
		intake_name = intake.name

	price_file = _ensure_private_file(
		"DEMO-OPS-price-import.csv",
		"item_code,supplier,normal_pack_price\nBB-ING-PARBOILED-RICE,Makro,149.95\nBB-ING-POTATOES,Checkers,109.99\n",
	)
	batch_name = frappe.db.get_value("BulkBite Price Import Batch", {"source_file": price_file}, "name")
	if not batch_name:
		batch = frappe.get_doc(
			{
				"doctype": "BulkBite Price Import Batch",
				"status": "Applied",
				"source_file": price_file,
				"total_rows": 2,
				"insert_count": 0,
				"update_count": 2,
				"unchanged_count": 0,
				"error_count": 0,
				"preview_json": json.dumps({"matched_fields": ["item_code", "supplier", "normal_pack_price"]}),
				"applied_on": "2026-08-01 09:00:00",
				"applied_by": "Administrator",
				"result_json": json.dumps({"demo": True, "offers": master["supplier_offers"][:2]}),
			}
		).insert(ignore_permissions=True)
		batch_name = batch.name
	return {"worker_document_intake": intake_name, "price_import_batch": batch_name}


# endregion SUPPORTING HISTORY


# =============================================================================
# region SHARED HELPERS
# =============================================================================


def _ensure_named_doc(doctype, name, values):
	"""Create or update one mutable named master record."""
	doc = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else frappe.new_doc(doctype)
	doc.update(values)
	doc.save(ignore_permissions=True)
	return doc


def _ensure_private_file(file_name, content):
	"""Reuse one deterministic private evidence file."""
	file_url = frappe.db.get_value("File", {"file_name": file_name, "is_private": 1}, "file_url")
	if file_url:
		return file_url
	return save_file(file_name, content.encode("utf-8"), None, None, is_private=1).file_url


# endregion SHARED HELPERS
