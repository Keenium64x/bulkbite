from __future__ import annotations

import math
import re

import frappe
from frappe import _
from frappe.utils import flt

from bulkbite.stock_production import load_expected_usage, round_operational_quantity


# =============================================================================
# region DETERMINISTIC KITCHEN PLAN
# =============================================================================


def build_run_instruction_plan(recipe_name, output_qty, team_size=1):
	"""Scale recipe truth and schedule its reviewed instruction graph into worker lanes."""
	recipe = frappe.get_doc("BulkBite Recipe", recipe_name)
	output_qty = round_operational_quantity(output_qty)
	if output_qty <= 0:
		frappe.throw(_("Instruction output must be greater than zero."))
	expectation = load_expected_usage(recipe.name, output_qty, "Ingredients")
	ingredients = [
		{"item_code": row["item_code"], "item_name": row["item_name"], "quantity": round_operational_quantity(row["expected_qty"]), "uom": row["uom"]}
		for row in expectation["ingredients"]
	]
	equipment = _equipment_position()
	steps = _build_steps(recipe, output_qty, ingredients, equipment)
	lanes, elapsed = _assign_worker_lanes(steps, max(int(team_size or 1), 1))
	return {
		"recipe": recipe.name,
		"recipe_name": recipe.recipe_name,
		"output_qty": output_qty,
		"output_uom": recipe.output_uom,
		"team_size": max(int(team_size or 1), 1),
		"ingredients": ingredients,
		"equipment": list(equipment.values()),
		"steps": steps,
		"worker_lanes": lanes,
		"estimated_elapsed_minutes": round(elapsed, 1),
		"warnings": _instruction_warnings(recipe, steps, equipment),
		"ai_available": bool(frappe.conf.get("gemini_api_key") and frappe.conf.get("gemini_private_receipt_approved")),
	}


def _build_steps(recipe, output_qty, ingredients, equipment):
	ingredient_by_code = {row["item_code"]: row for row in ingredients}
	steps = []
	for raw in sorted(recipe.instruction_steps or [], key=lambda row: int(row.step_number or 0)):
		items = [ingredient_by_code[code] for code in _csv(raw.ingredient_items) if code in ingredient_by_code]
		equipment_row = equipment.get(raw.equipment_type) or {}
		batch_capacity = flt(equipment_row.get("total_concurrent_capacity"))
		batch_basis = sum(flt(item["quantity"]) for item in items) or output_qty
		batches = max(math.ceil(batch_basis / batch_capacity), 1) if batch_capacity > 0 else 1
		duration = flt(raw.duration_minutes) + flt(raw.duration_per_kg_minutes) * output_qty
		steps.append({
			"step_number": int(raw.step_number), "step_name": raw.step_name, "instruction": raw.instruction,
			"ingredients": items, "equipment_type": raw.equipment_type, "depends_on_steps": _step_numbers(raw.depends_on_steps),
			"can_run_concurrently": bool(raw.can_run_concurrently), "minimum_workers": max(int(raw.minimum_workers or 1), 1),
			"worker_role": raw.worker_role, "quality_checkpoint": raw.quality_checkpoint,
			"batch_count": batches, "estimated_minutes": round(max(duration, 1) * batches, 1),
		})
	return steps


def _assign_worker_lanes(steps, team_size):
	"""Place dependency-ready work on the earliest available worker lane."""
	lanes = [{"lane": index + 1, "available_at": 0.0, "steps": []} for index in range(team_size)]
	finished_at = {}
	for step in steps:
		dependency_ready = max((finished_at.get(number, 0) for number in step["depends_on_steps"]), default=0)
		workers = min(step["minimum_workers"], team_size)
		selected = sorted(lanes, key=lambda row: row["available_at"])[:workers]
		resource_ready = max((row["available_at"] for row in selected), default=0)
		if not step["can_run_concurrently"]:
			resource_ready = max((row["available_at"] for row in lanes), default=0)
		start = max(dependency_ready, resource_ready)
		end = start + step["estimated_minutes"]
		for lane in selected:
			lane["steps"].append({"step_number": step["step_number"], "step_name": step["step_name"], "start_minute": round(start, 1), "end_minute": round(end, 1)})
			lane["available_at"] = end
		finished_at[step["step_number"]] = end
	return lanes, max(finished_at.values(), default=0)


def _equipment_position():
	rows = frappe.get_all("BulkBite Equipment Type", filters={"enabled": 1}, fields=["name", "equipment_type_name", "capacity_qty", "capacity_uom", "quantity_available", "concurrent_batch_limit"], order_by="equipment_type_name")
	return {
		row.name: {
			**row, "total_concurrent_capacity": round_operational_quantity(flt(row.capacity_qty) * int(row.quantity_available or 0) * int(row.concurrent_batch_limit or 1))
		}
		for row in rows
	}


def _instruction_warnings(recipe, steps, equipment):
	warnings = []
	if not recipe.instruction_steps:
		warnings.append(_("This recipe has no operational instruction steps yet. Add reviewed steps before using it on the kitchen floor."))
	for step in steps:
		if step["equipment_type"] and step["equipment_type"] not in equipment:
			warnings.append(_("Step {0} needs {1}, but no enabled equipment is configured.").format(step["step_number"], step["equipment_type"]))
	return warnings


def _csv(value):
	return [part.strip() for part in re.split(r"[,\n]", str(value or "")) if part.strip()]


def _step_numbers(value):
	return [int(part) for part in _csv(value) if part.isdigit()]


# endregion DETERMINISTIC KITCHEN PLAN
