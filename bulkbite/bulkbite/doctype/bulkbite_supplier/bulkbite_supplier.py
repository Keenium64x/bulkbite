import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class BulkBiteSupplier(Document):
	def validate(self):
		if cint(self.delivery_lead_time_days) < 0 or cint(self.order_safety_days) < 0:
			frappe.throw(_("Supplier lead time and safety days cannot be negative."))
