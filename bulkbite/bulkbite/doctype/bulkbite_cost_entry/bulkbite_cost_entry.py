from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteCostEntry(Document):
	def validate(self):
		if not flt(self.amount) and flt(self.quantity) and flt(self.unit_rate):
			self.amount = round(flt(self.quantity) * flt(self.unit_rate), 2)
