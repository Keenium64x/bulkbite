import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteStockBalance(Document):
	def before_insert(self):
		if not frappe.flags.bulkbite_balance_projection:
			frappe.throw(_("Stock balances are maintained by the stock journal."))

	def before_save(self):
		if not frappe.flags.bulkbite_balance_projection:
			frappe.throw(_("Stock balances cannot be edited manually."))

	def on_trash(self):
		if not frappe.flags.bulkbite_balance_projection:
			frappe.throw(_("Stock balances cannot be deleted manually."))
