from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from bulkbite.stock_ledger import append_stock_event, get_stock_balance, get_valuation_rate
from bulkbite.truth_ledger import append_truth_event
from bulkbite.variance import calculate_output_variance, calculate_usage_variance


# =============================================================================
# region PRODUCTION THEORY
# =============================================================================


def round_operational_quantity(value, precision=3):
	"""Return a stable decimal quantity for forms, API payloads, and stock theory."""
	return round(flt(value), precision)


def load_expected_usage(recipe_name, planned_output_qty, source_location):
	"""Scale one approved custom recipe into a frozen production expectation."""
	recipe = frappe.get_doc("BulkBite Recipe", recipe_name)
	if recipe.status != "Approved":
		frappe.throw(_("Select an approved recipe version."))
	planned_output = round_operational_quantity(planned_output_qty)
	if planned_output <= 0:
		frappe.throw(_("Planned output must be greater than zero."))
	scale = planned_output / flt(recipe.nominal_output_qty or 1)
	return {
		"finished_item": recipe.finished_item,
		"recipe_output_qty": flt(recipe.nominal_output_qty),
		"output_uom": recipe.output_uom,
		"ingredients": [
			{
				"item_code": row.item_code,
				"item_name": frappe.get_cached_value("BulkBite Item", row.item_code, "item_name"),
				"source_location": source_location,
				"uom": row.uom,
				"expected_qty": round_operational_quantity(flt(row.qty) * scale),
				"actual_qty": round_operational_quantity(flt(row.qty) * scale),
				"measurement_method": "Used",
				"available_before_measurement": get_available_stock(row.item_code, source_location),
				"valuation_rate": get_valuation_rate(row.item_code, source_location),
			}
			for row in recipe.ingredients
		],
	}


def apply_run_variances(run):
	output = calculate_output_variance(run.planned_output_qty, run.actual_output_qty)
	run.output_variance_qty = output["variance_qty"]
	run.output_variance_percent = output["variance_percent"]
	expected_cost = 0
	actual_cost = 0
	for row in run.ingredients:
		result = calculate_usage_variance(row.expected_qty, row.actual_qty, row.valuation_rate)
		for field in ("variance_qty", "variance_percent", "expected_cost", "actual_cost", "cost_variance"):
			setattr(row, field, result[field])
		expected_cost += result["expected_cost"]
		actual_cost += result["actual_cost"]
	run.expected_material_cost = expected_cost
	run.actual_material_cost = actual_cost
	run.material_cost_variance = actual_cost - expected_cost
	run.expected_cost_per_meal = expected_cost / flt(run.planned_output_qty) if run.planned_output_qty else 0
	run.actual_cost_per_meal = actual_cost / flt(run.actual_output_qty) if run.actual_output_qty else 0


def get_available_stock(item_code, location):
	return get_stock_balance(item_code, location)


def derive_usage_from_remaining(available_qty, remaining_qty):
	available = flt(available_qty)
	remaining = flt(remaining_qty)
	if remaining < 0:
		frappe.throw(_("Remaining stock cannot be negative."))
	if remaining > available:
		frappe.throw(
			_("Remaining stock ({0}) cannot exceed available stock ({1}). Record missing receipts, then measure again.").format(
				remaining, available
			)
		)
	return available - remaining


# endregion PRODUCTION THEORY


# =============================================================================
# region CUSTOM STOCK POSTING
# =============================================================================


def post_production_run(run):
	"""Post ingredient consumption and finished output through the BulkBite journal."""
	if run.stock_events_posted:
		return frappe.get_doc("BulkBite Stock Event", run.output_stock_event)
	for row in run.ingredients:
		available = get_available_stock(row.item_code, row.source_location or run.source_location)
		if flt(row.actual_qty) > available:
			frappe.throw(
				_("Usage for {0} ({1}) cannot exceed available stock ({2}).").format(
					row.item_code, flt(row.actual_qty), available
				)
			)
	for row in run.ingredients:
		event = append_stock_event(
			"Consumption",
			row.item_code,
			row.source_location or run.source_location,
			-flt(row.actual_qty),
			row.valuation_rate,
			run.doctype,
			run.name,
			row.name,
		)
		row.db_set("stock_event", event.name, update_modified=False)
	output_rate = flt(run.actual_material_cost) / flt(run.actual_output_qty) if run.actual_output_qty else 0
	return append_stock_event(
		"Production Output",
		run.finished_item,
		run.target_location,
		flt(run.actual_output_qty),
		output_rate,
		run.doctype,
		run.name,
	)


def record_production_event(run, output_stock_event, event_type="PRODUCTION_POSTED"):
	payload = {
		"production_run": run.name,
		"production_date": run.production_date,
		"recipe": run.recipe,
		"finished_item": run.finished_item,
		"planned_output_qty": flt(run.planned_output_qty),
		"actual_output_qty": flt(run.actual_output_qty),
		"expected_material_cost": flt(run.expected_material_cost),
		"actual_material_cost": flt(run.actual_material_cost),
		"output_stock_event": output_stock_event,
		"ingredients": [
			{
				"item_code": row.item_code,
				"expected_qty": flt(row.expected_qty),
				"actual_qty": flt(row.actual_qty),
				"uom": row.uom,
				"source_location": row.source_location,
				"stock_event": row.stock_event,
			}
			for row in run.ingredients
		],
	}
	return append_truth_event(event_type, run.doctype, run.name, payload)


# endregion CUSTOM STOCK POSTING
