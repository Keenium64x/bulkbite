from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.utils import flt


# =============================================================================
# region WORKFORCE CAPACITY
# =============================================================================


def get_employee_capacity_snapshot(demand=None):
	"""Compare planned output with theoretical and demonstrated team capacity."""
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
	recent_actual = _recent_actual_capacity()
	rows = []
	for employee_type in types:
		required_capacity = _capacity_driver(employee_type.capacity_basis, demand)
		capacity_per_worker = flt(employee_type.capacity_per_worker)
		planned_hours = flt(employee_type.expected_hours_per_run)
		theoretical_labour_minutes_per_unit = (
			planned_hours * 60 / capacity_per_worker if planned_hours and capacity_per_worker else 0
		)
		required_team_hours = required_capacity * theoretical_labour_minutes_per_unit / 60
		required_workers = math.ceil(required_team_hours / planned_hours) if required_team_hours and planned_hours else 0
		active_workers = active_counts.get(employee_type.name, 0)
		available_capacity = round(active_workers * capacity_per_worker, 3)
		available_worker_hours = round(active_workers * planned_hours, 2)
		worker_difference = active_workers - required_workers
		rows.append(
			{
				**employee_type,
				"required_capacity": round(required_capacity, 3),
				"available_capacity": available_capacity,
				"available_worker_hours": available_worker_hours,
				"required_team_hours": round(required_team_hours, 2),
				"theoretical_labour_minutes_per_unit": round(theoretical_labour_minutes_per_unit, 2),
				"theoretical_units_per_labour_hour": round(60 / theoretical_labour_minutes_per_unit, 2) if theoretical_labour_minutes_per_unit else 0,
				"takt_minutes_per_unit": round(planned_hours * 60 / required_capacity, 2) if planned_hours and required_capacity else 0,
				"required_workers": required_workers,
				"active_workers": active_workers,
				"worker_difference": worker_difference,
				"status": "Under capacity" if worker_difference < 0 else "Over capacity" if worker_difference > 0 else "At capacity",
				"expected_run_cost": _expected_run_cost(employee_type, required_workers),
				"expected_monthly_cost": _expected_monthly_cost(employee_type, required_workers),
				"warning": _capacity_warning(employee_type, required_capacity),
			}
		)
	return _team_capacity_summary(demand, rows, recent_actual)


def get_employee_production_history(employee_names):
	"""Return posted production-hour evidence grouped by employee profile."""
	history = {name: [] for name in employee_names or []}
	if not history:
		return history
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"docstatus": 1},
		fields=["name", "production_date", "finished_item", "actual_output_qty"],
		order_by="production_date desc, modified desc",
		limit=100,
	)
	if not runs:
		return history
	run_by_name = {row.name: row for row in runs}
	assignments = frappe.get_all(
		"BulkBite Production Employee",
		filters={
			"parent": ("in", list(run_by_name)),
			"parenttype": "BulkBite Production Run",
			"employee": ("in", list(history)),
		},
		fields=[
			"parent", "employee", "employee_name", "employee_type", "hours_worked",
			"completion_status", "payment_basis", "payment_rate", "payable_amount", "cost_entry",
		],
	)
	for assignment in assignments:
		run = run_by_name.get(assignment.parent)
		if not run:
			continue
		history[assignment.employee].append(
			{
				"production_run": run.name,
				"production_date": run.production_date,
				"finished_item": run.finished_item,
				"actual_output_qty": round(flt(run.actual_output_qty), 3),
				"hours_worked": round(flt(assignment.hours_worked), 2),
				"completion_status": assignment.completion_status,
				"payment_basis": assignment.payment_basis,
				"payment_rate": round(flt(assignment.payment_rate), 2),
				"payable_amount": round(flt(assignment.payable_amount), 2),
				"cost_entry": assignment.cost_entry,
			}
		)
	for rows in history.values():
		rows.sort(key=lambda row: (str(row["production_date"]), row["production_run"]), reverse=True)
	return history


