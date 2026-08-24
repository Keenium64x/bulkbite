from frappe.model.document import Document

from bulkbite.scan_identity import validate_item_scan_codes


class BulkBiteItem(Document):
	def validate(self):
		validate_item_scan_codes(self)
