import frappe

from bulkbite.planning import freeze_buying_theory


def execute():
	frappe.db.sql(
		"""
		update `tabBulkBite Supplier Offer`
		set effective_from = coalesce(effective_from, date(creation))
		where effective_from is null
		"""
	)
	for name in frappe.get_all(
		"BulkBite Production Plan",
		filters={"buying_snapshot_json": ["is", "not set"], "status": ["!=", "Cancelled"]},
		pluck="name",
	):
		freeze_buying_theory(frappe.get_doc("BulkBite Production Plan", name))
