import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class BulkBiteProductionServicePeriod(Document):
	def validate(self):
		if self.status == "Intentionally Skipped" and not self.resolution_reason:
			frappe.throw(_("Enter why this service period was intentionally skipped."))
		if self.status in {"Fulfilled", "Intentionally Skipped"}:
			self.missing_output_qty = 0

	def before_save(self):
		if not self.is_new():
			frappe.throw(_("Closed production service periods cannot be changed."))

	def on_trash(self):
		if getdate(self.planned_date) < getdate(nowdate()) or self.truth_event:
			frappe.throw(_("Closed production service periods cannot be deleted."))
