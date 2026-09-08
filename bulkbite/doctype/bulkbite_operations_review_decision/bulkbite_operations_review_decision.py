import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_decision


class BulkBiteOperationsReviewDecision(Document):
	"""Backend-owned upload, extraction, review, and submission state."""

	def validate(self):
		require_fields(self, ["reference_doctype", "reference_name", "decision"])
		validate_decision(self)

	def on_update(self):
		pass
