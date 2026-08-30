from __future__ import annotations

import math
import re

import frappe
from frappe import _
from frappe.utils import flt

from bulkbite.kitchen_instruction_ai import kitchen_ai_is_available, propose_kitchen_tasks
from bulkbite.kitchen_scheduler import KitchenScheduleError, calculate_kitchen_schedule, validate_task_graph
from bulkbite.stock_production import load_expected_usage, round_operational_quantity


# =============================================================================
# region DETERMINISTIC KITCHEN PLAN
# =============================================================================


def build_run_instruction_plan(recipe_name, output_qty, team_size=1):
	"""Scale recipe truth, validate a method graph, then schedule it deterministically."""
	recipe = frappe.get_doc("BulkBite Recipe", recipe_name)
	output_qty = round_operational_quantity(output_qty)
	if output_qty <= 0:
		frappe.throw(_("Instruction output must be greater than zero."))
	expectation = load_expected_usage(recipe.name, output_qty, "Ingredients")
	ingredients = [_build_ingredient_guidance(row) for row in expectation["ingredients"]]
	equipment = _equipment_position()
	workers = max(int(team_size or 1), 1)
	settings = _instruction_settings()
	steps, source, generation_warnings = _resolve_task_graph(recipe, output_qty, ingredients, equipment, workers, settings)
	schedule = calculate_kitchen_schedule(
		steps,
		workers,
		{key: max(int(row.get("quantity_available") or 1) * int(row.get("concurrent_batch_limit") or 1), 1) for key, row in equipment.items()},
		settings["kitchen_default_slack_minutes"],
	)
	steps = _attach_ingredient_truth(schedule["tasks"], ingredients)
	return {
		"recipe": recipe.name,
		"recipe_name": recipe.recipe_name,
		"output_qty": output_qty,
		"output_uom": recipe.output_uom,
		"team_size": workers,
		"ingredients": ingredients,
		"equipment": list(equipment.values()),
		"steps": steps,
		"worker_lanes": schedule["worker_lanes"],
		"estimated_elapsed_minutes": schedule["resource_constrained_minutes"],
		"critical_path_minutes": schedule["critical_path_minutes"],
		"default_slack_minutes": schedule["default_slack_minutes"],
		"instruction_source": source,
		"warnings": [*generation_warnings, *_instruction_warnings(recipe, steps, equipment)],
		"ai_available": kitchen_ai_is_available(),
	}


def _build_ingredient_guidance(row):
	"""Keep raw recipe weight authoritative and add deterministic kitchen estimates."""
	quantity = round_operational_quantity(row["expected_qty"])
	item = frappe.db.get_value(
		"BulkBite Item",
		row["item_code"],
		["prepared_yield_factor", "average_piece_weight_g", "piece_count_label", "preparation_yield_note"],
		as_dict=True,
	) or {}
	yield_factor = flt(item.get("prepared_yield_factor")) or 1
	prepared_quantity = round_operational_quantity(quantity * yield_factor)
	piece_count = None
	if row["uom"] == "Kg" and flt(item.get("average_piece_weight_g")) > 0:
		piece_count = max(round(quantity * 1000 / flt(item.get("average_piece_weight_g"))), 1)
	return {
		"item_code": row["item_code"],
		"item_name": row["item_name"],
		"quantity": quantity,
		"uom": row["uom"],
		"quantity_basis": "Raw purchase quantity",
		"prepared_yield_factor": round(yield_factor, 3),
		"prepared_quantity": prepared_quantity,
		"piece_count_estimate": piece_count,
		"piece_count_label": item.get("piece_count_label") or _default_piece_label(row["item_name"]),
		"preparation_yield_note": item.get("preparation_yield_note"),
	}


def _default_piece_label(item_name):
	label = str(item_name or "pieces").strip().lower()
	return label if label.endswith("s") else f"{label}s"


