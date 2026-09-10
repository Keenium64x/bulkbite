from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate


# =============================================================================
# region CUSTOMER MIX PERIODS
# =============================================================================


def get_customer_mix_periods(from_date=None, to_date=None):
	"""Return frozen customer-count periods, optionally limited to an overlapping range."""
	rows = frappe.get_all(
		"BulkBite Customer Mix Period",
		fields=_period_fields(),
		order_by="effective_from asc, plan_type asc",
	)
	start = getdate(from_date) if from_date else None
	end = getdate(to_date) if to_date else None
	return [
		row for row in rows
		if (not end or getdate(row.effective_from) <= end)
		and (not start or not row.effective_to or getdate(row.effective_to) >= start)
	]


def ensure_plan_customer_periods(plan, evidence_status="Incomplete"):
	"""Create the frozen customer periods represented by one dated production direction."""
	if not plan.period_start:
		return []
	created = []
	for row in plan.customer_mix or []:
		if int(row.customer_count or 0) <= 0:
			continue
		existing = frappe.db.get_value(
			"BulkBite Customer Mix Period",
			{"production_plan": plan.name, "plan_type": row.plan_type},
			"name",
		)
		if existing:
			frappe.db.set_value(
				"BulkBite Customer Mix Period",
				existing,
				_period_values(plan, row),
				update_modified=False,
			)
			created.append(existing)
			continue
		doc = frappe.get_doc({
			"doctype": "BulkBite Customer Mix Period",
			"evidence_status": evidence_status,
			**_period_values(plan, row),
		}).insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def close_plan_customer_periods(plan_name, effective_to):
	"""Close only the open customer periods owned by one superseded direction."""
	for name in frappe.get_all(
		"BulkBite Customer Mix Period",
		filters={"production_plan": plan_name, "effective_to": ["is", "not set"]},
		pluck="name",
	):
		frappe.db.set_value("BulkBite Customer Mix Period", name, "effective_to", getdate(effective_to))


def calculate_customer_period_drivers(start, end):
	"""Calculate dated customer, meal, food, and revenue drivers from frozen customer periods."""
	start, end = getdate(start), getdate(end)
	drivers = {
		"customers": 0.0,
		"meals": 0.0,
		"kilograms": 0.0,
		"revenue": 0.0,
		"days": date_diff(end, start) + 1,
		"customer_period_count": 0,
		"incomplete_customer_period_count": 0,
	}
	periods = get_customer_mix_periods(start, end)
	for row in periods:
		overlap_start = max(start, getdate(row.effective_from))
		overlap_end = min(end, getdate(row.effective_to) if row.effective_to else end)
		if overlap_start > overlap_end:
			continue
		drivers["customer_period_count"] += 1
		if row.evidence_status == "Incomplete":
			drivers["incomplete_customer_period_count"] += 1
		days = date_diff(overlap_end, overlap_start) + 1
		weeks = days / 7
		customers = max(int(row.customer_count or 0), 0)
		cycle_days = max(int(row.cycle_weeks or 4), 1) * 7
		drivers["customers"] += customers * days / cycle_days
		drivers["meals"] += customers * int(row.meals_per_day or 0) * int(row.days_per_week or 0) * weeks
		drivers["kilograms"] += customers * int(row.meals_per_day or 0) * int(row.days_per_week or 0) * flt(row.serving_size_g) / 1000 * weeks
		drivers["revenue"] += customers * flt(row.cycle_price) * days / cycle_days
	return {
		key: int(value) if key.endswith("_count") else round(value, 2)
		for key, value in drivers.items()
	}


def customer_periods_exist():
	return bool(frappe.db.count("BulkBite Customer Mix Period"))


def _period_values(plan, row):
	return {
		"plan_type": row.plan_type,
		"customer_count": row.customer_count,
		"effective_from": plan.period_start,
		"effective_to": plan.period_end,
		"serving_size_g": row.serving_size_g,
		"meals_per_day": row.meals_per_day,
		"days_per_week": row.days_per_week,
		"cycle_weeks": row.cycle_weeks,
		"cycle_price": row.customer_price,
		"price_basis": row.price_basis,
		"production_plan": plan.name,
	}


def _period_fields():
	return [
		"name", "plan_type", "customer_count", "effective_from", "effective_to", "evidence_status", "serving_size_g",
		"meals_per_day", "days_per_week", "cycle_weeks", "cycle_price", "price_basis", "production_plan", "notes",
	]


# endregion CUSTOMER MIX PERIODS
