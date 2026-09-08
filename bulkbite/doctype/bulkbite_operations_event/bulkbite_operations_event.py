import frappe
from frappe.model.document import Document


class BulkBiteOperationsEvent(Document):
    """Append-only business or audit event."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Event.")

    def on_update(self):
        pass
