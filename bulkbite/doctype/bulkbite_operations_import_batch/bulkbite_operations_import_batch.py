import frappe
from frappe.model.document import Document


class BulkBiteOperationsImportBatch(Document):
    """Backend-owned import state and row proof."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Import Batch.")

    def on_update(self):
        pass
