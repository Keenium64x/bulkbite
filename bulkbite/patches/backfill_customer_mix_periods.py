import frappe
from frappe.utils import add_days, getdate

from bulkbite.customer_periods import ensure_plan_customer_periods


def execute():
	"""Freeze dated customer terms for existing directions before later plan-type edits."""
	plans = frappe.get_all(
		"BulkBite Production Plan",
		filters={"status": ["!=", "Cancelled"], "period_start": ["is", "set"]},
		pluck="name",
		order_by="period_start asc, creation asc",
	)
	for index, name in enumerate(plans):
		plan = frappe.get_doc("BulkBite Production Plan", name)
		if plan.status == "Active" and index == len(plans) - 1:
			plan.db_set("period_end", None, update_modified=False)
		elif not plan.period_end:
			next_start = frappe.db.get_value("BulkBite Production Plan", plans[index + 1], "period_start") if index + 1 < len(plans) else None
			plan.db_set("period_end", add_days(getdate(next_start), -1) if next_start else add_days(getdate(plan.period_start), 27), update_modified=False)
		ensure_plan_customer_periods(plan)
