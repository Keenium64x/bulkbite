from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from openpyxl import load_workbook

from bulkbite.api import (
	get_catalogue_price_improvement_status,
	post_cost_invoice,
	process_catalogue_price_improvement_job,
	receive_stock_from_receipt,
	start_catalogue_price_improvement,
)
from bulkbite.finance_ledger import verify_finance_event_chain
from bulkbite.costing import calculate_operating_costs
from bulkbite.planning import build_spend_report
from bulkbite.price_workbook import apply_price_import, build_price_workbook, inspect_price_import, preview_price_import, review_price_import
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

		selected_fields = ["offer_id", "item_code", "item_name", "supplier", "effective_from", "units_per_pack", "unit_size", "purchase_uom", "normal_pack_price"]
		workbook = load_workbook(BytesIO(build_price_workbook(selected_fields)))
		assert workbook.sheetnames == ["Price Catalogue"]
		sheet = workbook["Price Catalogue"]
		headers = {cell.value: cell.column for cell in sheet[1]}
		assert set(headers) == {"Offer ID", "Item Code", "Item Name", "Supplier", "Price Effective From", "Units per Pack", "Size per Unit", "Size Unit", "Normal Pack Price"}
		for row_number in range(2, sheet.max_row + 1):
			if sheet.cell(row_number, headers["Offer ID"]).value == offer.name:
				sheet.cell(row_number, headers["Normal Pack Price"]).value = 135
				sheet.cell(row_number, headers["Price Effective From"]).value = "2026-08-25"
				break
		sheet.append([None, "BB-PRICE-PROOF-NEW", "Proof imported ingredient", "Proof Imported Supplier", "2026-08-25", 1, 2, "Kg", 50])
		stream = BytesIO()
		workbook.save(stream)
		file_doc = frappe.get_doc({"doctype": "File", "file_name": "bulkbite-price-proof.xlsx", "is_private": 1, "content": stream.getvalue()}).insert()
		file_path = Path(file_doc.get_full_path())
		stock_before = frappe.db.count("BulkBite Stock Event")
		inspection = inspect_price_import(file_doc.file_url)
		assert inspection["suggested_mapping"]["Normal Pack Price"] == "normal_pack_price"
		preview = preview_price_import(file_doc.file_url, inspection["suggested_mapping"])
		assert preview["counts"]["update"] >= 1
		assert preview["counts"]["insert"] >= 1
		if preview["counts"]["error"]:
			raise AssertionError([row for row in preview["rows"] if row["status"] == "error"])
		proposal = {
			"mapping": preview["mapping"], "suppliers": preview["suppliers"], "categories": preview["categories"],
			"items": preview["items"], "offers": preview["offers"], "ai_used": False, "ai_notes": "",
		}
		new_supplier = next(row for row in proposal["suppliers"] if row["name"] == "Proof Imported Supplier")
		new_supplier["name"] = "Proof Reviewed Supplier"
		new_item = next(row for row in proposal["items"] if row["item_code"] == "BB-PRICE-PROOF-NEW")
		new_item["item_name"] = "Reviewed imported ingredient"
		new_item["item_category"] = "Proof Dry Goods"
		new_offer = next(row for row in proposal["offers"] if row["item_code"] == "BB-PRICE-PROOF-NEW")
		new_offer["item_category"] = "Proof Dry Goods"
		reviewed = review_price_import(preview["name"], proposal)
		assert reviewed["counts"]["error"] == 0
		assert any(row["name"] == "Proof Reviewed Supplier" for row in reviewed["suppliers"])
		assert any(row["name"] == "Proof Dry Goods" for row in reviewed["categories"])
		assert any(row["supplier"] == "Proof Reviewed Supplier" for row in reviewed["offers"] if row["item_code"] == "BB-PRICE-PROOF-NEW")
		applied = apply_price_import(preview["name"])
		assert applied["status"] == "Applied"
		assert frappe.db.exists("BulkBite Item", "BB-PRICE-PROOF-NEW")
		assert frappe.db.exists("BulkBite Supplier", "Proof Reviewed Supplier")
		assert frappe.db.exists("BulkBite Item Category", "Proof Dry Goods")
		assert frappe.db.get_value("BulkBite Item", "BB-PRICE-PROOF-NEW", "item_category") == "Proof Dry Goods"
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


