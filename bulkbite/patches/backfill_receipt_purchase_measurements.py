import frappe
from frappe.utils import flt

from bulkbite.purchase_measurement import calculate_purchase_prices


def execute():
	"""Give pre-pack-model receipt lines a truthful one-pack representation."""
	rows = frappe.get_all(
		"BulkBite Receipt Line",
		filters={"purchase_qty": ["is", "not set"]},
		fields=["name", "qty", "uom", "rate", "amount"],
		limit_page_length=0,
	)
	for row in rows:
		amount = flt(row.amount) or flt(row.qty) * flt(row.rate)
		prices = calculate_purchase_prices(amount, 1, 1, row.qty)
		frappe.db.set_value(
			"BulkBite Receipt Line",
			row.name,
			{
				"purchase_qty": 1,
				"units_per_pack": 1,
				"unit_size": flt(row.qty),
				"purchase_uom": row.uom,
				"amount": amount,
				"price_per_pack": prices["price_per_pack"],
				"price_per_unit": prices["price_per_unit"],
				"rate": prices["price_per_stock_uom"],
			},
			update_modified=False,
		)
