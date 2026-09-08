import frappe
from frappe.model.document import Document
from bulkbite.dysium_validation import require_fields, validate_status


class BulkBiteOperationsTask(Document):
	"""Business record owned by the domain plane."""

	def validate(self):
		require_fields(self, ["title"])
		validate_status(self)

	def on_update(self):
		pass
