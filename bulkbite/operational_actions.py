from __future__ import annotations

import calendar
from datetime import timedelta

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate


# =============================================================================
# region OPERATIONAL SCHEDULE MATERIALIZATION
# =============================================================================


def materialize_operational_actions(schedule_name=None, from_date=None, to_date=None):
	"""Create dated action occurrences from enabled schedule definitions, idempotently."""
	start = getdate(from_date or add_days(nowdate(), -31))
	end = getdate(to_date or add_days(nowdate(), 90))
	filters = {"enabled": 1}
	if schedule_name:
		filters["name"] = schedule_name
	created = []
	for schedule in frappe.get_all(
		"BulkBite Operational Schedule",
		filters=filters,
		fields=["*"],
	):
		for due_date in _schedule_dates(schedule, start, end):
			if frappe.db.exists("BulkBite Operational Action", {"schedule": schedule.name, "due_date": due_date}):
				continue
			doc = frappe.get_doc({
				"doctype": "BulkBite Operational Action",
				"title": schedule.schedule_name,
				"action_type": schedule.action_type,
				"schedule": schedule.name,
				"due_date": due_date,
				"status": "Due",
				"target_section": schedule.default_section or "operations",
				"consequence_note": schedule.notes,
			}).insert(ignore_permissions=True)
			created.append(doc.name)
	return created


def _schedule_dates(schedule, start, end):
	anchor = max(getdate(schedule.start_date), start)
	interval = max(int(schedule.interval or 1), 1)
	if schedule.recurrence == "Weekly":
		target_weekday = list(calendar.day_name).index(schedule.day_of_week)
		cursor = anchor + timedelta(days=(target_weekday - anchor.weekday()) % 7)
		while cursor <= end:
			yield cursor
			cursor += timedelta(days=7 * interval)
		return
	if schedule.recurrence == "Custom Days":
		cursor = getdate(schedule.start_date)
		while cursor < anchor:
			cursor += timedelta(days=interval)
		while cursor <= end:
			yield cursor
			cursor += timedelta(days=interval)
		return
	month_step = interval * (3 if schedule.recurrence == "Quarterly" else 12 if schedule.recurrence == "Annual" else 1)
	cursor = getdate(schedule.start_date)
	if schedule.recurrence == "Annual" and int(schedule.month_of_year or 0):
		cursor = cursor.replace(month=max(1, min(int(schedule.month_of_year), 12)), day=1)
	while cursor.replace(day=1) < anchor.replace(day=1):
		cursor = getdate(add_months(cursor, month_step))
	while cursor <= end:
		last_day = calendar.monthrange(cursor.year, cursor.month)[1]
		due = cursor.replace(day=min(max(int(schedule.day_of_month or 1), 1), last_day))
		if start <= due <= end and due >= getdate(schedule.start_date):
			yield due
		cursor = getdate(add_months(cursor.replace(day=1), month_step))


# endregion OPERATIONAL SCHEDULE MATERIALIZATION


# =============================================================================
# region CALENDAR AND CONTAINER POSITION
# =============================================================================


def get_operational_calendar_snapshot(from_date=None, to_date=None):
	start = getdate(from_date or add_days(nowdate(), -30))
	end = getdate(to_date or add_days(nowdate(), 90))
	rows = frappe.get_all(
		"BulkBite Operational Action",
		filters={"due_date": ["between", [start, end]]},
		fields=["name", "title", "action_type", "schedule", "due_date", "status", "completed_on", "rescheduled_to", "cancellation_reason", "target_section", "reference_doctype", "reference_name", "consequence_note", "notes"],
		order_by="due_date asc, creation asc",
	)
	today = getdate(nowdate())
	for row in rows:
		row["display_status"] = "Missed" if row.status == "Due" and getdate(row.due_date) < today else row.status
	return {
		"from_date": start,
		"to_date": end,
		"actions": rows,
		"counts": {
			"missed": sum(row.display_status == "Missed" for row in rows),
			"due": sum(row.display_status == "Due" for row in rows),
			"completed": sum(row.display_status == "Completed" for row in rows),
			"rescheduled": sum(row.display_status == "Rescheduled" for row in rows),
		},
	}


