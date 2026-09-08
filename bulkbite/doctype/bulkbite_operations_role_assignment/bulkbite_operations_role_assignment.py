import frappe
from frappe.model.document import Document


class BulkBiteOperationsRoleAssignment(Document):
    """Business record owned by the domain plane."""

    def validate(self):
        raise NotImplementedError("Implement validation for BulkBite Operations Role Assignment.")

    def on_update(self):
        pass
