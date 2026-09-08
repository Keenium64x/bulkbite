import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields


class BulkBiteOperationsImportTemplate(Document):
	"""Backend-owned import state and row proof."""

	def validate(self):
		require_fields(self, ["template_name", "target_doctype", "required_headers"])
		validate_json_fields(self, ["required_headers"])

	def on_update(self):
		pass
