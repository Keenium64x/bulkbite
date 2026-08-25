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
	available_people = frappe.get_all(
		"BulkBite Employee",
		filters={"status": "Active", "available_for_production": 1},
		fields=["name", "full_name", "employee_type", "available_hours_per_run"],
		order_by="full_name",
	)
	people_by_type = {}
	for employee in available_people:
		people_by_type.setdefault(employee.employee_type, []).append(employee)
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
		people = people_by_type.get(employee_type.name, [])
		active_workers = len(people)
		availability = [
			{
				"employee": person.name,
				"full_name": person.full_name,
				"available_hours": round(flt(person.available_hours_per_run), 2),
			}
			for person in people
		]
		available_worker_hours = round(sum(row["available_hours"] for row in availability), 2)
		units_per_labour_hour = capacity_per_worker / planned_hours if capacity_per_worker and planned_hours else 0
		available_capacity = round(available_worker_hours * units_per_labour_hour, 3)
		worker_difference = active_workers - required_workers
		hour_difference = round(available_worker_hours - required_team_hours, 2)
		rows.append(
			{
				**employee_type,
				"required_capacity": round(required_capacity, 3),
				"available_capacity": available_capacity,
				"available_worker_hours": available_worker_hours,
				"hour_difference": hour_difference,
				"available_people": availability,
				"required_team_hours": round(required_team_hours, 2),
				"theoretical_labour_minutes_per_unit": round(theoretical_labour_minutes_per_unit, 2),
				"theoretical_units_per_labour_hour": round(60 / theoretical_labour_minutes_per_unit, 2) if theoretical_labour_minutes_per_unit else 0,
				"takt_minutes_per_unit": round(planned_hours * 60 / required_capacity, 2) if planned_hours and required_capacity else 0,
				"required_workers": required_workers,
				"active_workers": active_workers,
				"worker_difference": worker_difference,
				"status": "Under capacity" if hour_difference < 0 else "Over capacity" if hour_difference > 0 else "At capacity",
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
	decision = calculate_hour_capacity(required_output_qty, planning_minutes_per_kg, available_worker_hours)
	required_team_hours = decision["required_team_hours"]
	average_available_hours = available_worker_hours / active_workers if active_workers else 0
	required_workers = (
		math.ceil(required_team_hours / average_available_hours)
		if required_team_hours and average_available_hours else sum(row["required_workers"] for row in rows)
	)
	worker_difference = active_workers - required_workers
	hour_difference = decision["hour_difference"]
	has_capacity_rate = bool(planning_minutes_per_kg)
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
		"hour_difference": hour_difference,
		"status": "Capacity not configured" if required_output_qty and not has_capacity_rate else decision["status"],
		"planning_basis": "Actual rate" if actual_minutes_per_kg else "Theoretical rate",
		"planned_hours_per_worker": round(average_available_hours, 2),
		"available_worker_hours": round(available_worker_hours, 2),
		"required_team_hours": round(required_team_hours, 2),
		"takt_minutes_per_kg": decision["takt_minutes_per_unit"],
		"theoretical_labour_minutes_per_kg": round(theoretical_labour_minutes_per_kg, 2),
		"planning_labour_minutes_per_kg": round(planning_minutes_per_kg, 2),
		"maximum_labour_minutes_per_kg": round(maximum_minutes_per_kg, 2),
		"efficiency_improvement_percent": round(improvement_percent, 1),
		"under_capacity_types": sum(1 for row in rows if row["status"] == "Under capacity"),
		"expected_run_cost": round(sum(row["expected_run_cost"] for row in rows), 2),
		"expected_monthly_cost": round(sum(row["expected_monthly_cost"] for row in rows), 2),
		"actual": recent_actual,
	}


def calculate_hour_capacity(required_output_qty, labour_minutes_per_unit, available_team_hours):
	"""Return the production capacity decision from demand, work rate, and employee availability."""
	required_output_qty = flt(required_output_qty)
	labour_minutes_per_unit = flt(labour_minutes_per_unit)
	available_team_hours = flt(available_team_hours)
	required_team_hours = required_output_qty * labour_minutes_per_unit / 60
	hour_difference = round(available_team_hours - required_team_hours, 2)
	return {
		"required_team_hours": round(required_team_hours, 2),
		"available_team_hours": round(available_team_hours, 2),
		"hour_difference": hour_difference,
		"takt_minutes_per_unit": round(available_team_hours * 60 / required_output_qty, 2) if required_output_qty else 0,
		"status": "Under capacity" if hour_difference < 0 else "Over capacity" if hour_difference > 0 else "At capacity",
	}


def calculate_run_performance(actual_output_qty, actual_elapsed_hours, employees, planned_takt_minutes_per_kg=0):
	"""Calculate actual production labour evidence and compare it with the frozen planned takt."""
	actual_output_qty = flt(actual_output_qty)
	actual_elapsed_hours = flt(actual_elapsed_hours)
	completed = [row for row in employees or [] if row.get("completion_status") == "Completed"]
	actual_labour_hours = sum(flt(row.get("hours_worked")) for row in completed)
	actual_rate = actual_labour_hours * 60 / actual_output_qty if actual_output_qty else 0
	planned_takt = flt(planned_takt_minutes_per_kg)
	variance = actual_rate - planned_takt if actual_rate and planned_takt else 0
	if not actual_rate or not planned_takt:
		status = "Not measured"
	elif abs(variance) <= 0.1:
		status = "On pace"
	elif variance < 0:
		status = "Faster than takt"
	else:
		status = "Slower than takt"
	return {
		"actual_elapsed_hours": round(actual_elapsed_hours, 2),
		"actual_team_size": len({row.get("employee") for row in completed if row.get("employee")}),
		"actual_labour_hours": round(actual_labour_hours, 2),
		"actual_labour_minutes_per_kg": round(actual_rate, 2),
		"planned_takt_minutes_per_kg": round(planned_takt, 2),
		"takt_variance_minutes_per_kg": round(variance, 2),
		"takt_status": status,
	}


def calculate_capacity_forecast(current_mix, target_mix, forecast_weeks, capacity_windows, labour_minutes_per_kg):
	"""Forecast weekly output, labour-hours, elapsed duration, and people gaps."""
	forecast_weeks = max(int(forecast_weeks or 4), 1)
	current_by_plan = {row.get("plan_type"): row for row in current_mix or []}
	target_by_plan = {row.get("plan_type"): row for row in target_mix or []}
	windows = {int(row.get("week_number") or 0): row for row in capacity_windows or []}
	rows = []
	for week in range(1, forecast_weeks + 1):
		mix = []
		for plan_type, current in current_by_plan.items():
			target = target_by_plan.get(plan_type) or {}
			target_week = max(int(target.get("target_week") or forecast_weeks), 1)
			progress = min(week / target_week, 1)
			current_customers = flt(current.get("customer_count"))
			target_customers = flt(target.get("target_customers")) if target.get("target_customers") is not None else current_customers
			mix.append({**current, "customer_count": round(current_customers + (target_customers - current_customers) * progress)})
		demand = _forecast_demand(mix)
		cycle_week = ((week - 1) % 4) + 1
		window = windows.get(cycle_week) or {}
		elapsed_hours = flt(window.get("scheduled_elapsed_hours"))
		runs = max(int(window.get("runs_per_week") or 1), 1)
		team_size = max(int(window.get("team_size") or 0), 0)
		team_hours = elapsed_hours * runs * team_size
		required_hours = flt(demand["weekly_output_qty"]) * flt(labour_minutes_per_kg) / 60
		required_people = math.ceil(required_hours / (elapsed_hours * runs)) if required_hours and elapsed_hours else 0
		people_difference = team_size - required_people
		rows.append({
			"week_number": week,
			"cycle_week": cycle_week,
			"customers": demand["total_customers"],
			"required_output_qty": demand["weekly_output_qty"],
			"scheduled_elapsed_hours": round(elapsed_hours * runs, 2),
			"scheduled_team_hours": round(team_hours, 2),
			"planned_takt_minutes_per_kg": round(team_hours * 60 / demand["weekly_output_qty"], 2) if demand["weekly_output_qty"] else 0,
			"current_labour_minutes_per_kg": round(flt(labour_minutes_per_kg), 2),
			"required_team_hours": round(required_hours, 2),
			"expected_elapsed_hours": round(required_hours / team_size, 2) if team_size else 0,
			"team_size": team_size,
			"required_people": required_people,
			"people_difference": people_difference,
			"status": "Under capacity" if people_difference < 0 else "Over capacity" if people_difference > 0 else "At capacity",
		})
	return rows


def _forecast_demand(mix):
	weekly_servings = sum(flt(row.get("customer_count")) * flt(row.get("meals_per_day")) * flt(row.get("days_per_week")) for row in mix)
	weekly_output = sum(flt(row.get("customer_count")) * flt(row.get("meals_per_day")) * flt(row.get("days_per_week")) * flt(row.get("serving_size_g")) / 1000 for row in mix)
	return {
		"total_customers": int(sum(flt(row.get("customer_count")) for row in mix)),
		"weekly_servings": round(weekly_servings),
		"weekly_output_qty": round(weekly_output, 3),
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
