import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from bulkbite.purchase_measurement import calculate_purchase_prices, normalize_purchase_measurement


# =============================================================================
# region RECEIPT EVIDENCE LIFECYCLE
# =============================================================================


class BulkBiteReceiptIntake(Document):
	def validate(self):
		if self.stock_events_posted:
			persisted = frappe.db.get_value(
				self.doctype,
				self.name,
				["supplier", "supplier_invoice_number", "invoice_date", "currency", "default_location", "tax_amount"],
				as_dict=True,
			)
			if (
				self.has_value_changed("items")
				or self.has_value_changed("adjustments")
				or self.has_value_changed("evidence_files")
				or any(self.get(field) != persisted.get(field) for field in persisted or {})
			):
				frappe.throw(_("A received receipt is immutable. Create a correcting receipt or stock audit."))
		total = 0
		for row in self.items:
			self._set_legacy_purchase_measurement(row)
			if flt(row.purchase_qty) <= 0 or flt(row.units_per_pack) <= 0 or flt(row.unit_size) <= 0:
				frappe.throw(_("Packs bought, units per pack, and size per unit must be greater than zero for {0}.").format(row.item_code))
			if not frappe.get_cached_value("BulkBite Item", row.item_code, "enabled"):
				frappe.throw(_("Receipt item {0} is disabled.").format(row.item_code))
			measurement = normalize_purchase_measurement(row.purchase_qty, row.units_per_pack, row.unit_size, row.purchase_uom)
			stock_uom = frappe.get_cached_value("BulkBite Item", row.item_code, "stock_uom")
			if measurement["stock_uom"] != stock_uom:
				frappe.throw(_("Receipt unit for {0} must match its stock unit.").format(row.item_code))
			if flt(row.amount) < 0:
				frappe.throw(_("Receipt line total cannot be negative for {0}.").format(row.item_code))
			row.qty = measurement["stock_qty"]
			row.uom = stock_uom
			prices = calculate_purchase_prices(row.amount, row.purchase_qty, row.units_per_pack, row.qty)
			row.price_per_pack = prices["price_per_pack"]
			row.price_per_unit = prices["price_per_unit"]
			row.rate = prices["price_per_stock_uom"]
			total += row.amount
		self.subtotal_amount = total
		for adjustment in self.adjustments:
			if flt(adjustment.amount) < 0:
				frappe.throw(_("Receipt adjustment amounts cannot be negative."))
			adjustment.effect = "Saving" if adjustment.adjustment_type in {"Offer Discount", "Percentage Discount", "Fixed Discount", "Rebate", "Free Delivery", "Other Saving"} else "Cost"
		adjustment_total = sum((-1 if row.effect == "Saving" else 1) * flt(row.amount) for row in self.adjustments)
		self.total_amount = total + flt(self.tax_amount) + adjustment_total
		if self.items and self.status == "Draft":
			self.status = "Reviewed"

	def _set_legacy_purchase_measurement(self, row):
		"""Keep drafts created before pack fields existed valid during the migration."""
		if row.purchase_qty and row.units_per_pack and row.unit_size and row.purchase_uom:
			return
		stock_uom = frappe.get_cached_value("BulkBite Item", row.item_code, "stock_uom")
		row.purchase_qty = row.purchase_qty or 1
		row.units_per_pack = row.units_per_pack or 1
		row.unit_size = row.unit_size or row.qty or 1
		row.purchase_uom = row.purchase_uom or stock_uom
		row.amount = row.amount or flt(row.qty) * flt(row.rate)


# endregion RECEIPT EVIDENCE LIFECYCLE
