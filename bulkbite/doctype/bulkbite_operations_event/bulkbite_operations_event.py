import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_json_fields


class BulkBiteOperationsEvent(Document):
	"""Append-only business or audit event."""

	def validate(self):
		require_fields(self, ["event_type", "subject"])
		validate_json_fields(self, ["payload"])

	def on_update(self):
		pass
