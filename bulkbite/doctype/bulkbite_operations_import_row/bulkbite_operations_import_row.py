import frappe
from frappe.model.document import Document


class BulkBiteOperationsImportRow(Document):
    """Backend-owned import state and row proof."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Import Row.")

    def on_update(self):
        pass