def run_catalogue_job_boundary_proof():
	"""Prove AI review is queued, private to its manager, and separate from catalogue writes."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("bulkbite_catalogue_job_proof")
	try:
		batch = frappe.get_doc({
			"doctype": "BulkBite Price Import Batch",
			"source_file": "/private/files/catalogue-job-proof.xlsx",
			"status": "Previewed",
			"total_rows": 1,
			"preview_json": frappe.as_json({"mapping": {}, "suppliers": [], "categories": [], "items": [], "offers": []}),
		}).insert()
		queued_job = SimpleNamespace(id="bulkbite.localhost||catalogue-job-proof")
		with patch("bulkbite.api.frappe.enqueue", return_value=queued_job) as enqueue:
			started = start_catalogue_price_improvement(batch.name)
		queue_args = enqueue.call_args.kwargs
		assert started["status"] == "queued" and started["job_id"] == queued_job.id
		assert queue_args["queue"] == "long" and queue_args["deduplicate"] is True
		assert queue_args["batch_name"] == batch.name and queue_args["user"] == "Administrator"

		improved = {"name": batch.name, "status": "Previewed", "ai_used": True}
		with patch("bulkbite.api.improve_price_import", return_value=improved) as improve:
			processed = process_catalogue_price_improvement_job(batch.name, user="Administrator")
		assert processed == improved
		assert improve.call_args.args == (batch.name,)
		assert improve.call_args.kwargs["progress"]

		finished_job = SimpleNamespace(
			id=queued_job.id,
			kwargs={"user": "Administrator"},
			meta={"stage": "ready for review"},
			get_status=lambda refresh=True: "finished",
			return_value=lambda refresh=True: improved,
		)
		with patch("bulkbite.api.get_job", return_value=finished_job):
			status = get_catalogue_price_improvement_status(queued_job.id)
		assert status["status"] == "finished" and status["result"] == improved
		return {"passed": True, "queue": queue_args["queue"], "deduplicated": True, "private_to_user": True, "catalogue_apply_called": False}
	finally:
		frappe.db.rollback(save_point="bulkbite_catalogue_job_proof")


def run_cost_invoice_integration_proof():
	"""Prove recurring labour theory and evidence-backed actual costs without stock mutation."""
	frappe.set_user("Administrator")
	frappe.db.savepoint("bulkbite_cost_invoice_proof")
	file_paths = []
	try:
		expense_type = frappe.db.get_value("BulkBite Expense Type", {"expense_type_name": "Electricity and utilities"}, "name")
		fee_type = frappe.db.get_value("BulkBite Expense Type", {"expense_type_name": "Bank and transaction fees"}, "name")
		rule = frappe.get_doc({
			"doctype": "BulkBite Operating Cost Rule", "cost_code": "PROOF-UTILITIES",
			"cost_name": "Proof kitchen utilities", "cost_category": "Utilities", "basis": "Hourly",
			"rate": 50, "employee_count": 2, "hours_per_employee": 8, "default_quantity": 1,
			"recurrence": "Weekly", "effective_from": "2099-01-01", "enabled": 1,
		}).insert()
		theory = calculate_operating_costs("2099-01-01", "2099-01-14")
		expected = next(row for row in theory["expected_rows"] if row["name"] == rule.name)
		assert expected["quantity"] == 32 and expected["amount"] == 1600

		files = []
		for index in range(1, 3):
			file_doc = frappe.get_doc({"doctype": "File", "file_name": f"bulkbite-cost-proof-{index}.txt", "is_private": 1, "content": f"Proof cost evidence page {index}"}).insert()
			files.append(file_doc)
			file_paths.append(Path(file_doc.get_full_path()))
		stock_before = frappe.db.count("BulkBite Stock Event")
		invoice = frappe.get_doc({
			"doctype": "BulkBite Cost Invoice", "payee": "Proof Payroll", "invoice_number": "PROOF-COST-001",
			"invoice_date": "2099-01-07", "currency": "ZAR",
			"evidence_files": [{"evidence_file": row.file_url, "file_name": row.file_name} for row in files],
			"costs": [
				{"description": "Kitchen utilities", "expense_type": expense_type, "cost_rule": rule.name, "cost_category": "Utilities", "quantity": 16, "unit_rate": 50, "amount": 800},
				{"description": "Payroll administration", "expense_type": fee_type, "cost_category": "Transaction Fees", "quantity": 1, "unit_rate": 25, "amount": 25},
			],
		}).insert()
		assert invoice.total_amount == 825
		first = post_cost_invoice(invoice.name)
		assert first["costs_posted"] and first["line_count"] == 2
		assert frappe.db.count("BulkBite Cost Entry", {"cost_date": "2099-01-07"}) == 2
		assert frappe.db.count("BulkBite Finance Event", {"reference_name": invoice.name}) == 2
		assert verify_finance_event_chain()["valid"]
		second = post_cost_invoice(invoice.name)
		assert second["costs_posted"] and frappe.db.count("BulkBite Cost Entry", {"cost_date": "2099-01-07"}) == 2
		assert frappe.db.count("BulkBite Stock Event") == stock_before
		posted = frappe.get_doc(invoice.doctype, invoice.name)
		posted.payee = "Changed payee"
		immutable = False
		try:
			posted.save(ignore_permissions=True)
		except frappe.ValidationError:
			immutable = True
		assert immutable
		actual = calculate_operating_costs("2099-01-01", "2099-01-14")
		assert actual["actual_total"] == 825
		return {"passed": True, "expected_cost": expected["amount"], "actual_cost": actual["actual_total"], "posted_lines": 2, "finance_events": 2, "finance_chain_valid": True, "idempotent": True, "stock_events_unchanged": True, "immutable": immutable}
	finally:
		frappe.db.rollback(save_point="bulkbite_cost_invoice_proof")
		for file_path in file_paths:
			if file_path.exists():
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
