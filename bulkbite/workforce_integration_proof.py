from __future__ import annotations

import frappe

from bulkbite.api import get_employee_workspace, save_employee, save_employee_type, save_production_employees
from bulkbite.workforce import calculate_hour_capacity, get_employee_capacity_snapshot, get_employee_production_history, post_production_employee_costs


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
