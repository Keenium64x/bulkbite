import frappe
from frappe.model.document import Document


class BulkBiteOperationsExtractedDraft(Document):
    """Backend-owned upload, extraction, review, and submission state."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Extracted Draft.")

    def on_update(self):
        pass
