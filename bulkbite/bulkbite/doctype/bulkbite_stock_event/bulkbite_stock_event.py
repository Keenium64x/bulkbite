import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteStockEvent(Document):
	def before_insert(self):
		if not frappe.flags.bulkbite_stock_append:
			frappe.throw(_("Stock events can only be created by the BulkBite stock journal."))

	def before_save(self):
		if not self.is_new():
			frappe.throw(_("Posted stock events are immutable. Record a reversal instead."))

	def on_trash(self):
		frappe.throw(_("Posted stock events cannot be deleted. Record a reversal instead."))
