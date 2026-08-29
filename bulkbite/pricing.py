from __future__ import annotations

import re

import frappe
from frappe.utils import flt, getdate, nowdate


# =============================================================================
# region OFFER IDENTITY
# =============================================================================


def supplier_offer_key(item_code, supplier, supplier_item_code=None):
	"""Return the stable logical identity used by workbook exchange."""
	parts = [item_code or "", supplier or "", supplier_item_code or "default"]
	return "::".join(re.sub(r"[^a-z0-9]+", "-", str(part).strip().lower()).strip("-") for part in parts)


# endregion OFFER IDENTITY


# =============================================================================
# region LANDED COST BRIDGE
# =============================================================================


def calculate_offer_price_bridge(offer, packs=1, on_date=None, use_offer_discount=True, basket_subtotal=None):
	"""Explain one offer's base pack price, savings, VAT, added costs, and landed cost."""
	on_date = getdate(on_date or nowdate())
	packs = max(flt(packs), 0)
	base_pack_price = flt(_value(offer, "normal_price"))
	discount_price = flt(_value(offer, "discounted_price"))
	discount_active = bool(
		use_offer_discount
		and discount_price > 0
		and _date_active(_value(offer, "discount_from"), _value(offer, "discount_to"), on_date)
	)
	base_subtotal = round(base_pack_price * packs, 2)
	components = []
	savings = 0.0
	added_costs = 0.0
	potential_costs = 0.0
	if discount_active:
		amount = round(max(base_pack_price - discount_price, 0) * packs, 2)
		if amount:
			components.append(_component("Offer discount", "Offer Discount", amount, "saving"))
			savings += amount

	adjustments = _matching_adjustments(offer, on_date, basket_subtotal or base_subtotal)
	for adjustment in adjustments:
		amount = _adjustment_amount(adjustment, base_subtotal, basket_subtotal or base_subtotal, packs)
		if not amount:
			continue
		kind = adjustment.adjustment_type
		if kind == "Free Delivery":
			potential_costs += amount
			savings += amount
			components.append(_component(adjustment.adjustment_name, kind, amount, "saving", adjustment.name))
		elif kind in {"Percentage Discount", "Fixed Discount", "Rebate", "Other Saving"}:
			savings += amount
			components.append(_component(adjustment.adjustment_name, kind, amount, "saving", adjustment.name))
		else:
			added_costs += amount
			components.append(_component(adjustment.adjustment_name, kind, amount, "cost", adjustment.name))

	net_before_vat = max(base_subtotal + potential_costs + added_costs - savings, 0)
	vat_rate = flt(_value(offer, "vat_rate"))
	vat_included = bool(_value(offer, "price_includes_vat"))
	vat_amount = round(net_before_vat * vat_rate / (100 + vat_rate), 2) if vat_included and vat_rate else round(net_before_vat * vat_rate / 100, 2)
	vat_added = 0.0 if vat_included else vat_amount
	if vat_amount:
		components.append(_component(f"VAT at {vat_rate:g}%", "VAT", vat_amount, "included" if vat_included else "cost"))
	landed_cost = round(net_before_vat + vat_added, 2)
	return {
		"base_pack_price": round(base_pack_price, 2),
		"base_subtotal": base_subtotal,
		"potential_costs": round(potential_costs, 2),
		"savings": round(savings, 2),
		"added_costs": round(added_costs, 2),
		"vat_amount": vat_amount,
		"vat_added": vat_added,
		"landed_cost": landed_cost,
		"landed_pack_price": round(landed_cost / packs, 2) if packs else 0,
		"discount_active": discount_active,
		"components": components,
	}


