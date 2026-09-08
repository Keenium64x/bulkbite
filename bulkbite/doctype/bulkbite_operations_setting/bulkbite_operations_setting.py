import frappe
from frappe.model.document import Document


class BulkBiteOperationsSetting(Document):
	"""Project-level configuration and defaults."""

	def validate(self):
		pass

	def on_update(self):
		pass
