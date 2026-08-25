import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteEmployee(Document):
	def validate(self):
		if self.end_date and self.start_date and self.end_date < self.start_date:
			frappe.throw(_("End date cannot be before start date."))
		if self.use_payment_override and flt(self.payment_rate_override) < 0:
			frappe.throw(_("Payment override cannot be negative."))
		if self.status != "Active":
			self.available_for_production = 0
