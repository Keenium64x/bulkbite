import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from bulkbite.stock_ledger import append_stock_event, get_stock_balance


class BulkBiteStockAudit(Document):
	def validate(self):
		if self.docstatus == 0 and not self.stock_events_posted:
			for row in self.items:
				row.expected_qty = get_stock_balance(row.item_code, row.location)
				row.uom = frappe.get_cached_value("BulkBite Item", row.item_code, "stock_uom")
				row.valuation_rate = frappe.get_cached_value("BulkBite Item", row.item_code, "theory_valuation_rate") or 0
				row.variance_qty = flt(row.counted_qty) - flt(row.expected_qty)

	def on_submit(self):
		if self.stock_events_posted:
			frappe.throw(_("This audit was already posted."))
		for row in self.items:
			if not row.variance_qty:
				continue
			event = append_stock_event("Reconciliation", row.item_code, row.location, row.variance_qty, row.valuation_rate, self.doctype, self.name, row.name)
			row.db_set("stock_event", event.name, update_modified=False)
		self.db_set("stock_events_posted", 1, update_modified=False)

	def on_cancel(self):
		frappe.throw(_("Posted audits remain immutable. Create a new audit to correct stock."))
