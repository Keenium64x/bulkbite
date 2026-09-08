import frappe
from frappe.model.document import Document


class BulkBiteOperationsBatch(Document):
    """Business record owned by the domain plane."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Batch.")

    def on_update(self):
        pass
