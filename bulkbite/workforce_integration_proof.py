from __future__ import annotations

import frappe

from bulkbite.api import get_employee_workspace, save_employee, save_employee_type, save_production_employees
from bulkbite.workforce import calculate_capacity_forecast, calculate_hour_capacity, get_employee_capacity_snapshot, get_employee_production_history, post_production_employee_costs


# =============================================================================
# region ROLLED-BACK LEAN WORKFORCE PROOF
# =============================================================================


def run_hours():
	"""Prove that individual employee-hours drive takt and capacity status."""
	under = calculate_hour_capacity(required_output_qty=120, labour_minutes_per_unit=6, available_team_hours=7)
	assert under == {
		"required_team_hours": 12.0, "available_team_hours": 7.0, "hour_difference": -5.0,
		"takt_minutes_per_unit": 3.5, "status": "Under capacity",
	}
	over = calculate_hour_capacity(required_output_qty=120, labour_minutes_per_unit=6, available_team_hours=13)
	assert over == {
		"required_team_hours": 12.0, "available_team_hours": 13.0, "hour_difference": 1.0,
		"takt_minutes_per_unit": 6.5, "status": "Over capacity",
	}
	return {"under_capacity": under, "over_capacity": over}


def run_capacity_carry_forward():
	"""Prove that early production suppresses later runs until its carried effort is exhausted."""
	mix = [{"plan_type": "Proof", "customer_count": 10, "meals_per_day": 1, "days_per_week": 1, "serving_size_g": 1000}]
	runs = [
		{"week_number": week, "run_number": 1, "scheduled_elapsed_hours": hours, "planned_people": 1}
		for week, hours in enumerate((30, 2, 2, 2), start=1)
	]
	weeks = calculate_capacity_forecast(mix, mix, 4, [], 60, runs)
	assert [row["scheduled_team_hours"] for row in weeks] == [30.0, 0.0, 0.0, 2.0]
	assert [row["run_count"] for row in weeks] == [1, 0, 0, 1]
	assert [row["week_team_hour_difference"] for row in weeks] == [20.0, -10.0, -10.0, -8.0]
	assert [row["closing_team_hour_balance"] for row in weeks] == [20.0, 10.0, 0.0, -8.0]
	assert [row["capacity_state"] for row in weeks] == ["ready", "idle", "idle", "under"]
	assert [row["status"] for row in weeks] == ["Over capacity", "Covered by earlier production", "Covered by earlier production", "Under capacity"]
	multi_runs = [
		{"week_number": week, "run_number": run, "scheduled_elapsed_hours": 6, "planned_people": 1}
		for week in range(1, 5)
		for run in range(1, 3)
	]
	multi_run_weeks = calculate_capacity_forecast(mix, mix, 4, [], 60, multi_runs)
	assert [row["run_count"] for row in multi_run_weeks] == [2, 2, 1, 2]
	assert [row["closing_team_hour_balance"] for row in multi_run_weeks] == [2.0, 4.0, 0.0, 2.0]
	return {"weeks": weeks, "multi_run_weeks": multi_run_weeks}


def run():
	"""Prove Lean capacity, immediate saves, hour evidence, and exactly-once costs."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("workforce_proof")
	try:
		type_name = _unique("Proof kitchen team")
		type_result = save_employee_type({
			"employee_type_name": type_name, "capacity_basis": "Kg per Production Run",
			"capacity_per_worker": 50, "expected_hours_per_run": 5,
			"payment_basis": "Hourly", "payment_rate": 50, "enabled": 1,
		})
		employee_results = [
			save_employee({
				"full_name": _unique("Proof Worker"), "employee_type": type_result["name"],
				"status": "Active", "available_for_production": 1, "available_hours_per_run": available_hours,
			})
			for available_hours in (5, 2)
		]
		workspace = get_employee_workspace()
		assert any(row.name == type_result["name"] for row in workspace["employee_types"])
		assert all(any(row.name == result["name"] for row in workspace["employees"]) for result in employee_results)

		theory = get_employee_capacity_snapshot({"weekly_output_qty": 120})
		assert theory["required_workers"] == 4
		assert theory["active_workers"] == 2
		assert theory["required_team_hours"] == 12
		assert theory["available_worker_hours"] == 7
		assert theory["hour_difference"] == -5
		assert theory["takt_minutes_per_kg"] == 3.5
		assert theory["status"] == "Under capacity"

		frappe.db.set_value("BulkBite Employee", employee_results[1]["name"], "available_hours_per_run", 8)
		buffer = get_employee_capacity_snapshot({"weekly_output_qty": 120})
		assert buffer["available_worker_hours"] == 13
		assert buffer["hour_difference"] == 1
		assert buffer["takt_minutes_per_kg"] == 6.5
		assert buffer["status"] == "Over capacity"

		draft_name = frappe.db.get_value("BulkBite Production Run", {"docstatus": 0}, "name", order_by="modified desc")
		if not draft_name:
			return {"under_capacity": theory, "over_capacity": buffer, "assignment": "skipped because no draft production exists"}
		run = save_production_employees(draft_name, [
			{"employee": employee_results[0]["name"], "completion_status": "Completed", "hours_worked": 4},
			{"employee": employee_results[1]["name"], "completion_status": "Completed", "hours_worked": 4},
		])
		assert len(run["employees"]) == 2
		run_doc = frappe.get_doc("BulkBite Production Run", draft_name)
		before_stock = frappe.db.count("BulkBite Stock Event")
		first = post_production_employee_costs(run_doc)
		second = post_production_employee_costs(run_doc.reload())
		assert first == second and len(first) == 2
		assert frappe.db.count("BulkBite Stock Event") == before_stock

		frappe.db.set_value("BulkBite Production Run", draft_name, "docstatus", 1, update_modified=False)
		history = get_employee_production_history([result["name"] for result in employee_results])
		assert all(rows and rows[0]["hours_worked"] == 4 for rows in history.values())
		actual = get_employee_capacity_snapshot({"weekly_output_qty": 120})
		assert actual["actual"]["run_count"] >= 1
		assert actual["actual"]["total_team_hours"] >= 8
		assert actual["actual"]["labour_minutes_per_kg"] > 0
		assert actual["planning_basis"] == "Actual rate"
		return {
			"under_capacity": theory, "over_capacity": buffer, "actual": actual["actual"], "history_rows": sum(len(rows) for rows in history.values()),
			"labour_costs": first, "stock_events_unchanged": True,
		}
	finally:
		frappe.db.rollback(save_point="workforce_proof")


def _unique(prefix):
	return f"{prefix} {frappe.generate_hash(length=8)}"


# endregion ROLLED-BACK LEAN WORKFORCE PROOF
