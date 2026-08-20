import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteRecipe(Document):
	def validate(self):
		if flt(self.nominal_output_qty) <= 0:
			frappe.throw(_("Recipe output must be greater than zero."))
		if not self.ingredients:
			frappe.throw(_("A recipe needs at least one controlled ingredient."))
		seen = set()
		for row in self.ingredients:
			if row.item_code in seen:
				frappe.throw(_("Ingredient {0} occurs more than once in this recipe.").format(row.item_code))
			seen.add(row.item_code)
			if flt(row.qty) <= 0:
				frappe.throw(_("Ingredient quantities must be greater than zero."))
