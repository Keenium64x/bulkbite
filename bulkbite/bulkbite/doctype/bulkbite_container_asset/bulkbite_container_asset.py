import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteContainerAsset(Document):
	def validate(self):
		if self.lifecycle_state == "With Customer" and not self.current_customer_reference:
			frappe.throw(_("Enter the customer reference for a container held by a customer."))
