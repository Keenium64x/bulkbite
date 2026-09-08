import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields, validate_status


class BulkBiteOperationsUploadBatch(Document):
	"""Backend-owned upload, extraction, review, and submission state."""

	def validate(self):
		require_fields(self, ["source_file", "status"])
		validate_status(self)
		validate_json_fields(self, ["metadata_json"])

	def on_update(self):
		pass
