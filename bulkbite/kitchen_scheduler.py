from __future__ import annotations

from collections import defaultdict
import re


# =============================================================================
# region KITCHEN TASK GRAPH VALIDATION
# =============================================================================


class KitchenScheduleError(ValueError):
	pass


def validate_task_graph(tasks, ingredient_codes=None, equipment_codes=None):
	"""Return a normalized acyclic task graph using only supplied kitchen truth."""
	ingredient_codes = set(ingredient_codes or [])
	equipment_codes = set(equipment_codes or [])
	normalized = []
	seen = set()
	for position, raw in enumerate(tasks or [], start=1):
		task = dict(raw)
		task_id = str(task.get("task_id") or position).strip()
		if not task_id or task_id in seen:
			raise KitchenScheduleError("Kitchen task IDs must be unique and non-empty.")
		seen.add(task_id)
		ingredients = [str(value).strip() for value in task.get("ingredient_item_codes") or [] if str(value).strip()]
		unknown_ingredients = set(ingredients) - ingredient_codes
		if unknown_ingredients:
			raise KitchenScheduleError(f"Task {task_id} uses unknown ingredients: {', '.join(sorted(unknown_ingredients))}.")
		equipment = str(task.get("equipment_type") or "").strip() or None
		if equipment and equipment not in equipment_codes:
			raise KitchenScheduleError(f"Task {task_id} uses unknown equipment: {equipment}.")
		duration = float(task.get("duration_minutes") or 0)
		if duration <= 0:
			raise KitchenScheduleError(f"Task {task_id} must have a positive duration.")
		normalized.append({
			**task,
			"task_id": task_id,
			"step_number": position,
			"step_name": str(task.get("title") or task.get("step_name") or f"Task {position}").strip(),
			"title": str(task.get("title") or task.get("step_name") or f"Task {position}").strip(),
			"objective": str(task.get("objective") or task.get("instruction") or "").strip(),
			"instruction": str(task.get("instruction") or task.get("objective") or "").strip(),
			"ingredient_item_codes": ingredients,
			"equipment_type": equipment,
			"depends_on_task_ids": [str(value).strip() for value in task.get("depends_on_task_ids") or [] if str(value).strip()],
			"duration_minutes": round(duration, 1),
			"estimated_minutes": round(duration, 1),
			"minimum_workers": max(int(task.get("minimum_workers") or 1), 1),
			"substeps": _normalize_substeps(task.get("substeps")),
		})
		_reject_untrusted_quantity_text(normalized[-1])
	for task in normalized:
		unknown = set(task["depends_on_task_ids"]) - seen
		if unknown:
			raise KitchenScheduleError(f"Task {task['task_id']} has unknown dependencies: {', '.join(sorted(unknown))}.")
		if task["task_id"] in task["depends_on_task_ids"]:
			raise KitchenScheduleError(f"Task {task['task_id']} cannot depend on itself.")
	_topological_order(normalized)
	return normalized


def _reject_untrusted_quantity_text(task):
	"""Keep all ingredient quantities outside AI-authored prose."""
	text = " ".join([
		str(task.get("objective") or ""),
		str(task.get("instruction") or ""),
		*[str(row.get("instruction") or "") for row in task.get("substeps") or []],
	])
	if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|litre|litres|liter|liters|each)\b", text, re.IGNORECASE):
		raise KitchenScheduleError(f"Task {task['task_id']} repeats an ingredient quantity in generated prose. Quantities must come from recipe truth.")


def _normalize_substeps(substeps):
	rows = []
	for position, raw in enumerate(substeps or [], start=1):
		if isinstance(raw, str):
			rows.append({"order": position, "instruction": raw.strip(), "check": ""})
			continue
		rows.append({
			"order": position,
			"instruction": str(raw.get("instruction") or "").strip(),
			"check": str(raw.get("check") or "").strip(),
		})
	return [row for row in rows if row["instruction"]]


def _topological_order(tasks):
	by_id = {task["task_id"]: task for task in tasks}
	remaining = {task_id: set(task["depends_on_task_ids"]) for task_id, task in by_id.items()}
	order = []
	while remaining:
		ready = sorted(task_id for task_id, dependencies in remaining.items() if not dependencies)
		if not ready:
			raise KitchenScheduleError("Kitchen tasks contain a dependency cycle.")
		for task_id in ready:
			order.append(task_id)
			remaining.pop(task_id)
		for dependencies in remaining.values():
			dependencies.difference_update(ready)
	return order


# endregion KITCHEN TASK GRAPH VALIDATION


# =============================================================================
# region CRITICAL PATH AND RESOURCE SCHEDULE
# =============================================================================


