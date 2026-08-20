import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


# =============================================================================
# region DOCUMENT REVIEW LIFECYCLE
# =============================================================================


class BulkBiteDocumentIntake(Document):
	def validate(self):
		if self.status == "Applied" and self.has_value_changed("rows"):
			frappe.throw(_("Applied document measurements cannot be changed."))
		if self.document_type in {"Usage Sheet", "Remaining Stock Sheet"} and not self.production_run:
			frappe.throw(_("Select the production run that this worker sheet belongs to."))
		for row in self.rows:
			if row.accepted and (not row.item_code or not row.uom or flt(row.qty) < 0):
				frappe.throw(_("Every accepted row needs an item, unit, and non-negative quantity."))


# endregion DOCUMENT REVIEW LIFECYCLE
