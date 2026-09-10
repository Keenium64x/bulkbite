from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate

from bulkbite.customer_periods import calculate_customer_period_drivers, customer_periods_exist
from bulkbite.planning import build_plan_snapshot, calculate_customer_demand
from bulkbite.reporting_scope import is_demo_evidence
from bulkbite.workforce import get_employee_capacity_snapshot


# =============================================================================
# region OPERATING COST CALCULATION
# =============================================================================


def calculate_operating_costs(from_date, to_date):
	"""Return expected cost rules and evidence-backed actual costs for a period."""
	start, end = getdate(from_date), getdate(to_date)
	drivers = _period_drivers(start, end)
	rules = [
		rule for rule in frappe.get_all(
		"BulkBite Operating Cost Rule",
		filters={"enabled": 1, "cost_category": ("!=", "Labour")},
		fields=["name", "cost_code", "cost_name", "cost_category", "basis", "rate", "employee_count", "hours_per_employee", "default_quantity", "recurrence", "effective_from", "effective_to", "vat_treatment", "accounting_category", "notes"],
		order_by="cost_category asc, cost_name asc",
	)
		if not is_demo_evidence(rule, "name", "cost_code", "notes")
	]
	expected_rows = []
	for rule in rules:
		if rule.effective_from and getdate(rule.effective_from) > end:
			continue
		if rule.effective_to and getdate(rule.effective_to) < start:
			continue
		quantity = _rule_quantity(rule, drivers, start, end)
		expected_rows.append({**rule, "quantity": round(quantity, 3), "amount": round(quantity * flt(rule.rate), 2)})
	workforce = _expected_workforce_costs()
	expected_rows.extend(workforce)
	actual_rows = [
		row for row in frappe.get_all(
		"BulkBite Cost Entry",
		filters={"cost_date": ["between", [start, end]]},
		fields=["name", "cost_date", "cost_rule", "cost_category", "payee", "quantity", "unit_rate", "amount", "vat_amount", "production_plan", "accounting_category", "notes"],
		order_by="cost_date asc, name asc",
	)
		if not is_demo_evidence(row, "name", "cost_rule", "payee", "notes")
	]
	breakdown = {}
	for row in expected_rows:
		breakdown.setdefault(row["cost_category"], {"category": row["cost_category"], "expected": 0.0, "actual": 0.0})["expected"] += flt(row["amount"])
	for row in actual_rows:
		breakdown.setdefault(row.cost_category, {"category": row.cost_category, "expected": 0.0, "actual": 0.0})["actual"] += flt(row.amount)
	for row in breakdown.values():
		row["variance"] = round(row["actual"] - row["expected"], 2)
	return {
		"drivers": drivers,
		"expected_rows": expected_rows,
		"actual_rows": actual_rows,
		"breakdown": sorted(breakdown.values(), key=lambda row: row["category"]),
		"expected_total": round(sum(flt(row["amount"]) for row in expected_rows), 2),
		"actual_total": round(sum(flt(row.amount) for row in actual_rows), 2),
	}


def _expected_workforce_costs():
	"""Return employee-type forecasts separately from miscellaneous cost rules."""
	plan_name = frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")
	if not plan_name:
		return []
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	snapshot = get_employee_capacity_snapshot(calculate_customer_demand(plan.customer_mix))
	return [
		{
			"name": f"WORKFORCE::{row['name']}",
			"cost_code": None,
			"cost_name": row["employee_type_name"],
			"cost_category": "Labour",
			"basis": row["payment_basis"],
			"rate": row["payment_rate"],
			"quantity": row["required_workers"],
			"amount": row["expected_monthly_cost"],
			"workforce_forecast": 1,
		}
		for row in snapshot["rows"]
		if not is_demo_evidence(row, "name", "employee_type_name")
	]


def enrich_spend_report(report):
	"""Add revenue, operating costs, buying-cost bridges, savings, and qualified profit positions."""
	period = report["period"]
	operating = calculate_operating_costs(period["from_date"], period["to_date"])
	revenue = flt(operating["drivers"]["revenue"])
	expected_food = _expected_food_consumption_cost(period["from_date"], period["to_date"])
	production_actuals = _production_food_costs(period["from_date"], period["to_date"])
	actual_food = flt(production_actuals["actual_material_cost"])
	expected_gross = revenue - expected_food
	actual_gross = revenue - actual_food
	report["operating_costs"] = operating
	report["production_food_costs"] = production_actuals
	report["expected_food_consumption_cost"] = round(expected_food, 2)
	report["profit"] = {
		"revenue": round(revenue, 2),
		"revenue_basis": "Configured customer plans overlapping the selected period",
		"expected_gross_profit": round(expected_gross, 2),
		"actual_gross_profit": round(actual_gross, 2),
		"expected_operating_result": round(expected_gross - flt(operating["expected_total"]), 2),
		"actual_operating_result": round(actual_gross - flt(operating["actual_total"]), 2),
		"actual_qualification": _actual_profit_qualification(report, operating),
		"actual_complete": _actual_profit_complete(report, operating),
	}
	return report


