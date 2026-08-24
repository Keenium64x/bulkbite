from __future__ import annotations

from frappe.utils import flt


# =============================================================================
# region PURCHASE MEASUREMENT
# =============================================================================


_PURCHASE_UOMS = {
	"g": ("g", "Kg", 0.001),
	"gram": ("g", "Kg", 0.001),
	"grams": ("g", "Kg", 0.001),
	"kg": ("Kg", "Kg", 1),
	"kgs": ("Kg", "Kg", 1),
	"ml": ("ml", "Litre", 0.001),
	"l": ("Litre", "Litre", 1),
	"litre": ("Litre", "Litre", 1),
	"litres": ("Litre", "Litre", 1),
	"each": ("Each", "Each", 1),
	"ea": ("Each", "Each", 1),
	"unit": ("Each", "Each", 1),
	"units": ("Each", "Each", 1),
	"pc": ("Each", "Each", 1),
	"pcs": ("Each", "Each", 1),
}


def normalize_purchase_measurement(packs_bought, units_per_pack, unit_size, purchase_uom):
	"""Convert reviewed supplier packaging into the item's stock measurement."""
	purchase_unit, stock_uom, multiplier = _PURCHASE_UOMS.get(
		str(purchase_uom or "").strip().lower(), (None, None, None)
	)
	if not stock_uom:
		return {"purchase_uom": None, "stock_qty": 0, "stock_uom": None}
	stock_qty = flt(packs_bought, 9) * flt(units_per_pack, 9) * flt(unit_size, 9) * multiplier
	return {"purchase_uom": purchase_unit, "stock_qty": stock_qty, "stock_uom": stock_uom}


def calculate_purchase_prices(line_total, packs_bought, units_per_pack, stock_qty):
	"""Return comparable prices without confusing packs, inner units, and stock units."""
	amount = flt(line_total, 9)
	packs = flt(packs_bought, 9)
	inner_units = packs * flt(units_per_pack, 9)
	quantity = flt(stock_qty, 9)
	return {
		"price_per_pack": amount / packs if packs else 0,
		"price_per_unit": amount / inner_units if inner_units else 0,
		"price_per_stock_uom": amount / quantity if quantity else 0,
	}


# endregion PURCHASE MEASUREMENT
