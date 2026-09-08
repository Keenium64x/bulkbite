import frappe
from frappe.model.document import Document


class BulkBiteOperationsTask(Document):
    """Business record owned by the domain plane."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Task.")

    def on_update(self):
        pass
