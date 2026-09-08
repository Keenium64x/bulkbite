import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields, validate_status


class BulkBiteOperationsImportRow(Document):
	"""Backend-owned import state and row proof."""

	def validate(self):
		require_fields(self, ["import_batch", "row_number", "row_payload", "row_status"])
		validate_status(self, "row_status")
		validate_json_fields(self, ["row_payload"])

	def on_update(self):
		pass
