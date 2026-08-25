import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteExpenseType(Document):
	def validate(self):
		if self.expense_type_name:
			self.expense_type_name = " ".join(self.expense_type_name.split())
		duplicate = frappe.db.exists("BulkBite Expense Type", {"expense_type_name": self.expense_type_name, "name": ("!=", self.name)})
		if duplicate:
			frappe.throw(_("Expense type {0} already exists.").format(self.expense_type_name))
