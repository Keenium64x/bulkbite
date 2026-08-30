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
			"requires_active_worker": bool(task.get("requires_active_worker", True)),
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
	_apply_resource_constrained_cpm(by_id, worker_lanes, resource_duration, default_slack)
	ordered_tasks = sorted(by_id.values(), key=lambda task: (task["scheduled_start"], task["step_number"]))
	for task in ordered_tasks:
		for field in ("early_start", "early_finish", "late_start", "late_finish", "slack_minutes", "scheduled_start", "scheduled_end"):
			task[field] = round(task[field], 1)
	return {
		"tasks": ordered_tasks,
		"worker_lanes": worker_lanes,
		"logical_dependency_minutes": round(project_duration, 1),
		"critical_path_minutes": round(resource_duration, 1),
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
		ready.sort(
			key=lambda task: _resource_priority(
				task,
				workers,
				equipment_slots,
				completed_at,
				team_size,
			)
		)
		task = ready[0]
		worker_count = min(task["minimum_workers"], team_size) if task["requires_active_worker"] else 0
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
		task["equipment_slot"] = equipment_slot + 1 if equipment_slot is not None else None
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
	_attach_assist_opportunities(lanes, by_id, max(completed_at.values(), default=0.0))
	return by_id, lanes, max(completed_at.values(), default=0.0)


def _apply_resource_constrained_cpm(by_id, lanes, schedule_finish, default_slack):
	"""Calculate safe start windows from the actual worker and equipment sequence."""
	successors = defaultdict(set)
	for task in by_id.values():
		for dependency in task["depends_on_task_ids"]:
			successors[dependency].add(task["task_id"])
	for lane in lanes:
		primary = [row for row in lane["steps"] if row.get("kind") != "assist"]
		primary.sort(key=lambda row: (row["start_minute"], row["end_minute"], row["step_number"]))
		for current, following in zip(primary, primary[1:]):
			if current["task_id"] != following["task_id"]:
				successors[current["task_id"]].add(following["task_id"])
	equipment_lanes = defaultdict(list)
	for task in by_id.values():
		if task.get("equipment_type") and task.get("equipment_slot"):
			equipment_lanes[(task["equipment_type"], task["equipment_slot"])].append(task)
	for tasks in equipment_lanes.values():
		tasks.sort(key=lambda row: (row["scheduled_start"], row["scheduled_end"], row["step_number"]))
		for current, following in zip(tasks, tasks[1:]):
			if current["task_id"] != following["task_id"]:
				successors[current["task_id"]].add(following["task_id"])

	buffered_finish = schedule_finish + max(float(default_slack or 0), 0.0)
	for task in by_id.values():
		task["early_start"] = task["scheduled_start"]
		task["early_finish"] = task["scheduled_end"]
	for task in sorted(by_id.values(), key=lambda row: (row["scheduled_start"], row["scheduled_end"], row["step_number"]), reverse=True):
		task["late_finish"] = min((by_id[child]["late_start"] for child in successors[task["task_id"]]), default=buffered_finish)
		task["late_start"] = task["late_finish"] - task["duration_minutes"]
		task["slack_minutes"] = max(task["late_start"] - task["scheduled_start"], 0.0)
		task["is_critical"] = task["slack_minutes"] <= max(float(default_slack or 0), 0.0) + 0.001
	for lane in lanes:
		for row in lane["steps"]:
			task = by_id.get(row["task_id"])
			if task:
				row["is_critical"] = task["is_critical"]


def _resource_priority(task, workers, equipment_slots, completed_at, team_size):
	"""Keep a single worker in reviewed recipe order while retaining parallel CPM priority."""
	earliest_start = _earliest_resource_start(task, workers, equipment_slots, completed_at, team_size)
	if team_size == 1:
		return (task["step_number"], earliest_start)
	return (earliest_start, not task["is_critical"], task["step_number"])


def _attach_assist_opportunities(lanes, by_id, schedule_finish):
	"""Fill safe lane gaps with advisory help on overlapping parallel preparation."""
	for lane in lanes:
		primary_steps = sorted(lane["steps"], key=lambda row: (row["start_minute"], row["step_number"]))
		gaps = _lane_gaps(primary_steps, schedule_finish)
		assists = []
		for gap_start, gap_end, preceding_step in gaps:
			candidate = _best_assist_task(lane["lane"], gap_start, gap_end, by_id)
			if not candidate:
				continue
			assist_start = max(gap_start, candidate["scheduled_start"])
			assist_end = min(gap_end, candidate["scheduled_end"])
			assists.append({
				"kind": "assist",
				"task_id": candidate["task_id"],
				"step_number": candidate["step_number"],
				"step_name": candidate["step_name"],
				"start_minute": round(assist_start, 1),
				"end_minute": round(assist_end, 1),
				"duration_minutes": round(assist_end - assist_start, 1),
				"equipment_type": candidate["equipment_type"],
				"is_critical": candidate["is_critical"],
				"assisting_workers": candidate["assigned_workers"],
				"after_step_number": preceding_step,
			})
		lane["assist_steps"] = assists
		lane["steps"] = sorted(
			[*primary_steps, *assists],
			key=lambda row: (row["start_minute"], row.get("kind") == "assist", row["step_number"]),
		)


def _lane_gaps(steps, schedule_finish):
	gaps = []
	cursor = 0.0
	preceding_step = None
	for step in steps:
		if step["start_minute"] > cursor:
			gaps.append((cursor, step["start_minute"], preceding_step))
		cursor = max(cursor, step["end_minute"])
		preceding_step = step["step_number"]
	if schedule_finish > cursor:
		gaps.append((cursor, schedule_finish, preceding_step))
	return gaps


def _best_assist_task(lane_number, gap_start, gap_end, by_id):
	candidates = [
		task
		for task in by_id.values()
		if task.get("can_run_concurrently")
		and lane_number not in task.get("assigned_workers", [])
		and task.get("scheduled_start", 0) < gap_end
		and task.get("scheduled_end", 0) > gap_start
	]
	if not candidates:
		return None
	return min(
		candidates,
		key=lambda task: (
			not task["is_critical"],
			-max(0, min(gap_end, task["scheduled_end"]) - max(gap_start, task["scheduled_start"])),
			task["step_number"],
		),
	)


def _earliest_resource_start(task, workers, equipment_slots, completed_at, team_size):
	worker_count = min(task["minimum_workers"], team_size) if task["requires_active_worker"] else 0
	selected_workers = sorted(range(team_size), key=lambda index: workers[index])[:worker_count]
	dependency_ready = max((completed_at[parent] for parent in task["depends_on_task_ids"]), default=0.0)
	worker_ready = max((workers[index] for index in selected_workers), default=0.0)
	equipment_ready = min(equipment_slots.get(task["equipment_type"], [0.0])) if task["equipment_type"] else 0.0
	return max(dependency_ready, worker_ready, equipment_ready)


# endregion CRITICAL PATH AND RESOURCE SCHEDULE
