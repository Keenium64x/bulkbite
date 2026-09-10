from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from bulkbite.stock_production import round_operational_quantity
from bulkbite.truth_ledger import append_truth_event


# =============================================================================
# region SERVICE PERIOD RESOLUTION
# =============================================================================


def production_calendar_slot(rows, period_start, as_of_date=None, offset=0):
	"""Map the next scheduled production date to one repeating meal and cycle."""
	ordered_rows = _ordered_plan_rows(rows)
	if not ordered_rows:
		return {"row": None, "cycle_number": 1, "slot_index": 0, "planned_date": None}
	start = getdate(period_start or nowdate())
	today = getdate(as_of_date or nowdate())
	days_since_start = max((today - start).days, 0)
	upcoming_slot = (days_since_start + 6) // 7
	slot_index = max(upcoming_slot + int(offset or 0), 0)
	return _calendar_slot_at_index(ordered_rows, start, slot_index)


def resolve_elapsed_service_periods(rows, runs, period_start, as_of_date=None, intentional_skips=None):
	"""Resolve every elapsed service date independently without carrying shortages forward."""
	ordered_rows = _ordered_plan_rows(rows)
	if not ordered_rows:
		return []
	start = getdate(period_start or nowdate())
	today = getdate(as_of_date or nowdate())
	skip_by_date = {
		getdate(row.get("planned_date")): row
		for row in intentional_skips or []
		if row.get("planned_date") and row.get("status") == "Intentionally Skipped"
	}
	periods = []
	slot_index = 0
	while True:
		slot = _calendar_slot_at_index(ordered_rows, start, slot_index)
		if slot["planned_date"] >= today:
			break
		periods.append(_resolve_service_period(slot, runs, skip_by_date.get(slot["planned_date"])))
		slot_index += 1
	return periods


def resolve_current_service_period(rows, runs, period_start, as_of_date=None, intentional_skips=None, offset=0):
	"""Return the first current or future service period which has not been intentionally skipped."""
	skip_dates = {
		getdate(row.get("planned_date"))
		for row in intentional_skips or []
		if row.get("planned_date") and row.get("status") == "Intentionally Skipped"
	}
	offset = int(offset or 0)
	while True:
		slot = production_calendar_slot(rows, period_start, as_of_date, offset)
		if not slot["row"] or slot["planned_date"] not in skip_dates:
			break
		offset += 1
	actual_output, evidence = service_period_output(slot, runs)
	required_output = _required_output(slot["row"])
	planned_output = round_operational_quantity(slot["row"].get("planned_output_qty") or required_output)
	return {
		**slot,
		"required_output_qty": required_output,
		"planned_output_qty": planned_output,
		"actual_output_qty": actual_output,
		"remaining_output_qty": round_operational_quantity(max(planned_output - actual_output, 0)),
		"output_difference_qty": round_operational_quantity(actual_output - required_output),
		"evidence_runs": evidence,
	}


def service_period_output(slot, runs):
	"""Total direct and dated substitute output that belongs to one service period."""
	row = slot["row"] or {}
	meal_number = int(row.get("cycle_week") or row.get("week_number") or 0)
	cycle_number = int(slot.get("cycle_number") or 1)
	planned_date = getdate(slot["planned_date"])
	window_start = add_days(planned_date, -6)
	direct = []
	substitutes = []
	for run in runs or []:
		if not int(_run_value(run, "docstatus") or 0):
			continue
		action = _run_value(run, "direction_action") or "Advance Direction"
		run_cycle = int(_run_value(run, "cycle_number") or 1)
		run_meal = int(_run_value(run, "plan_week_number") or 0)
		if action != "Off Plan" and (run_cycle, run_meal) == (cycle_number, meal_number):
			direct.append(run)
			continue
		run_date = _run_value(run, "production_date")
		finished_item = _run_value(run, "finished_item")
		if run_date and window_start <= getdate(run_date) <= planned_date and finished_item == row.get("finished_item"):
			substitutes.append(run)
	evidence = direct + [run for run in substitutes if _run_name(run) not in {_run_name(item) for item in direct}]
	output = sum(flt(_run_value(run, "actual_output_qty")) for run in evidence)
	return round_operational_quantity(output), [_run_name(run) for run in evidence if _run_name(run)]


