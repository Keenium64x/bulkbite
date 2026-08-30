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
	steps = _expand_equipment_batches(steps, ingredients, equipment)
	schedule = calculate_kitchen_schedule(
		steps,
		workers,
		{key: max(int(row.get("quantity_available") or 1) * int(row.get("concurrent_batch_limit") or 1), 1) for key, row in equipment.items()},
		settings["kitchen_default_slack_minutes"],
	)
	steps = _attach_ingredient_truth(schedule["tasks"], ingredients)
	for step in steps:
		step["equipment_name"] = (equipment.get(step.get("equipment_type")) or {}).get("equipment_type_name")
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
				_recent_timing_evidence(recipe.name),
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
		duration = flt(raw.duration_minutes) + flt(raw.duration_per_kg_minutes) * output_qty
		step_number = int(raw.step_number)
		steps.append({
			"task_id": str(step_number), "title": raw.step_name, "objective": raw.instruction,
			"recipe_step_number": step_number,
			"ingredient_item_codes": [item["item_code"] for item in items], "equipment_type": raw.equipment_type,
			"depends_on_task_ids": [str(number) for number in _step_numbers(raw.depends_on_steps)],
			"can_run_concurrently": bool(raw.can_run_concurrently),
			"requires_active_worker": bool(getattr(raw, "requires_active_worker", True)),
			"minimum_workers": max(int(raw.minimum_workers or 1), 1),
			"worker_role": raw.worker_role, "quality_checkpoint": raw.quality_checkpoint,
			"duration_minutes": round(max(duration, 1), 1),
			"substeps": _fallback_substeps(raw.instruction, raw.quality_checkpoint),
		})
	return steps


def _expand_equipment_batches(tasks, ingredients, equipment):
	"""Turn equipment pressure into schedulable batch nodes instead of a label."""
	ingredient_by_code = {row["item_code"]: row for row in ingredients}
	expanded_ids = {}
	batch_specs = {}
	for task in tasks:
		equipment_row = equipment.get(task.get("equipment_type")) or {}
		capacity = flt(equipment_row.get("capacity_qty"))
		load_rows = [
			ingredient_by_code[code]
			for code in task.get("ingredient_item_codes") or []
			if code in ingredient_by_code and flt(ingredient_by_code[code].get("prepared_quantity")) > 0
		]
		prepared_load = sum(flt(row.get("prepared_quantity")) for row in load_rows)
		load_uom = _single_load_uom(task, load_rows)
		capacity_uom = _normalized_capacity_uom(equipment_row.get("capacity_uom"))
		if capacity > 0 and prepared_load > 0 and load_uom != capacity_uom:
			raise KitchenScheduleError(
				_("{0} measures batch capacity in {1}, but {2} is loaded in {3}. Configure a usable {3} capacity for this equipment and food before building the cooking plan.").format(
					equipment_row.get("equipment_type_name") or task.get("equipment_type"),
					equipment_row.get("capacity_uom") or _("an unspecified unit"),
					task.get("step_name") or task.get("title"),
					load_rows[0].get("uom"),
				)
			)
		batch_count = max(math.ceil(prepared_load / capacity), 1) if capacity > 0 and prepared_load > 0 else 1
		expanded_ids[task["task_id"]] = [
			task["task_id"] if batch_count == 1 else f"{task['task_id']}::batch-{index}"
			for index in range(1, batch_count + 1)
		]
		batch_specs[task["task_id"]] = (batch_count, prepared_load, capacity, equipment_row)

	expanded = []
	task_by_id = {task["task_id"]: task for task in tasks}
	for task in tasks:
		batch_count, prepared_load, capacity, equipment_row = batch_specs[task["task_id"]]
		for batch_index, task_id in enumerate(expanded_ids[task["task_id"]], start=1):
			dependency_ids = _batch_dependency_ids(
				task,
				batch_index,
				batch_count,
				task_by_id,
				expanded_ids,
			)
			batch_load = min(capacity, max(prepared_load - capacity * (batch_index - 1), 0)) if capacity > 0 else prepared_load
			expanded.append({
				**task,
				"task_id": task_id,
				"source_task_id": task["task_id"],
				"title": task["title"] if batch_count == 1 else _("{0}, batch {1} of {2}").format(task["title"], batch_index, batch_count),
				"step_name": task["step_name"] if batch_count == 1 else _("{0}, batch {1} of {2}").format(task["step_name"], batch_index, batch_count),
				"depends_on_task_ids": dependency_ids,
				"batch_count": batch_count,
				"batch_index": batch_index,
				"prepared_load_qty": round_operational_quantity(prepared_load),
				"batch_load_qty": round_operational_quantity(batch_load),
				"batch_capacity_qty": round_operational_quantity(capacity),
				"batch_capacity_uom": equipment_row.get("capacity_uom"),
			})
	return validate_task_graph(
		expanded,
		ingredient_by_code.keys(),
		equipment.keys(),
	)


