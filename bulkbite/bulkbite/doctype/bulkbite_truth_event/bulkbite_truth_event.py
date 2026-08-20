import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteTruthEvent(Document):
	def before_insert(self):
		if not getattr(frappe.flags, "bulkbite_truth_append", False):
			frappe.throw(_("Truth events can only be appended by a BulkBite posting workflow."))

	def before_save(self):
		if not self.is_new():
			frappe.throw(_("Truth events cannot be changed after they are recorded."))

	def on_trash(self):
		frappe.throw(_("Truth events cannot be deleted."))
