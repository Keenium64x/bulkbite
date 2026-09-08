import frappe
from frappe.model.document import Document


class BulkBiteOperationsReviewDecision(Document):
    """Backend-owned upload, extraction, review, and submission state."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Review Decision.")

    def on_update(self):
        pass