def get_container_position_snapshot(as_of_date=None):
	today = getdate(as_of_date or nowdate())
	states = {state: 0 for state in ["Clean", "Filled", "With Customer", "Maintenance", "Lost", "Retired"]}
	assets = frappe.get_all(
		"BulkBite Container Asset",
		fields=["name", "asset_code", "container_type", "lifecycle_state", "current_customer_reference", "expected_return_date", "last_movement", "replacement_cost", "enabled"],
		order_by="asset_code asc",
	)
	for asset in assets:
		states[asset.lifecycle_state] = states.get(asset.lifecycle_state, 0) + 1
		asset["overdue"] = bool(asset.lifecycle_state == "With Customer" and asset.expected_return_date and getdate(asset.expected_return_date) < today)
	types = frappe.get_all(
		"BulkBite Container Type",
		filters={"enabled": 1},
		fields=["name", "container_type_name", "capacity_qty", "capacity_uom", "replacement_price", "non_return_charge_multiplier", "expected_return_days", "default_for_production"],
		order_by="default_for_production desc, container_type_name asc",
	)
	pending_charges = sum(
		flt(value) for value in frappe.get_all(
			"BulkBite Container Movement",
			filters={"docstatus": 1, "movement_type": "Marked Lost"},
			pluck="replacement_charge",
		)
	)
	return {
		"states": states,
		"tracked": len(assets),
		"overdue": sum(bool(asset.overdue) for asset in assets),
		"pending_replacement_charges": round(pending_charges, 2),
		"types": types,
		"assets": assets,
	}


# endregion CALENDAR AND CONTAINER POSITION


# =============================================================================
# region NEXT ACTION ENGINE
# =============================================================================


def build_operational_action_snapshot(plan_snapshot=None):
	"""Choose the single next operational action and retain the supporting queue."""
	calendar_snapshot = get_operational_calendar_snapshot()
	container_position = get_container_position_snapshot()
	actions = []
	for action in calendar_snapshot["actions"]:
		if action.display_status not in {"Missed", "Due"}:
			continue
		severity = "overdue" if action.display_status == "Missed" else "attention"
		actions.append({
			"priority": 10 if severity == "overdue" else 50,
			"severity": severity,
			"title": action.title,
			"reason": action.consequence_note or f"{action.action_type} is {action.display_status.lower()}.",
			"due_date": action.due_date,
			"action_section": action.target_section or "operations",
			"action_label": "Review calendar",
			"recovery_steps": ["Review what was missed.", "Complete it now, reschedule it, or record why it was cancelled."],
		})
	buying = (plan_snapshot or {}).get("buying") or {}
	shortages = [row for row in buying.get("lines") or [] if flt(row.get("shortage_qty")) > 0]
	for supplier in buying.get("suppliers") or []:
		if not any(row.get("supplier") == supplier.get("supplier") for row in shortages):
			continue
		overdue = supplier.get("order_by_date") and getdate(supplier["order_by_date"]) < getdate(nowdate())
		actions.append({
			"priority": 15 if overdue else 30,
			"severity": "overdue" if overdue else "attention",
			"title": f"Order from {supplier.get('supplier')}",
			"reason": f"Ingredients are short for the production planned on {supplier.get('production_date')}. Order by {supplier.get('order_by_date')}.",
			"due_date": supplier.get("order_by_date"),
			"action_section": "buying",
			"action_label": "Open buying",
			"recovery_steps": ["Check available supplier stock and delivery timing.", "If the deadline has passed, move the run or source the shortage locally."],
		})
	next_station = (plan_snapshot or {}).get("next_production") or {}
	next_row = next_station.get("row") or {}
	if next_row and flt(next_row.get("remaining_output_qty") or next_row.get("planned_output_qty")) > 0:
		remaining = flt(next_row.get("remaining_output_qty") or next_row.get("planned_output_qty"))
		actions.append({
			"priority": 40,
			"severity": "attention",
			"title": "Complete the next production run",
			"reason": f"{round(remaining, 1)} kg is still needed for the current meal target.",
			"due_date": next_row.get("planned_date"),
			"action_section": "production",
			"action_label": "Open production",
			"recovery_steps": ["Confirm ingredient readiness.", "Record another run for the remaining food."],
		})
	if container_position["overdue"]:
		actions.append({
			"priority": 20,
			"severity": "attention",
			"title": "Recover overdue containers",
			"reason": f"{container_position['overdue']} customer containers are past their expected return date.",
			"due_date": None,
			"action_section": "stock",
			"action_label": "Open container control",
			"recovery_steps": ["Contact the listed customers.", "Record returns or mark unreturned containers lost so the replacement charge is visible."],
		})
	actions.sort(key=lambda row: (row["priority"], str(row.get("due_date") or "9999-12-31")))
	primary = actions[0] if actions else {
		"priority": 100,
		"severity": "ready",
		"title": "Operations are on track",
		"reason": "There is no overdue duty, buying deadline, production shortfall, or container exception requiring action.",
		"due_date": None,
		"action_section": "production",
		"action_label": "Open production",
		"recovery_steps": [],
	}
	return {"primary": primary, "actions": actions, "calendar": calendar_snapshot, "containers": container_position}


# endregion NEXT ACTION ENGINE


def daily_operational_action_generation():
	materialize_operational_actions()