def _single_load_uom(task, load_rows):
	"""Return one comparable load unit, refusing mixed physical measures."""
	units = {_normalized_capacity_uom(row.get("uom")) for row in load_rows}
	if len(units) > 1:
		raise KitchenScheduleError(
			_("{0} combines ingredients measured in incompatible units. Split it into unit-specific equipment tasks before calculating batches.").format(
				task.get("step_name") or task.get("title")
			)
		)
	return next(iter(units), "")


def _normalized_capacity_uom(value):
	return {
		"kg": "kg",
		"kilogram": "kg",
		"kilograms": "kg",
		"l": "litre",
		"litre": "litre",
		"litres": "litre",
		"liter": "litre",
		"liters": "litre",
		"each": "each",
	}.get(str(value or "").strip().lower(), str(value or "").strip().lower())


def _batch_dependency_ids(task, batch_index, batch_count, task_by_id, expanded_ids):
	dependencies = []
	current_ingredients = set(task.get("ingredient_item_codes") or [])
	for dependency in task.get("depends_on_task_ids") or []:
		dependency_ids = expanded_ids[dependency]
		dependency_task = task_by_id[dependency]
		matching_pipeline = (
			batch_count > 1
			and len(dependency_ids) == batch_count
			and bool(current_ingredients.intersection(dependency_task.get("ingredient_item_codes") or []))
		)
		dependencies.extend([dependency_ids[batch_index - 1]] if matching_pipeline else dependency_ids)
	return dependencies


def _recent_timing_evidence(recipe_name, limit=8):
	"""Return read-only timing evidence so AI estimates can reference actual runs."""
	try:
		rows = frappe.get_all(
			"BulkBite Production Run",
			filters={"recipe": recipe_name, "docstatus": 1, "actual_elapsed_hours": (">", 0)},
			fields=["name", "production_date", "actual_output_qty", "actual_elapsed_hours", "actual_team_size"],
			order_by="production_date desc, modified desc",
			limit=limit,
		)
		return [
			{
				"run": row.name,
				"production_date": row.production_date,
				"output_qty": round_operational_quantity(row.actual_output_qty),
				"elapsed_minutes": round(flt(row.actual_elapsed_hours) * 60, 1),
				"team_size": int(row.actual_team_size or 0),
			}
			for row in rows
		]
	except Exception:
		return []


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
		elif step.get("equipment_type") and not flt((equipment.get(step["equipment_type"]) or {}).get("capacity_qty")):
			warnings.append(_("{0} has no usable batch capacity, so {1} cannot be split into equipment batches.").format(step["equipment_type"], step["step_name"]))
	return warnings


def _csv(value):
	return [part.strip() for part in re.split(r"[,\n]", str(value or "")) if part.strip()]


def _step_numbers(value):
	return [int(part) for part in _csv(value) if part.isdigit()]


# endregion DETERMINISTIC KITCHEN PLAN