def missed_service_periods(rows, runs, period_start, as_of_date=None, intentional_skips=None):
	"""Return only elapsed missed periods for production history."""
	return [
		period for period in resolve_elapsed_service_periods(rows, runs, period_start, as_of_date, intentional_skips)
		if period["status"] == "Missed"
	]


def _resolve_service_period(slot, runs, intentional_skip=None):
	row = slot["row"]
	required_output = _required_output(row)
	actual_output, evidence = service_period_output(slot, runs)
	if intentional_skip:
		status = "Intentionally Skipped"
		missing_output = 0
	elif actual_output + 0.0005 >= required_output:
		status = "Fulfilled"
		missing_output = 0
	else:
		status = "Missed"
		missing_output = round_operational_quantity(required_output - actual_output)
	return {
		"cycle_number": slot["cycle_number"],
		"meal_number": int(row.get("cycle_week") or row.get("week_number") or 1),
		"production_plan_row": row.get("name"),
		"planned_date": slot["planned_date"],
		"finished_item": row.get("finished_item"),
		"finished_item_name": row.get("finished_item_name") or row.get("finished_item"),
		"required_output_qty": required_output,
		"actual_output_qty": actual_output,
		"missing_output_qty": missing_output,
		"status": status,
		"evidence_runs": evidence,
		"resolution_reason": (intentional_skip or {}).get("resolution_reason"),
	}


def _calendar_slot_at_index(ordered_rows, start, slot_index):
	row = dict(ordered_rows[slot_index % len(ordered_rows)])
	row["week_number"] = int(row.get("cycle_week") or row.get("week_number") or 1)
	row["cycle_week"] = row["week_number"]
	row["planned_date"] = add_days(start, slot_index * 7)
	return {
		"row": row,
		"cycle_number": slot_index // len(ordered_rows) + 1,
		"slot_index": slot_index,
		"planned_date": row["planned_date"],
	}


def _ordered_plan_rows(rows):
	return sorted(rows or [], key=lambda value: value.get("cycle_week") or value.get("week_number") or 0)


def _required_output(row):
	return round_operational_quantity(row.get("customer_required_output_qty") or row.get("planned_output_qty"))


def _run_name(run):
	return _run_value(run, "name")


def _run_value(run, fieldname):
	return run.get(fieldname) if isinstance(run, dict) else getattr(run, fieldname, None)


# endregion SERVICE PERIOD RESOLUTION


# =============================================================================
# region SERVICE PERIOD PERSISTENCE
# =============================================================================


def load_service_period_records(plan_name):
	"""Load final service-period evidence for one production direction."""
	if not plan_name:
		return []
	return frappe.get_all(
		"BulkBite Production Service Period",
		filters={"production_plan": plan_name},
		fields=[
			"name", "period_key", "production_plan", "production_plan_row", "cycle_number", "meal_number",
			"planned_date", "finished_item", "required_output_qty", "actual_output_qty", "missing_output_qty",
			"status", "resolution_reason", "truth_event", "customer_follow_up_action",
		],
		order_by="planned_date asc",
	)


def materialize_elapsed_service_periods(plan, rows, runs, as_of_date=None):
	"""Persist each elapsed service-period result exactly once in the current transaction."""
	known = load_service_period_records(plan.name)
	intentional = [row for row in known if row.status == "Intentionally Skipped"]
	resolved = resolve_elapsed_service_periods(rows, runs, plan.period_start, as_of_date, intentional)
	known_keys = {row.period_key for row in known}
	created = []
	for period in resolved:
		period_key = service_period_key(plan.name, period["planned_date"])
		if period_key in known_keys:
			continue
		created.append(_insert_closed_service_period(plan, period, period_key))
		known_keys.add(period_key)
	return created


def mark_service_period_skipped(plan, rows, planned_date, reason):
	"""Record one explicit future closure so the meal cycle advances without a missed-service debt."""
	date_value = getdate(planned_date)
	if date_value < getdate(nowdate()):
		frappe.throw(_("A past service period can no longer be changed to an intentional skip."))
	if not str(reason or "").strip():
		frappe.throw(_("Enter why this service period will be skipped."))
	slot = _slot_for_planned_date(rows, plan.period_start, date_value)
	period_key = service_period_key(plan.name, date_value)
	if frappe.db.exists("BulkBite Production Service Period", period_key):
		frappe.throw(_("This service period has already been resolved."))
	period = _resolve_service_period(slot, [], {"resolution_reason": str(reason).strip()})
	period["status"] = "Intentionally Skipped"
	period["missing_output_qty"] = 0
	return _insert_closed_service_period(plan, period, period_key)


