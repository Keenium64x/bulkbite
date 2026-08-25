import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteCostEntry(Document):
	def before_insert(self):
		if not getattr(frappe.flags, "bulkbite_cost_entry_append", False):
			frappe.throw(_("Actual costs can only be created through a BulkBite posting workflow."))

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Posted actual costs are immutable. Record a correcting expense instead."))
		if not flt(self.amount) and flt(self.quantity) and flt(self.unit_rate):
			self.amount = round(flt(self.quantity) * flt(self.unit_rate), 2)

	def on_trash(self):
		if self.finance_event or frappe.db.exists("BulkBite Finance Event", {"cost_entry": self.name}):
			frappe.throw(_("Ledger-backed actual costs cannot be deleted. Record a correcting expense instead."))
