import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from bulkbite.pricing import supplier_offer_key

from bulkbite.purchase_measurement import normalize_purchase_measurement


class BulkBiteSupplierOffer(Document):
	def validate(self):
		if self.effective_from and self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Price Until cannot be before Price From."))
		self._preserve_price_history()
		if flt(self.units_per_pack) <= 0 or flt(self.unit_size) <= 0:
			frappe.throw(_("Units per pack and size per unit must be greater than zero."))
		measurement = normalize_purchase_measurement(1, self.units_per_pack, self.unit_size, self.purchase_uom)
		stock_uom = frappe.get_cached_value("BulkBite Item", self.item_code, "stock_uom")
		if measurement["stock_uom"] != stock_uom:
			frappe.throw(_("Offer pack unit must convert to the item's stock unit."))
		self.stock_qty_per_pack = measurement["stock_qty"]
		self.offer_key = supplier_offer_key(self.item_code, self.supplier, self.supplier_item_code)
		if flt(self.normal_price) < 0 or flt(self.discounted_price) < 0:
			frappe.throw(_("Offer prices cannot be negative."))
		if flt(self.vat_rate) < 0:
			frappe.throw(_("VAT rate cannot be negative."))

	def _preserve_price_history(self):
		if self.is_new():
			return
		price_fields = {
			"item_code", "supplier", "units_per_pack", "unit_size", "purchase_uom",
			"normal_price", "discounted_price", "discount_from", "discount_to", "effective_from",
			"price_includes_vat", "vat_rate",
		}
		if any(self.has_value_changed(field) for field in price_fields):
			frappe.throw(_("Supplier price history is append-only. Create a new supplier offer for the changed pack or price, then close this record with Price Until."))
