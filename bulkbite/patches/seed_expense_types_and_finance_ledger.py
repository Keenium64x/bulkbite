import frappe

from bulkbite.finance_ledger import append_finance_event


DEFAULT_EXPENSE_TYPES = [
	("Production labour", "Labour", "Other", "No VAT"),
	("Electricity and utilities", "Utilities", "Utilities", "Inclusive"),
	("Rent and property", "Rent", "Rent and Property", "Inclusive"),
	("Delivery and logistics", "Delivery", "Delivery and Logistics", "Inclusive"),
	("Packaging", "Packaging", "General Supplier Invoice", "Inclusive"),
	("Kitchen consumables", "Kitchen Consumables", "General Supplier Invoice", "Inclusive"),
	("Bank and transaction fees", "Transaction Fees", "Professional Services", "No VAT"),
	("General operating expense", "Other Production Overhead", "General Supplier Invoice", "Inclusive"),
]


def execute():
	for name, category, document_type, vat_treatment in DEFAULT_EXPENSE_TYPES:
		if not frappe.db.exists("BulkBite Expense Type", {"expense_type_name": name}):
			frappe.get_doc({
				"doctype": "BulkBite Expense Type", "expense_type_name": name, "cost_category": category,
				"document_type": document_type, "default_vat_treatment": vat_treatment, "enabled": 1,
			}).insert(ignore_permissions=True)
	default_by_category = {
		row.cost_category: row.name for row in frappe.get_all("BulkBite Expense Type", fields=["name", "cost_category"], order_by="name")
	}
	for entry in frappe.get_all("BulkBite Cost Entry", fields=["name", "cost_category", "production_run", "finance_event"], order_by="cost_date asc, creation asc"):
		doc = frappe.get_doc("BulkBite Cost Entry", entry.name)
		if not doc.expense_type:
			doc.db_set("expense_type", default_by_category.get(doc.cost_category) or default_by_category.get("Other Production Overhead"), update_modified=False)
		if not doc.finance_event and not frappe.db.exists("BulkBite Finance Event", {"cost_entry": doc.name}):
			reference_doctype = "BulkBite Production Run" if doc.production_run else doc.doctype
			reference_name = doc.production_run or doc.name
			event = append_finance_event("Actual Expense", doc.reload(), reference_doctype, reference_name)
			doc.db_set("finance_event", event.name, update_modified=False)
