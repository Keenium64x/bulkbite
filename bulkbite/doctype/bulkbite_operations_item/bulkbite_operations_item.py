import frappe
from frappe.model.document import Document


class BulkBiteOperationsItem(Document):
    """Business record owned by the domain plane."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Item.")

    def on_update(self):
        pass
