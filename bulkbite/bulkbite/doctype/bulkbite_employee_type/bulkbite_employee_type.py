import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteEmployeeType(Document):
	def validate(self):
		if flt(self.capacity_per_worker) <= 0:
			frappe.throw(_("Capacity per worker must be greater than zero."))
		if flt(self.payment_rate) < 0:
			frappe.throw(_("Payment rate cannot be negative."))
		if self.payment_basis == "Hourly" and flt(self.expected_hours_per_run) <= 0:
			frappe.throw(_("Hourly employee types need expected hours per production run."))
