from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.utils import flt


# =============================================================================
# region WORKFORCE CAPACITY
# =============================================================================


def get_employee_capacity_snapshot(demand=None):
	"""Compare current production demand with configured employee capacity."""
	demand = demand or {}
	types = frappe.get_all(
		"BulkBite Employee Type",
		filters={"enabled": 1},
		fields=[
			"name", "employee_type_name", "description", "capacity_basis",
			"capacity_per_worker", "expected_hours_per_run", "payment_basis",
			"payment_rate", "working_assumptions",
		],
		order_by="employee_type_name",
	)
	active_counts = {}
	for employee_type in frappe.get_all(
		"BulkBite Employee",
		filters={"status": "Active", "available_for_production": 1},
		pluck="employee_type",
	):
		active_counts[employee_type] = active_counts.get(employee_type, 0) + 1
	rows = []
	for employee_type in types:
		required_capacity = _capacity_driver(employee_type.capacity_basis, demand)
		capacity_per_worker = flt(employee_type.capacity_per_worker)
		required_workers = math.ceil(required_capacity / capacity_per_worker) if required_capacity and capacity_per_worker else 0
		active_workers = active_counts.get(employee_type.name, 0)
		available_capacity = round(active_workers * capacity_per_worker, 3)
		worker_difference = active_workers - required_workers
		rows.append(
			{
				**employee_type,
				"required_capacity": round(required_capacity, 3),
				"available_capacity": available_capacity,
				"required_workers": required_workers,
				"active_workers": active_workers,
				"worker_difference": worker_difference,
				"status": "Under capacity" if worker_difference < 0 else "Over capacity" if worker_difference > 0 else "At capacity",
				"expected_run_cost": _expected_run_cost(employee_type, required_workers),
				"expected_monthly_cost": _expected_monthly_cost(employee_type, required_workers),
				"warning": _capacity_warning(employee_type, required_capacity),
			}
		)
	return {
		"rows": rows,
		"required_workers": sum(row["required_workers"] for row in rows),
		"active_workers": sum(row["active_workers"] for row in rows),
		"under_capacity_types": sum(1 for row in rows if row["status"] == "Under capacity"),
		"expected_run_cost": round(sum(row["expected_run_cost"] for row in rows), 2),
		"expected_monthly_cost": round(sum(row["expected_monthly_cost"] for row in rows), 2),
	}


def calculate_assignment_pay(employee_type, hours_worked=0, completion_status="Completed"):
	"""Freeze the payment facts attributable to one production run."""
	if completion_status != "Completed":
		return {"payment_basis": employee_type.payment_basis, "payment_rate": flt(employee_type.payment_rate), "payable_amount": 0}
	basis = employee_type.payment_basis
	rate = flt(employee_type.payment_rate)
	amount = flt(hours_worked) * rate if basis == "Hourly" else rate if basis == "Per Production Run" else 0
	return {"payment_basis": basis, "payment_rate": rate, "payable_amount": round(amount, 2)}


def post_production_employee_costs(run):
	"""Create one actual labour-cost entry per payable production assignment."""
	created = []
	for row in run.employees or []:
		if row.cost_entry:
			created.append(row.cost_entry)
			continue
		if row.completion_status != "Completed" or row.payment_basis not in {"Hourly", "Per Production Run"}:
			continue
		amount = flt(row.payable_amount)
		if amount <= 0:
			continue
		cost = frappe.get_doc(
			{
				"doctype": "BulkBite Cost Entry",
				"cost_date": run.production_date,
				"cost_category": "Labour",
				"payee": row.employee_name or row.employee,
				"quantity": flt(row.hours_worked) if row.payment_basis == "Hourly" else 1,
				"unit_rate": flt(row.payment_rate),
				"amount": amount,
				"production_plan": run.production_plan,
				"production_run": run.name,
				"employee": row.employee,
				"production_employee_row": row.name,
				"notes": _("Created from posted production run {0}.").format(run.name),
			}
		)
		cost.insert(ignore_permissions=True)
		row.db_set("cost_entry", cost.name, update_modified=False)
		created.append(cost.name)
	return created


def _capacity_driver(basis, demand):
	return flt(
		{
			"Meals per Production Run": demand.get("weekly_servings"),
			"Kg per Production Run": demand.get("weekly_output_qty"),
			"Customers Served": demand.get("total_customers"),
			"Hours Available": demand.get("production_hours"),
			"Runs per Period": demand.get("runs_per_period", 1),
		}.get(basis, 0)
	)


def _expected_run_cost(employee_type, required_workers):
	basis = employee_type.payment_basis
	rate = flt(employee_type.payment_rate)
	if basis == "Per Production Run":
		return round(required_workers * rate, 2)
	if basis == "Hourly":
		return round(required_workers * flt(employee_type.expected_hours_per_run) * rate, 2)
	return 0


def _expected_monthly_cost(employee_type, required_workers):
	basis = employee_type.payment_basis
	rate = flt(employee_type.payment_rate)
	if basis == "Monthly":
		return round(required_workers * rate, 2)
	if basis == "Weekly":
		return round(required_workers * rate * 4, 2)
	if basis in {"Hourly", "Per Production Run"}:
		return round(_expected_run_cost(employee_type, required_workers) * 4, 2)
	return 0


def _capacity_warning(employee_type, required_capacity):
	if required_capacity and flt(employee_type.capacity_per_worker) <= 0:
		return _("Set capacity per worker before relying on this role.")
	if employee_type.payment_basis == "Hourly" and flt(employee_type.expected_hours_per_run) <= 0:
		return _("Set expected hours per run to forecast hourly labour.")
	return None


# endregion WORKFORCE CAPACITY
