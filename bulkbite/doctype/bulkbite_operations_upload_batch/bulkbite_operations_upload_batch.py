import frappe
from frappe.model.document import Document


class BulkBiteOperationsUploadBatch(Document):
    """Backend-owned upload, extraction, review, and submission state."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Upload Batch.")

    def on_update(self):
        pass
