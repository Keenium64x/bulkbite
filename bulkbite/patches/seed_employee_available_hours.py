import frappe
from frappe.utils import flt


def execute():
	"""Give existing production employees an explicit per-run availability baseline."""
	default_hours = {
		row.name: flt(row.expected_hours_per_run)
		for row in frappe.get_all("BulkBite Employee Type", fields=["name", "expected_hours_per_run"])
	}
	for employee in frappe.get_all(
		"BulkBite Employee",
		filters={"available_for_production": 1, "available_hours_per_run": ("<=", 0)},
		fields=["name", "employee_type"],
	):
		frappe.db.set_value(
			"BulkBite Employee",
			employee.name,
			"available_hours_per_run",
			default_hours.get(employee.employee_type, 0),
			update_modified=False,
		)
