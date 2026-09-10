from __future__ import annotations

import frappe
from frappe.utils import getdate

from bulkbite.api import save_monthly_production_plan
from bulkbite.customer_periods import ensure_plan_customer_periods


# =============================================================================
# region KNOWN CUSTOMER HISTORY BOOTSTRAP
# =============================================================================


@frappe.whitelist()
def preview_known_customer_history():
	"""Show the exact real customer periods that can replace the demo direction."""
	return {
		"completed_cycle": {
			"from_date": "2026-08-01",
			"to_date": "2026-08-28",
			"customer_mix": [{"plan_type": "Full", "customer_count": 1}],
			"cycle_revenue": 2799.95,
			"evidence_status": "Confirmed Aggregate",
		},
		"next_cycle": {
			"from_date": "2026-09-12",
			"customer_mix": [{"plan_type": "Full", "customer_count": 2}],
			"cycle_revenue": 5599.90,
			"evidence_status": "Confirmed Aggregate",
		},
		"service_gap": {"from_date": "2026-08-29", "to_date": "2026-09-11"},
		"source_direction": _source_direction_name(),
		"warning": "Demo receipts, runs, costs, stock events, and balances remain separate evidence and are not converted by this customer-history operation.",
	}


@frappe.whitelist()
def apply_known_customer_history(approved=False):
	"""Create the two confirmed aggregate customer periods without fabricating operating evidence."""
	if not approved:
		frappe.throw("Approve the known customer-history preview before applying it.")
	result = apply_known_customer_history_records()
	frappe.db.commit()
	return result


def apply_known_customer_history_records(required_source=True):
	"""Apply the confirmed history inside the caller's transaction."""
	frappe.set_user("Administrator")
	source_name = _source_direction_name()
	if not source_name:
		if required_source:
			frappe.throw("Create a meal direction before applying the known customer history.")
		return {"skipped": True, "reason": "No meal direction is available as the recipe and capacity source."}
	source = frappe.get_doc("BulkBite Production Plan", source_name)
	is_demo_source = "DEMO FULL OPERATIONS V1" in str(source.notes or "")
	if is_demo_source:
		frappe.db.delete("BulkBite Customer Mix Period", {"production_plan": source.name})
		source.db_set({"status": "Cancelled", "period_end": getdate("2026-08-28")}, update_modified=False)
	completed = _ensure_direction_version(source, "2026-08-01", "2026-08-28", 1, "Completed")
	active = _ensure_direction_version(source, "2026-09-12", None, 2, "Active")
	_copy_future_vacations(source, active, "2026-09-12")
	frappe.db.set_value(
		"BulkBite Production Plan",
		{"name": ("not in", [completed.name, active.name]), "status": "Active"},
		"status",
		"Completed",
		update_modified=False,
	)
	return {
		"completed_plan": completed.name,
		"active_plan": active.name,
		"customer_periods": frappe.get_all(
			"BulkBite Customer Mix Period",
			filters={"production_plan": ("in", [completed.name, active.name])},
			fields=["plan_type", "customer_count", "effective_from", "effective_to", "cycle_price", "evidence_status", "production_plan"],
			order_by="effective_from asc",
		),
	}


def _ensure_direction_version(source, period_start, period_end, full_customers, status):
	title = f"Real customer direction from {period_start}"
	existing = frappe.db.get_value("BulkBite Production Plan", {"plan_title": title}, "name")
	if existing:
		plan = frappe.get_doc("BulkBite Production Plan", existing)
		plan.set("customer_mix", _customer_mix(source, full_customers))
		plan.period_start = getdate(period_start)
		plan.period_end = getdate(period_end) if period_end else None
		plan.status = status
		plan.save(ignore_permissions=True)
	else:
		payload = _plan_payload(source, period_start, full_customers, title)
		result = save_monthly_production_plan(payload)
		plan = frappe.get_doc("BulkBite Production Plan", result["name"])
	plan.db_set({"status": status, "period_end": getdate(period_end) if period_end else None}, update_modified=False)
	ensure_plan_customer_periods(plan.reload(), evidence_status="Confirmed Aggregate")
	for period_name in frappe.get_all("BulkBite Customer Mix Period", filters={"production_plan": plan.name}, pluck="name"):
		frappe.db.set_value(
			"BulkBite Customer Mix Period",
			period_name,
			{"effective_to": getdate(period_end) if period_end else None, "evidence_status": "Confirmed Aggregate"},
			update_modified=False,
		)
	return plan.reload()


def _plan_payload(source, period_start, full_customers, title):
	return {
		"plan_title": title,
		"period_start": period_start,
		"customer_changes_from": period_start,
		"customer_mix": _customer_mix(source, full_customers),
		"purchase_routes": [{"item_category": row.item_category, "supplier": row.supplier, "use_discounted_price": row.use_discounted_price} for row in source.purchase_routes],
		"plan_rows": [{"recipe": row.recipe, "finished_item": row.finished_item, "extra_output_qty": 0} for row in source.plan_rows],
		"forecast_weeks": 4,
		"default_team_template": source.default_team_template,
		"capacity_windows": [{"scheduled_elapsed_hours": row.scheduled_elapsed_hours, "runs_per_week": row.runs_per_week, "team_template": row.team_template} for row in source.capacity_windows],
		"capacity_runs": [{"week_number": row.week_number, "run_number": row.run_number, "day_of_week": row.day_of_week, "planned_output_qty": row.planned_output_qty, "output_mode": row.output_mode, "scheduled_elapsed_hours": row.scheduled_elapsed_hours, "team_template": row.team_template, "planned_people": row.planned_people} for row in source.capacity_runs],
		"forecast_customer_mix": [{"plan_type": row.plan_type, "target_customers": full_customers if row.plan_type == "Full" else 0, "target_week": 1} for row in source.customer_mix],
		"location": "Ingredients",
	}


def _customer_mix(source, full_customers):
	return [
		{
			"plan_type": row.plan_type,
			"customer_count": full_customers if row.plan_type == "Full" else 0,
			"price_basis": "Normal",
		}
		for row in source.customer_mix
	]


def _copy_future_vacations(source, target, effective_from):
	if source.name == target.name:
		return
	for vacation in frappe.get_all(
		"BulkBite Planning Vacation",
		filters={"production_plan": source.name, "status": "Active", "from_date": (">=", effective_from)},
		fields=["name", "vacation_name", "from_date", "to_date"],
	):
		filters = {
			"production_plan": target.name,
			"status": "Active",
			"from_date": vacation.from_date,
			"to_date": vacation.to_date,
		}
		if not frappe.db.exists("BulkBite Planning Vacation", filters):
			frappe.get_doc({
				"doctype": "BulkBite Planning Vacation",
				"production_plan": target.name,
				"vacation_name": vacation.vacation_name,
				"from_date": vacation.from_date,
				"to_date": vacation.to_date,
			}).insert(ignore_permissions=True)
		frappe.db.set_value("BulkBite Planning Vacation", vacation.name, "status", "Deleted", update_modified=False)


def _source_direction_name():
	name = frappe.db.get_value("BulkBite Production Plan", {"notes": ("like", "%DEMO FULL OPERATIONS V1%")}, "name", order_by="modified desc")
	return name or frappe.db.get_value("BulkBite Production Plan", {}, "name", order_by="modified desc")


# endregion KNOWN CUSTOMER HISTORY BOOTSTRAP
