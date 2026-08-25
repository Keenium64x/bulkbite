import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteFinanceEvent(Document):
	def before_insert(self):
		if not getattr(frappe.flags, "bulkbite_finance_append", False):
			frappe.throw(_("Finance events can only be appended by a BulkBite posting workflow."))

	def before_save(self):
		if not self.is_new():
			frappe.throw(_("Finance events cannot be changed after they are recorded."))

	def on_trash(self):
		frappe.throw(_("Finance events cannot be deleted. Record a correcting expense instead."))
