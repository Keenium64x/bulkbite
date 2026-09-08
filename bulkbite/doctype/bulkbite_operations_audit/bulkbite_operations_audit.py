import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_decision


class BulkBiteOperationsAudit(Document):
	"""Business record owned by the domain plane."""

	def validate(self):
		require_fields(self, ["reference_doctype", "reference_name", "decision"])
		validate_decision(self)

	def on_update(self):
		pass