def _resolve_task_graph(recipe, output_qty, ingredients, equipment, team_size, settings):
	warnings = []
	if settings["use_ai_kitchen_instructions"] and kitchen_ai_is_available():
		try:
			proposal = propose_kitchen_tasks(
				{"recipe": recipe.name, "recipe_name": recipe.recipe_name, "guidance": recipe.instruction_guidance, "output_qty": output_qty, "output_uom": recipe.output_uom},
			ingredients,
			list(equipment.values()),
			team_size,
			)
			if proposal and proposal.tasks:
				return validate_task_graph(
					[row.model_dump() for row in proposal.tasks],
					[row["item_code"] for row in ingredients],
					equipment.keys(),
				), "AI generated and deterministically scheduled", warnings
		except (KitchenScheduleError, RuntimeError, ValueError) as exc:
			warnings.append(_("AI could not produce a safe task graph, so the reviewed recipe method is shown instead: {0}").format(str(exc)))
	fallback = _build_reviewed_tasks(recipe, output_qty, ingredients, equipment)
	return validate_task_graph(fallback, [row["item_code"] for row in ingredients], equipment.keys()), "Reviewed recipe fallback", warnings


def _build_reviewed_tasks(recipe, output_qty, ingredients, equipment):
	ingredient_by_code = {row["item_code"]: row for row in ingredients}
	steps = []
	for raw in sorted(recipe.instruction_steps or [], key=lambda row: int(row.step_number or 0)):
		items = [ingredient_by_code[code] for code in _csv(raw.ingredient_items) if code in ingredient_by_code]
		equipment_row = equipment.get(raw.equipment_type) or {}
		batch_capacity = flt(equipment_row.get("total_concurrent_capacity"))
		batch_basis = sum(flt(item["quantity"]) for item in items) or output_qty
		batches = max(math.ceil(batch_basis / batch_capacity), 1) if batch_capacity > 0 else 1
		duration = flt(raw.duration_minutes) + flt(raw.duration_per_kg_minutes) * output_qty
		step_number = int(raw.step_number)
		steps.append({
			"task_id": str(step_number), "title": raw.step_name, "objective": raw.instruction,
			"ingredient_item_codes": [item["item_code"] for item in items], "equipment_type": raw.equipment_type,
			"depends_on_task_ids": [str(number) for number in _step_numbers(raw.depends_on_steps)],
			"can_run_concurrently": bool(raw.can_run_concurrently),
			"requires_active_worker": bool(getattr(raw, "requires_active_worker", True)),
			"minimum_workers": max(int(raw.minimum_workers or 1), 1),
			"worker_role": raw.worker_role, "quality_checkpoint": raw.quality_checkpoint,
			"batch_count": batches, "duration_minutes": round(max(duration, 1) * batches, 1),
			"substeps": _fallback_substeps(raw.instruction, raw.quality_checkpoint),
		})
	return steps


def _fallback_substeps(instruction, quality_checkpoint):
	parts = [part.strip() for part in re.split(r"(?:\n+|(?<=[.!?])\s+)", str(instruction or "")) if part.strip()]
	return [{"order": index, "instruction": part, "check": quality_checkpoint if index == len(parts) else ""} for index, part in enumerate(parts, start=1)]


def _attach_ingredient_truth(steps, ingredients):
	by_code = {row["item_code"]: row for row in ingredients}
	for step in steps:
		step["ingredients"] = [by_code[code] for code in step["ingredient_item_codes"] if code in by_code]
		step["depends_on_steps"] = [next((row["step_number"] for row in steps if row["task_id"] == task_id), task_id) for task_id in step["depends_on_task_ids"]]
		step["batch_count"] = int(step.get("batch_count") or 1)
	return steps


def _instruction_settings():
	try:
		settings = frappe.get_single("BulkBite Settings")
		return {
			"kitchen_default_slack_minutes": max(flt(settings.kitchen_default_slack_minutes), 0),
			"use_ai_kitchen_instructions": bool(settings.use_ai_kitchen_instructions),
		}
	except Exception:
		return {"kitchen_default_slack_minutes": 10, "use_ai_kitchen_instructions": True}


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
		warnings.append(_("This recipe has no reviewed fallback method. AI instructions will be unavailable if generation fails."))
	for step in steps:
		if step["equipment_type"] and step["equipment_type"] not in equipment:
			warnings.append(_("Step {0} needs {1}, but no enabled equipment is configured.").format(step["step_number"], step["equipment_type"]))
	return warnings


def _csv(value):
	return [part.strip() for part in re.split(r"[,\n]", str(value or "")) if part.strip()]


def _step_numbers(value):
	return [int(part) for part in _csv(value) if part.isdigit()]


# endregion DETERMINISTIC KITCHEN PLAN
