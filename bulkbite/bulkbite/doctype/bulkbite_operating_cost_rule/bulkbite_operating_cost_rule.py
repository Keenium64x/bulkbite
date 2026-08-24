import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class BulkBiteOperatingCostRule(Document):
	def validate(self):
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))
		if flt(self.rate) < 0 or flt(self.default_quantity) < 0:
			frappe.throw(_("Cost rates and quantities cannot be negative."))
