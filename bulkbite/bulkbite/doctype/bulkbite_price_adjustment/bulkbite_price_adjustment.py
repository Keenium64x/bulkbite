import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class BulkBitePriceAdjustment(Document):
	def validate(self):
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))
		if flt(self.value) < 0 or flt(self.threshold_amount) < 0:
			frappe.throw(_("Adjustment values cannot be negative."))
		required = {"Supplier": "supplier", "Item Category": "item_category", "Item": "item_code", "Supplier Offer": "supplier_offer"}
		if required.get(self.scope_type) and not self.get(required[self.scope_type]):
			frappe.throw(_("Choose the record this adjustment applies to."))