def calculate_kitchen_schedule(tasks, team_size, equipment_capacity=None, default_slack_minutes=0):
	"""Calculate CPM values, then assign dependency-ready tasks to workers and equipment."""
	team_size = max(int(team_size or 1), 1)
	equipment_capacity = {key: max(int(value or 1), 1) for key, value in (equipment_capacity or {}).items()}
	by_id = {task["task_id"]: dict(task) for task in tasks}
	order = _topological_order(tasks)
	successors = defaultdict(list)
	for task in tasks:
		for dependency in task["depends_on_task_ids"]:
			successors[dependency].append(task["task_id"])

	for task_id in order:
		task = by_id[task_id]
		task["early_start"] = max((by_id[parent]["early_finish"] for parent in task["depends_on_task_ids"]), default=0.0)
		task["early_finish"] = task["early_start"] + task["duration_minutes"]
	project_duration = max((task["early_finish"] for task in by_id.values()), default=0.0)
	default_slack = max(float(default_slack_minutes or 0), 0.0)
	buffered_finish = project_duration + default_slack
	for task_id in reversed(order):
		task = by_id[task_id]
		task["late_finish"] = min((by_id[child]["late_start"] for child in successors[task_id]), default=buffered_finish)
		task["late_start"] = task["late_finish"] - task["duration_minutes"]
		task["slack_minutes"] = max(task["late_start"] - task["early_start"], 0.0)
		task["is_critical"] = task["slack_minutes"] <= default_slack + 0.001

	_scheduled, worker_lanes, resource_duration = _assign_resources(by_id, order, successors, team_size, equipment_capacity)
	ordered_tasks = sorted(by_id.values(), key=lambda task: (task["scheduled_start"], task["step_number"]))
	for task in ordered_tasks:
		for field in ("early_start", "early_finish", "late_start", "late_finish", "slack_minutes", "scheduled_start", "scheduled_end"):
			task[field] = round(task[field], 1)
	return {
		"tasks": ordered_tasks,
		"worker_lanes": worker_lanes,
		"critical_path_minutes": round(project_duration, 1),
		"resource_constrained_minutes": round(resource_duration, 1),
		"default_slack_minutes": round(max(float(default_slack_minutes or 0), 0.0), 1),
	}


def _assign_resources(by_id, order, successors, team_size, equipment_capacity):
	workers = [0.0] * team_size
	equipment_slots = {key: [0.0] * capacity for key, capacity in equipment_capacity.items()}
	unscheduled = set(order)
	completed_at = {}
	lanes = [{"lane": index + 1, "available_at": 0.0, "steps": []} for index in range(team_size)]
	while unscheduled:
		ready = [by_id[task_id] for task_id in unscheduled if all(parent in completed_at for parent in by_id[task_id]["depends_on_task_ids"])]
		if not ready:
			raise KitchenScheduleError("No dependency-ready kitchen task could be scheduled.")
		ready.sort(key=lambda task: (_earliest_resource_start(task, workers, equipment_slots, completed_at, team_size), not task["is_critical"], task["step_number"]))
		task = ready[0]
		worker_count = min(task["minimum_workers"], team_size)
		selected_workers = sorted(range(team_size), key=lambda index: workers[index])[:worker_count]
		dependency_ready = max((completed_at[parent] for parent in task["depends_on_task_ids"]), default=0.0)
		worker_ready = max((workers[index] for index in selected_workers), default=0.0)
		equipment_slot = None
		equipment_ready = 0.0
		if task["equipment_type"]:
			slots = equipment_slots.setdefault(task["equipment_type"], [0.0])
			equipment_slot = min(range(len(slots)), key=lambda index: slots[index])
			equipment_ready = slots[equipment_slot]
		start = max(dependency_ready, worker_ready, equipment_ready)
		end = start + task["duration_minutes"]
		task["scheduled_start"] = start
		task["scheduled_end"] = end
		task["assigned_workers"] = sorted(index + 1 for index in selected_workers)
		for index in selected_workers:
			workers[index] = end
			lanes[index]["available_at"] = end
			lanes[index]["steps"].append({
				"task_id": task["task_id"],
				"step_number": task["step_number"],
				"step_name": task["step_name"],
				"start_minute": round(start, 1),
				"end_minute": round(end, 1),
				"duration_minutes": task["duration_minutes"],
				"equipment_type": task["equipment_type"],
				"is_critical": task["is_critical"],
			})
		if equipment_slot is not None:
			equipment_slots[task["equipment_type"]][equipment_slot] = end
		completed_at[task["task_id"]] = end
		unscheduled.remove(task["task_id"])
	return by_id, lanes, max(completed_at.values(), default=0.0)


def _earliest_resource_start(task, workers, equipment_slots, completed_at, team_size):
	worker_count = min(task["minimum_workers"], team_size)
	selected_workers = sorted(range(team_size), key=lambda index: workers[index])[:worker_count]
	dependency_ready = max((completed_at[parent] for parent in task["depends_on_task_ids"]), default=0.0)
	worker_ready = max((workers[index] for index in selected_workers), default=0.0)
	equipment_ready = min(equipment_slots.get(task["equipment_type"], [0.0])) if task["equipment_type"] else 0.0
	return max(dependency_ready, worker_ready, equipment_ready)


# endregion CRITICAL PATH AND RESOURCE SCHEDULE
