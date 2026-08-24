from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate

from bulkbite.planning import calculate_customer_demand


# =============================================================================
# region OPERATING COST CALCULATION
# =============================================================================


def calculate_operating_costs(from_date, to_date):
	"""Return expected cost rules and evidence-backed actual costs for a period."""
	start, end = getdate(from_date), getdate(to_date)
	drivers = _period_drivers(start, end)
	rules = frappe.get_all(
		"BulkBite Operating Cost Rule",
		filters={"enabled": 1},
		fields=["name", "cost_code", "cost_name", "cost_category", "basis", "rate", "default_quantity", "effective_from", "effective_to", "vat_treatment", "accounting_category"],
		order_by="cost_category asc, cost_name asc",
	)
	expected_rows = []
	for rule in rules:
		if rule.effective_from and getdate(rule.effective_from) > end:
			continue
		if rule.effective_to and getdate(rule.effective_to) < start:
			continue
		quantity = _rule_quantity(rule, drivers)
		expected_rows.append({**rule, "quantity": round(quantity, 3), "amount": round(quantity * flt(rule.rate), 2)})
	actual_rows = frappe.get_all(
		"BulkBite Cost Entry",
		filters={"cost_date": ["between", [start, end]]},
		fields=["name", "cost_date", "cost_rule", "cost_category", "payee", "quantity", "unit_rate", "amount", "vat_amount", "production_plan", "accounting_category"],
		order_by="cost_date asc, name asc",
	)
	breakdown = {}
	for row in expected_rows:
		breakdown.setdefault(row.cost_category, {"category": row.cost_category, "expected": 0.0, "actual": 0.0})["expected"] += flt(row.amount)
	for row in actual_rows:
		breakdown.setdefault(row.cost_category, {"category": row.cost_category, "expected": 0.0, "actual": 0.0})["actual"] += flt(row.amount)
	for row in breakdown.values():
		row["variance"] = round(row["actual"] - row["expected"], 2)
	return {
		"drivers": drivers,
		"expected_rows": expected_rows,
		"actual_rows": actual_rows,
		"breakdown": sorted(breakdown.values(), key=lambda row: row["category"]),
		"expected_total": round(sum(flt(row.amount) for row in expected_rows), 2),
		"actual_total": round(sum(flt(row.amount) for row in actual_rows), 2),
	}


def enrich_spend_report(report):
	"""Add revenue, operating costs, buying-cost bridges, savings, and qualified profit positions."""
	period = report["period"]
	operating = calculate_operating_costs(period["from_date"], period["to_date"])
	revenue = flt(operating["drivers"]["revenue"])
	expected_food = flt(report["summary"]["expected_spend"])
	actual_food = flt(report["summary"]["actual_spend"])
	expected_gross = revenue - expected_food
	actual_gross = revenue - actual_food
	report["operating_costs"] = operating
	report["profit"] = {
		"revenue": round(revenue, 2),
		"revenue_basis": "Configured customer plans overlapping the selected period",
		"expected_gross_profit": round(expected_gross, 2),
		"actual_gross_profit": round(actual_gross, 2),
		"expected_operating_result": round(expected_gross - flt(operating["expected_total"]), 2),
		"actual_operating_result": round(actual_gross - flt(operating["actual_total"]), 2),
		"actual_qualification": "Actual food and entered operating costs against configured customer-plan revenue",
	}
	return report


def _period_drivers(start, end):
	plans = frappe.get_all(
		"BulkBite Production Plan",
		filters={"period_start": ["<=", end], "period_end": [">=", start], "status": ["!=", "Cancelled"]},
		pluck="name",
	)
	drivers = {"customers": 0.0, "meals": 0.0, "kilograms": 0.0, "revenue": 0.0, "days": date_diff(end, start) + 1}
	for name in plans:
		plan = frappe.get_doc("BulkBite Production Plan", name)
		demand = calculate_customer_demand(plan.customer_mix)
		overlap_start = max(start, getdate(plan.period_start))
		overlap_end = min(end, getdate(plan.period_end))
		weeks = (date_diff(overlap_end, overlap_start) + 1) / 7
		drivers["customers"] += flt(demand["total_customers"]) * weeks
		drivers["meals"] += flt(demand["weekly_servings"]) * weeks
		drivers["kilograms"] += flt(demand["weekly_output_qty"]) * weeks
		cycle_weeks = max(max([int(row.get("cycle_weeks") or 4) for row in demand.get("mix") or []], default=4), 1)
		drivers["revenue"] += flt(demand["cycle_revenue"]) * weeks / cycle_weeks
	return {key: round(value, 2) for key, value in drivers.items()}


def _rule_quantity(rule, drivers):
	if rule.basis in {"Fixed", "Hourly"}:
		return flt(rule.default_quantity)
	if rule.basis == "Per Meal":
		return flt(drivers["meals"])
	if rule.basis == "Per Customer":
		return flt(drivers["customers"])
	if rule.basis == "Per Kg":
		return flt(drivers["kilograms"])
	if rule.basis == "Percentage of Revenue":
		return flt(drivers["revenue"]) / 100
	return 0


# endregion OPERATING COST CALCULATION
