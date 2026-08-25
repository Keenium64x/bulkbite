import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


# =============================================================================
# region COST INVOICE EVIDENCE LIFECYCLE
# =============================================================================


class BulkBiteCostInvoice(Document):
	def validate(self):
		if self.costs_posted:
			persisted = frappe.db.get_value(self.doctype, self.name, ["document_type", "payee", "invoice_number", "invoice_date", "due_date", "currency", "production_plan"], as_dict=True)
			if self.has_value_changed("evidence_files") or self.has_value_changed("costs") or any(self.get(field) != persisted.get(field) for field in persisted or {}):
				frappe.throw(_("A posted cost invoice is immutable. Create a correcting cost entry or invoice."))
		if not self.evidence_files:
			frappe.throw(_("Add at least one private invoice or evidence file."))
		subtotal = 0
		for row in self.costs:
			if flt(row.quantity) < 0 or flt(row.unit_rate) < 0 or flt(row.amount) < 0 or flt(row.vat_amount) < 0:
				frappe.throw(_("Cost quantities, rates, amounts, and VAT cannot be negative."))
			if not flt(row.amount) and flt(row.quantity) and flt(row.unit_rate):
				row.amount = round(flt(row.quantity) * flt(row.unit_rate), 2)
			subtotal += flt(row.amount)
			if not row.expense_type:
				frappe.throw(_("Choose an expense type for {0}.").format(row.description))
		self.subtotal_amount = round(subtotal, 2)
		self.total_amount = round(subtotal + flt(self.tax_amount), 2)
		if self.costs and self.status == "Draft":
			self.status = "Reviewed"


# endregion COST INVOICE EVIDENCE LIFECYCLE
