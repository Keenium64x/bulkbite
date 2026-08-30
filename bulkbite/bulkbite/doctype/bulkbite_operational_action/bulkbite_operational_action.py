import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class BulkBiteOperationalAction(Document):
	def validate(self):
		if self.status == "Completed" and not self.completed_on:
			self.completed_on = getdate()
		if self.status == "Rescheduled" and not self.rescheduled_to:
			frappe.throw(_("Choose the new date for a rescheduled action."))
		if self.status == "Cancelled" and not self.cancellation_reason:
			frappe.throw(_("Enter why this action was cancelled."))