def _recent_actual_capacity(limit=4):
	"""Summarise the latest posted runs that contain completed labour hours."""
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"docstatus": 1, "actual_output_qty": (">", 0)},
		fields=["name", "production_date", "finished_item", "actual_output_qty"],
		order_by="production_date desc, modified desc",
		limit=12,
	)
	if not runs:
		return _empty_actual_capacity()
	assignments = frappe.get_all(
		"BulkBite Production Employee",
		filters={
			"parent": ("in", [run.name for run in runs]),
			"parenttype": "BulkBite Production Run",
			"completion_status": "Completed",
			"hours_worked": (">", 0),
		},
		fields=["parent", "employee", "hours_worked"],
	)
	assignments_by_run = {}
	for row in assignments:
		assignments_by_run.setdefault(row.parent, []).append(row)
	evidence = []
	for run in runs:
		team = assignments_by_run.get(run.name, [])
		if not team:
			continue
		team_hours = sum(flt(row.hours_worked) for row in team)
		team_size = len({row.employee for row in team})
		output_qty = flt(run.actual_output_qty)
		evidence.append(
			{
				"production_run": run.name,
				"production_date": run.production_date,
				"finished_item": run.finished_item,
				"output_qty": round(output_qty, 3),
				"team_members": team_size,
				"team_hours": round(team_hours, 2),
				"average_hours_per_worker": round(team_hours / team_size, 2) if team_size else 0,
				"labour_minutes_per_kg": round(team_hours * 60 / output_qty, 2) if output_qty else 0,
				"kg_per_labour_hour": round(output_qty / team_hours, 2) if team_hours else 0,
			}
		)
		if len(evidence) == limit:
			break
	if not evidence:
		return _empty_actual_capacity()
	total_output = sum(row["output_qty"] for row in evidence)
	total_hours = sum(row["team_hours"] for row in evidence)
	worker_appearances = sum(row["team_members"] for row in evidence)
	return {
		"source": f"Latest {len(evidence)} posted run{'s' if len(evidence) != 1 else ''}",
		"run_count": len(evidence),
		"total_output_qty": round(total_output, 3),
		"total_team_hours": round(total_hours, 2),
		"average_team_size": round(worker_appearances / len(evidence), 1),
		"average_hours_per_worker": round(total_hours / worker_appearances, 2) if worker_appearances else 0,
		"labour_minutes_per_kg": round(total_hours * 60 / total_output, 2) if total_output else 0,
		"kg_per_labour_hour": round(total_output / total_hours, 2) if total_hours else 0,
		"runs": evidence,
	}


def _empty_actual_capacity():
	return {
		"source": "No posted run evidence yet", "run_count": 0, "total_output_qty": 0,
		"total_team_hours": 0, "average_team_size": 0, "average_hours_per_worker": 0,
		"labour_minutes_per_kg": 0, "kg_per_labour_hour": 0, "runs": [],
	}


def _team_capacity_summary(demand, rows, recent_actual):
	required_output_qty = flt(demand.get("weekly_output_qty"))
	active_workers = sum(row["active_workers"] for row in rows)
	available_worker_hours = sum(row["available_worker_hours"] for row in rows)
	theoretical_team_hours = sum(row["required_team_hours"] for row in rows)
	theoretical_labour_minutes_per_kg = (
		theoretical_team_hours * 60 / required_output_qty if required_output_qty else 0
	)
	actual_minutes_per_kg = flt(recent_actual.get("labour_minutes_per_kg"))
	planning_minutes_per_kg = actual_minutes_per_kg or theoretical_labour_minutes_per_kg
	required_team_hours = required_output_qty * planning_minutes_per_kg / 60
	planned_hours_per_worker = _average_planned_hours(rows)
	required_workers = (
		math.ceil(required_team_hours / planned_hours_per_worker)
		if required_team_hours and planned_hours_per_worker else sum(row["required_workers"] for row in rows)
	)
	worker_difference = active_workers - required_workers
	has_capacity_rate = bool(planning_minutes_per_kg and planned_hours_per_worker)
	maximum_minutes_per_kg = available_worker_hours * 60 / required_output_qty if required_output_qty else 0
	improvement_percent = (
		max((planning_minutes_per_kg - maximum_minutes_per_kg) / planning_minutes_per_kg * 100, 0)
		if planning_minutes_per_kg else 0
	)
	return {
		"rows": rows,
		"required_output_qty": round(required_output_qty, 3),
		"required_workers": required_workers,
		"active_workers": active_workers,
		"worker_difference": worker_difference,
		"status": "Capacity not configured" if required_output_qty and not has_capacity_rate else "Under capacity" if worker_difference < 0 else "Buffer available" if worker_difference > 0 else "Capacity ready",
		"planning_basis": "Actual rate" if actual_minutes_per_kg else "Theoretical rate",
		"planned_hours_per_worker": round(planned_hours_per_worker, 2),
		"available_worker_hours": round(available_worker_hours, 2),
		"required_team_hours": round(required_team_hours, 2),
		"takt_minutes_per_kg": round(planned_hours_per_worker * 60 / required_output_qty, 2) if required_output_qty else 0,
		"theoretical_labour_minutes_per_kg": round(theoretical_labour_minutes_per_kg, 2),
		"planning_labour_minutes_per_kg": round(planning_minutes_per_kg, 2),
		"maximum_labour_minutes_per_kg": round(maximum_minutes_per_kg, 2),
		"efficiency_improvement_percent": round(improvement_percent, 1),
		"under_capacity_types": sum(1 for row in rows if row["status"] == "Under capacity"),
		"expected_run_cost": round(sum(row["expected_run_cost"] for row in rows), 2),
		"expected_monthly_cost": round(sum(row["expected_monthly_cost"] for row in rows), 2),
		"actual": recent_actual,
	}


def _average_planned_hours(rows):
	worker_hours = [flt(row["expected_hours_per_run"]) for row in rows if flt(row["expected_hours_per_run"]) > 0]
	return sum(worker_hours) / len(worker_hours) if worker_hours else 0


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
	from bulkbite.finance_ledger import create_actual_expense

	expense_type = frappe.db.get_value("BulkBite Expense Type", {"expense_type_name": "Production labour"}, "name")
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
		cost, event = create_actual_expense(
			{
				"cost_date": run.production_date,
				"expense_type": expense_type,
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
			},
			reference_doctype=run.doctype,
			reference_name=run.name,
			reference_line=row.name,
			ignore_permissions=True,
		)
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
