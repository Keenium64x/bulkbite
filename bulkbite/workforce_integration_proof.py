from __future__ import annotations

import frappe

from bulkbite.api import save_production_employees
from bulkbite.workforce import get_employee_capacity_snapshot, post_production_employee_costs


# =============================================================================
# region ROLLED-BACK WORKFORCE PROOF
# =============================================================================


def run():
	"""Prove workforce capacity, pay freezing, and exactly-once labour costs."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("workforce_proof")
	try:
		type_doc = frappe.get_doc({
			"doctype": "BulkBite Employee Type", "employee_type_name": _unique("Proof kitchen assistant"),
			"capacity_basis": "Meals per Production Run", "capacity_per_worker": 100,
			"expected_hours_per_run": 4, "payment_basis": "Per Production Run", "payment_rate": 250, "enabled": 1,
		}).insert()
		employee = frappe.get_doc({
			"doctype": "BulkBite Employee", "full_name": "Proof Worker", "employee_type": type_doc.name,
			"status": "Active", "available_for_production": 1,
		}).insert()
		snapshot = get_employee_capacity_snapshot({"weekly_servings": 250})
		row = next(value for value in snapshot["rows"] if value["name"] == type_doc.name)
		assert row["required_workers"] == 3 and row["active_workers"] == 1 and row["status"] == "Under capacity"

		run_name = frappe.db.get_value("BulkBite Production Run", {"docstatus": 0}, "name", order_by="modified desc")
		if not run_name:
			return {"capacity": row, "assignment": "skipped because no draft production exists"}
		run = save_production_employees(run_name, [{"employee": employee.name, "completion_status": "Completed", "hours_worked": 4}])
		assert len(run["employees"]) == 1 and run["employees"][0]["payable_amount"] == 250
		run_doc = frappe.get_doc("BulkBite Production Run", run_name)
		before_stock = frappe.db.count("BulkBite Stock Event")
		first = post_production_employee_costs(run_doc)
		second = post_production_employee_costs(run_doc.reload())
		assert first == second and len(first) == 1
		assert frappe.db.count("BulkBite Cost Entry", {"production_employee_row": run_doc.employees[0].name}) == 1
		assert frappe.db.count("BulkBite Stock Event") == before_stock
		return {"capacity": row, "labour_cost": first[0], "stock_events_unchanged": True}
	finally:
		frappe.db.rollback(save_point="workforce_proof")


def _unique(prefix):
	return f"{prefix} {frappe.generate_hash(length=8)}"


# endregion ROLLED-BACK WORKFORCE PROOF
