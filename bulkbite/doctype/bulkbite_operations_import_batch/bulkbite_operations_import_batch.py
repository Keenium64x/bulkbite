import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields, validate_status


class BulkBiteOperationsImportBatch(Document):
	"""Backend-owned import state and row proof."""

	def validate(self):
		require_fields(self, ["template", "source_file", "status"])
		validate_status(self)
		validate_json_fields(self, ["summary_json"])

	def on_update(self):
		pass