def _period_drivers(start, end):
	if customer_periods_exist():
		return calculate_customer_period_drivers(start, end)
	plans = frappe.get_all(
		"BulkBite Production Plan",
		filters={"period_start": ["<=", end], "status": ["!=", "Cancelled"]},
		fields=["name", "period_start", "period_end"],
	)
	plans = [row for row in plans if not row.period_end or getdate(row.period_end) >= start]
	drivers = {"customers": 0.0, "meals": 0.0, "kilograms": 0.0, "revenue": 0.0, "days": date_diff(end, start) + 1}
	for plan_row in plans:
		plan = frappe.get_doc("BulkBite Production Plan", plan_row.name)
		demand = calculate_customer_demand(plan.customer_mix)
		overlap_start = max(start, getdate(plan.period_start))
		overlap_end = min(end, getdate(plan.period_end) if plan.period_end else end)
		weeks = (date_diff(overlap_end, overlap_start) + 1) / 7
		cycle_weeks = max(max([int(row.get("cycle_weeks") or 4) for row in demand.get("mix") or []], default=4), 1)
		drivers["customers"] += flt(demand["total_customers"]) * weeks / cycle_weeks
		drivers["meals"] += flt(demand["weekly_servings"]) * weeks
		drivers["kilograms"] += flt(demand["weekly_output_qty"]) * weeks
		drivers["revenue"] += flt(demand["cycle_revenue"]) * weeks / cycle_weeks
	return {key: round(value, 2) for key, value in drivers.items()}


def _actual_profit_complete(report, operating):
	if not flt(operating.get("drivers", {}).get("revenue")) and not operating.get("drivers", {}).get("customer_period_count", 0):
		return True
	return bool(
		report.get("production_food_costs", {}).get("run_count")
		and operating.get("actual_rows")
		and not operating.get("drivers", {}).get("incomplete_customer_period_count", 0)
	)


def _actual_profit_qualification(report, operating):
	if not flt(operating.get("drivers", {}).get("revenue")) and not operating.get("drivers", {}).get("customer_period_count", 0):
		return "No customer service falls in the selected dates."
	missing = []
	if not report.get("production_food_costs", {}).get("run_count"):
		missing.append("posted production usage")
	if not operating.get("actual_rows"):
		missing.append("operating costs")
	if operating.get("drivers", {}).get("incomplete_customer_period_count", 0):
		missing.append("historical customer evidence")
	if missing:
		return "Recorded result only. Still missing: {0}.".format(", ".join(missing))
	return "Complete recorded food, operating-cost, and customer-period evidence for the selected dates."


def _production_food_costs(start, end):
	"""Return ingredient cost consumed by posted production, separate from purchasing cash flow."""
	runs = [
		run for run in frappe.get_all(
		"BulkBite Production Run",
		filters={"production_date": ["between", [start, end]], "docstatus": 1, "stock_events_posted": 1},
		fields=["name", "production_date", "actual_output_qty", "actual_material_cost", "notes"],
		order_by="production_date asc, creation asc",
	)
		if not is_demo_evidence(run, "name", "notes")
	]
	return {
		"run_count": len(runs),
		"actual_output_qty": round(sum(flt(row.actual_output_qty) for row in runs), 3),
		"actual_material_cost": round(sum(flt(row.actual_material_cost) for row in runs), 2),
		"runs": runs,
	}


def _expected_food_consumption_cost(start, end):
	"""Value recipe ingredients consumed in overlapping customer-plan periods."""
	start, end = getdate(start), getdate(end)
	plans = frappe.get_all(
		"BulkBite Production Plan",
		filters={"period_start": ["<=", end], "status": ["!=", "Cancelled"]},
		fields=["name", "period_start", "period_end"],
	)
	total = 0.0
	for row in plans:
		if row.period_end and getdate(row.period_end) < start:
			continue
		plan = frappe.get_doc("BulkBite Production Plan", row.name)
		cycle_weeks = max(max([int(mix.cycle_weeks or 4) for mix in plan.customer_mix], default=4), 1)
		plan_rows, _requirements = build_plan_snapshot(plan, weeks=cycle_weeks)
		cycle_cost = sum(
			flt(ingredient.get("required_qty")) * flt(ingredient.get("valuation_rate"))
			for plan_row in plan_rows
			for ingredient in plan_row.get("ingredients") or []
		)
		overlap_start = max(start, getdate(plan.period_start))
		overlap_end = min(end, getdate(plan.period_end) if plan.period_end else end)
		period_share = (date_diff(overlap_end, overlap_start) + 1) / (cycle_weeks * 7)
		total += cycle_cost * period_share
	return round(total, 2)


def _rule_quantity(rule, drivers, start, end):
	multiplier = _recurrence_multiplier(rule.recurrence, start, end)
	if rule.basis == "Hourly":
		hours = flt(rule.hours_per_employee) or flt(rule.default_quantity)
		return max(int(rule.employee_count or 1), 1) * hours * multiplier
	if rule.basis == "Fixed":
		return flt(rule.default_quantity) * multiplier
	if rule.basis == "Per Meal":
		return flt(drivers["meals"])
	if rule.basis == "Per Customer":
		return flt(drivers["customers"])
	if rule.basis == "Per Kg":
		return flt(drivers["kilograms"])
	if rule.basis == "Percentage of Revenue":
		return flt(drivers["revenue"]) / 100
	return 0


def _recurrence_multiplier(recurrence, start, end):
	days = date_diff(end, start) + 1
	if recurrence == "Weekly":
		return days / 7
	if recurrence == "Monthly":
		return days / 30.4375
	return 1


# endregion OPERATING COST CALCULATION
