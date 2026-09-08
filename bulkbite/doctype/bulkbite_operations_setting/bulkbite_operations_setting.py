import frappe
from frappe.model.document import Document


class BulkBiteOperationsSetting(Document):
    """Project-level configuration and defaults."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Setting.")

    def on_update(self):
        pass
