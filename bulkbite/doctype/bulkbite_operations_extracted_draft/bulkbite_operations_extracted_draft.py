import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields


class BulkBiteOperationsExtractedDraft(Document):
	"""Backend-owned upload, extraction, review, and submission state."""

	def validate(self):
		require_fields(self, ["upload_batch", "field_values"])
		validate_json_fields(self, ["field_values", "validation_errors"])

	def on_update(self):
		pass
