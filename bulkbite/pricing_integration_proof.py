from __future__ import annotations

from io import BytesIO
from pathlib import Path

import frappe
from openpyxl import load_workbook

from bulkbite.api import receive_stock_from_receipt
from bulkbite.planning import build_spend_report
from bulkbite.price_workbook import apply_price_workbook, build_price_workbook, preview_price_workbook
from bulkbite.pricing import calculate_offer_price_bridge


# =============================================================================
# region PRICING AND WORKBOOK PROOF
# =============================================================================


def run_pricing_integration_proof():
	"""Prove price versioning, savings detail, workbook review, and the stock boundary."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("bulkbite_price_proof")
	file_path = None
	try:
		item = _ensure_proof_item()
		supplier = _ensure_proof_supplier()
		offer = frappe.get_doc({
			"doctype": "BulkBite Supplier Offer", "item_code": item.name, "supplier": supplier.name,
			"supplier_item_code": "PROOF-PACK", "effective_from": "2026-08-01", "units_per_pack": 6,
			"unit_size": 200, "purchase_uom": "g", "normal_price": 120, "currency": "ZAR",
			"price_includes_vat": 1, "vat_rate": 15, "enabled": 1,
		}).insert()
		frappe.get_doc({
			"doctype": "BulkBite Price Adjustment", "adjustment_code": "PROOF-FREE-DELIVERY",
			"adjustment_name": "Proof free delivery", "scope_type": "Supplier Offer", "supplier_offer": offer.name,
			"adjustment_type": "Free Delivery", "calculation_basis": "Fixed", "value": 35,
			"effective_from": "2026-08-01", "enabled": 1,
		}).insert()
		bridge = calculate_offer_price_bridge(offer, 2, "2026-08-24")
		assert bridge["savings"] == 35
		assert any(row["type"] == "Free Delivery" for row in bridge["components"])

		workbook = load_workbook(BytesIO(build_price_workbook()))
		sheet = workbook["Items and Current Prices"]
		headers = {cell.value: cell.column for cell in sheet[1]}
		for row_number in range(2, sheet.max_row + 1):
			if sheet.cell(row_number, headers["offer_id"]).value == offer.name:
				sheet.cell(row_number, headers["normal_pack_price"]).value = 135
				sheet.cell(row_number, headers["effective_from"]).value = "2026-08-25"
				break
		stream = BytesIO()
		workbook.save(stream)
		file_doc = frappe.get_doc({"doctype": "File", "file_name": "bulkbite-price-proof.xlsx", "is_private": 1, "content": stream.getvalue()}).insert()
		file_path = Path(file_doc.get_full_path())
		stock_before = frappe.db.count("BulkBite Stock Event")
		preview = preview_price_workbook(file_doc.file_url)
		assert preview["counts"]["update"] >= 1
		if preview["counts"]["error"]:
			raise AssertionError([row for row in preview["rows"] if row["status"] == "error"])
		applied = apply_price_workbook(preview["name"])
		assert applied["status"] == "Applied"
		assert frappe.db.count("BulkBite Stock Event") == stock_before
		old = frappe.get_doc(offer.doctype, offer.name)
		assert not old.enabled and str(old.effective_to) == "2026-08-24"
		new_offer = frappe.get_all(offer.doctype, filters={"item_code": item.name, "supplier": supplier.name, "normal_price": 135, "enabled": 1}, pluck="name")
		assert len(new_offer) == 1
		return {"passed": True, "preview_counts": preview["counts"], "stock_events_unchanged": True, "old_offer": old.name, "new_offer": new_offer[0], "free_delivery_saving": bridge["savings"]}
	finally:
		frappe.db.rollback(save_point="bulkbite_price_proof")
		if file_path and file_path.exists():
			file_path.unlink()


def run_receipt_adjustment_integration_proof():
	"""Prove receipt totals, report allocation, stock posting, and adjustment immutability."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("bulkbite_receipt_adjustment_proof")
	try:
		item = _ensure_proof_item()
		supplier = _ensure_proof_supplier()
		receipt = frappe.get_doc(
			{
				"doctype": "BulkBite Receipt Intake",
				"receipt_file": "/private/files/bulkbite-receipt-adjustment-proof.txt",
				"business_name": "BulkBite",
				"supplier": supplier.name,
				"supplier_invoice_number": "PROOF-ADJUSTMENTS",
				"invoice_date": "2099-12-31",
				"currency": "ZAR",
				"default_location": "Ingredients",
				"items": [
					{
						"item_code": item.name,
						"purchase_qty": 1,
						"units_per_pack": 1,
						"unit_size": 1,
						"purchase_uom": "Kg",
						"amount": 120,
						"location": "Ingredients",
					}
				],
				"adjustments": [
					{"adjustment_type": "Free Delivery", "description": "Proof free delivery", "amount": 35},
					{"adjustment_type": "Delivery Fee", "description": "Proof urgent delivery", "amount": 10},
				],
			}
		).insert(ignore_permissions=True)
		assert receipt.total_amount == 95

		report = build_spend_report("2099-12-31", "2099-12-31")
		assert report["summary"]["actual_spend"] == 95
		assert _actual_breakdown_amount(report, "Receipt savings") == -35
		assert _actual_breakdown_amount(report, "Delivery and buying costs") == 10
		free_delivery = next(row for row in report["savings"] if row["name"] == "Proof free delivery")
		assert free_delivery["expected_amount"] == 0 and free_delivery["actual_amount"] == 35
		free_delivery_type = next(row for row in report["savings_by_type"] if row["type"] == "Free Delivery")
		assert free_delivery_type["actual_amount"] == 35

		stock_before = frappe.db.count("BulkBite Stock Event")
		receive_stock_from_receipt(receipt.name)
		assert frappe.db.count("BulkBite Stock Event") == stock_before + 1
		posted_receipt = frappe.get_doc(receipt.doctype, receipt.name)
		posted_receipt.adjustments[0].amount = 36
		immutable = False
		try:
			posted_receipt.save(ignore_permissions=True)
		except frappe.ValidationError:
			immutable = True
		assert immutable
		return {
			"passed": True,
			"receipt_total": receipt.total_amount,
			"free_delivery_saving": free_delivery["actual_amount"],
			"delivery_cost": _actual_breakdown_amount(report, "Delivery and buying costs"),
			"adjustments_immutable_after_stock": immutable,
		}
	finally:
		frappe.db.rollback(save_point="bulkbite_receipt_adjustment_proof")


def _actual_breakdown_amount(report, category):
	return round(sum(row["actual_spend"] for row in report["breakdown"] if row["item_category"] == category), 2)


def _ensure_proof_item():
	name = "BB-PRICE-PROOF"
	if frappe.db.exists("BulkBite Item", name):
		return frappe.get_doc("BulkBite Item", name)
	return frappe.get_doc({"doctype": "BulkBite Item", "item_code": name, "item_name": "Price Proof Ingredient", "item_type": "Ingredient", "stock_uom": "Kg", "track_stock": 1, "purchasable": 1, "enabled": 1}).insert()


def _ensure_proof_supplier():
	name = "Price Proof Supplier"
	if frappe.db.exists("BulkBite Supplier", name):
		return frappe.get_doc("BulkBite Supplier", name)
	return frappe.get_doc({"doctype": "BulkBite Supplier", "supplier_name": name, "enabled": 1}).insert()


# endregion PRICING AND WORKBOOK PROOF
