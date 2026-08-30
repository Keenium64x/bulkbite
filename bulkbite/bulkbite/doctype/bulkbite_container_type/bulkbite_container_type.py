import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteContainerType(Document):
	def validate(self):
		self._validate_stock_identity()
		self._validate_default_for_production()

	def _validate_stock_identity(self):
		if not self.stock_item:
			frappe.throw(_("Choose the Packaging item that represents this container in Stock."))
		item_type, stock_uom = frappe.get_cached_value(
			"BulkBite Item",
			self.stock_item,
			["item_type", "stock_uom"],
		)
		if item_type != "Packaging" or stock_uom != "Each":
			frappe.throw(_("Container stock items must be Packaging items measured in Each."))

	def _validate_default_for_production(self):
		if not self.default_for_production:
			return
		if not self.enabled:
			frappe.throw(_("The default production container must be enabled."))
		other_default = frappe.db.exists(
			"BulkBite Container Type",
			{
				"name": ["!=", self.name],
				"enabled": 1,
				"default_for_production": 1,
			},
		)
		if other_default:
			frappe.throw(_("{0} is already the default production container.").format(other_default))
