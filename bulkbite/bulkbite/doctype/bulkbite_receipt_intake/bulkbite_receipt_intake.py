import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


# =============================================================================
# region RECEIPT EVIDENCE LIFECYCLE
# =============================================================================


class BulkBiteReceiptIntake(Document):
	def validate(self):
		if self.stock_events_posted and self.has_value_changed("items"):
			frappe.throw(_("Receipt lines cannot change after stock has been received."))
		total = 0
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Receipt quantity must be greater than zero for {0}.").format(row.item_code))
			row.amount = flt(row.qty) * flt(row.rate)
			total += row.amount
		self.subtotal_amount = total
		self.total_amount = total + flt(self.tax_amount)
		if self.items and self.status == "Draft":
			self.status = "Reviewed"


# endregion RECEIPT EVIDENCE LIFECYCLE
