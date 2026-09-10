import frappe
from frappe.utils import getdate, nowdate


def execute():
	for period in frappe.get_all(
		"BulkBite Production Service Period",
		filters={"status": "Intentionally Skipped", "planned_date": [">=", nowdate()]},
		fields=["name", "production_plan", "planned_date", "resolution_reason"],
	):
		if frappe.db.exists("BulkBite Planning Vacation", {"legacy_service_period": period.name}):
			continue
		frappe.get_doc({
			"doctype": "BulkBite Planning Vacation",
			"vacation_name": period.resolution_reason or "Planned closure",
			"production_plan": period.production_plan,
			"from_date": getdate(period.planned_date),
			"to_date": getdate(period.planned_date),
			"status": "Active",
			"legacy_service_period": period.name,
		}).insert(ignore_permissions=True)