def service_period_key(plan_name, planned_date):
	return f"{plan_name}:{getdate(planned_date).isoformat()}"


def _insert_closed_service_period(plan, period, period_key):
	frappe.db.sql(
		"select name from `tabDocType` where name = %s for update",
		("BulkBite Production Service Period",),
	)
	if frappe.db.exists("BulkBite Production Service Period", period_key):
		return frappe.get_doc("BulkBite Production Service Period", period_key)
	doc = frappe.get_doc({
		"doctype": "BulkBite Production Service Period",
		"period_key": period_key,
		"production_plan": plan.name,
		"production_plan_row": period.get("production_plan_row"),
		"cycle_number": period["cycle_number"],
		"meal_number": period["meal_number"],
		"planned_date": period["planned_date"],
		"finished_item": period.get("finished_item"),
		"required_output_qty": period["required_output_qty"],
		"actual_output_qty": period["actual_output_qty"],
		"missing_output_qty": period["missing_output_qty"],
		"status": period["status"],
		"resolution_reason": period.get("resolution_reason"),
	}).insert(ignore_permissions=True)
	follow_up = _insert_customer_follow_up(doc) if doc.status == "Missed" else None
	truth = append_truth_event(
		"PRODUCTION_SERVICE_PERIOD_CLOSED",
		doc.doctype,
		doc.name,
		{
			"period_key": doc.period_key,
			"production_plan": doc.production_plan,
			"production_plan_row": doc.production_plan_row,
			"cycle_number": doc.cycle_number,
			"meal_number": doc.meal_number,
			"planned_date": doc.planned_date,
			"finished_item": doc.finished_item,
			"required_output_qty": doc.required_output_qty,
			"actual_output_qty": doc.actual_output_qty,
			"missing_output_qty": doc.missing_output_qty,
			"status": doc.status,
			"resolution_reason": doc.resolution_reason,
			"evidence_runs": period.get("evidence_runs") or [],
			"customer_follow_up_action": follow_up.name if follow_up else None,
		},
	)
	doc.db_set(
		{
			"truth_event": truth.name,
			"customer_follow_up_action": follow_up.name if follow_up else None,
		},
		update_modified=False,
	)
	return doc


def _insert_customer_follow_up(period):
	return frappe.get_doc({
		"doctype": "BulkBite Operational Action",
		"title": _("Resolve missed customer meals"),
		"action_type": "Production Review",
		"due_date": add_days(period.planned_date, 1),
		"status": "Due",
		"target_section": "production",
		"reference_doctype": period.doctype,
		"reference_name": period.name,
		"consequence_note": _("Arrange the customer follow-up for {0} kg that was not produced.").format(period.missing_output_qty),
		"notes": _("Service period {0} closed as missed. This quantity does not carry into later production targets.").format(period.planned_date),
	}).insert(ignore_permissions=True)


def _slot_for_planned_date(rows, period_start, planned_date):
	start = getdate(period_start or nowdate())
	days = (getdate(planned_date) - start).days
	if days < 0 or days % 7:
		frappe.throw(_("Choose one of the plan's scheduled service dates."))
	ordered_rows = _ordered_plan_rows(rows)
	if not ordered_rows:
		frappe.throw(_("Add meals to the production direction first."))
	return _calendar_slot_at_index(ordered_rows, start, days // 7)


def daily_production_service_period_resolution():
	"""Close elapsed periods for every active dated production direction."""
	for plan_name in frappe.get_all("BulkBite Production Plan", filters={"status": "Active"}, pluck="name"):
		plan = frappe.get_doc("BulkBite Production Plan", plan_name)
		if not plan.period_start:
			continue
		from bulkbite.planning import build_plan_snapshot

		rows = build_plan_snapshot(plan, "Ingredients")[0]
		runs = frappe.get_all(
			"BulkBite Production Run",
			filters={"production_plan": plan.name},
			fields=[
				"name", "production_plan_row", "plan_week_number", "cycle_number", "direction_action",
				"production_date", "finished_item", "docstatus", "actual_output_qty",
			],
		)
		materialize_elapsed_service_periods(plan, rows, runs)


# endregion SERVICE PERIOD PERSISTENCE