def calculate_basket_adjustments(supplier, basket_subtotal, on_date=None):
	"""Calculate supplier or global basket rules once for a supplier basket."""
	on_date = getdate(on_date or nowdate())
	rows = frappe.get_all(
		"BulkBite Price Adjustment",
		filters={"enabled": 1, "scope_type": ["in", ["Global", "Supplier", "Basket"]]},
		fields=["name", "adjustment_name", "adjustment_type", "calculation_basis", "value", "threshold_amount", "supplier", "effective_from", "effective_to", "priority", "stackable"],
		order_by="priority asc, name asc",
	)
	components, savings, added_costs, potential_costs = [], 0.0, 0.0, 0.0
	for row in rows:
		if row.supplier and row.supplier != supplier:
			continue
		if row.scope_type != "Basket" and row.calculation_basis != "Basket Subtotal":
			continue
		if not _date_active(row.effective_from, row.effective_to, on_date) or flt(basket_subtotal) < flt(row.threshold_amount):
			continue
		if row.adjustment_type == "Minimum Order":
			continue
		amount = _adjustment_amount(row, basket_subtotal, basket_subtotal, 1)
		if row.adjustment_type == "Free Delivery":
			potential_costs += amount
			savings += amount
			components.append(_component(row.adjustment_name, row.adjustment_type, amount, "saving", row.name))
		elif row.adjustment_type in {"Percentage Discount", "Fixed Discount", "Rebate", "Other Saving"}:
			savings += amount
			components.append(_component(row.adjustment_name, row.adjustment_type, amount, "saving", row.name))
		else:
			added_costs += amount
			components.append(_component(row.adjustment_name, row.adjustment_type, amount, "cost", row.name))
		if not row.stackable:
			break
	return {
		"potential_costs": round(potential_costs, 2),
		"savings": round(savings, 2),
		"added_costs": round(added_costs, 2),
		"net_adjustment": round(potential_costs + added_costs - savings, 2),
		"components": components,
	}


def _matching_adjustments(offer, on_date, basket_subtotal):
	item_code = _value(offer, "item_code")
	supplier = _value(offer, "supplier")
	offer_name = _value(offer, "name")
	category = frappe.get_cached_value("BulkBite Item", item_code, "item_category") if item_code else None
	rows = frappe.get_all(
		"BulkBite Price Adjustment",
		filters={"enabled": 1, "scope_type": ["not in", ["Basket"]]},
		fields=["name", "adjustment_name", "scope_type", "supplier_offer", "supplier", "item_code", "item_category", "adjustment_type", "calculation_basis", "value", "threshold_amount", "effective_from", "effective_to", "priority", "stackable"],
		order_by="priority asc, name asc",
	)
	matched = []
	for row in rows:
		if row.calculation_basis == "Basket Subtotal":
			continue
		if not _date_active(row.effective_from, row.effective_to, on_date) or flt(basket_subtotal) < flt(row.threshold_amount):
			continue
		match = (
			row.scope_type == "Global"
			or (row.scope_type == "Supplier" and row.supplier == supplier)
			or (row.scope_type == "Item Category" and row.item_category == category)
			or (row.scope_type == "Item" and row.item_code == item_code)
			or (row.scope_type == "Supplier Offer" and row.supplier_offer == offer_name)
		)
		if match:
			matched.append(row)
			if not row.stackable:
				break
	return matched


def _adjustment_amount(adjustment, pack_subtotal, basket_subtotal, packs):
	basis = adjustment.calculation_basis
	base = flt(basket_subtotal if basis == "Basket Subtotal" else pack_subtotal)
	if adjustment.adjustment_type == "Percentage Discount":
		return round(base * flt(adjustment.value) / 100, 2)
	if basis == "Pack Price":
		return round(flt(adjustment.value) * max(flt(packs), 1), 2)
	return round(flt(adjustment.value), 2)


def _component(name, component_type, amount, effect, reference=None):
	return {"name": name, "type": component_type, "amount": round(flt(amount), 2), "effect": effect, "reference": reference}


def _date_active(effective_from, effective_to, on_date):
	return (not effective_from or getdate(effective_from) <= on_date) and (not effective_to or getdate(effective_to) >= on_date)


def _value(record, fieldname):
	return record.get(fieldname) if hasattr(record, "get") else getattr(record, fieldname, None)


# endregion LANDED COST BRIDGE
