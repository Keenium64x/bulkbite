from __future__ import annotations

import frappe

from bulkbite.api import get_employee_workspace, save_employee, save_employee_type, save_production_employees
from bulkbite.workforce import get_employee_capacity_snapshot, get_employee_production_history, post_production_employee_costs


# =============================================================================
# region ROLLED-BACK LEAN WORKFORCE PROOF
# =============================================================================


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
				"status": "Active", "available_for_production": 1,
			})
			for _ in range(2)
		]
		workspace = get_employee_workspace()
		assert any(row.name == type_result["name"] for row in workspace["employee_types"])
		assert all(any(row.name == result["name"] for row in workspace["employees"]) for result in employee_results)

		theory = get_employee_capacity_snapshot({"weekly_output_qty": 120})
		assert theory["required_workers"] == 3
		assert theory["active_workers"] == 2
		assert theory["required_team_hours"] == 12
		assert theory["takt_minutes_per_kg"] == 2.5
		assert theory["status"] == "Under capacity"
		assert theory["worker_difference"] == -1

		draft_name = frappe.db.get_value("BulkBite Production Run", {"docstatus": 0}, "name", order_by="modified desc")
		if not draft_name:
			return {"capacity": theory, "assignment": "skipped because no draft production exists"}
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
			"theory": theory, "actual": actual["actual"], "history_rows": sum(len(rows) for rows in history.values()),
			"labour_costs": first, "stock_events_unchanged": True,
		}
	finally:
		frappe.db.rollback(save_point="workforce_proof")


def _unique(prefix):
	return f"{prefix} {frappe.generate_hash(length=8)}"


# endregion ROLLED-BACK LEAN WORKFORCE PROOF
