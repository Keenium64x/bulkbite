from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils import flt, getdate, today
from frappe.utils.file_manager import save_file

from bulkbite.api import (
	apply_document_measurements,
	approve_stock_audit,
	create_document_extraction_draft,
	create_stock_count_draft,
	get_accountant_export,
	receive_stock_from_receipt,
	review_document_extraction,
	update_production_actuals,
)
from bulkbite.stock_ledger import (
	append_stock_event,
	get_stock_balance,
	rebuild_stock_balances,
	verify_stock_balances,
	verify_stock_event_chain,
)
from bulkbite.truth_ledger import append_truth_event, verify_truth_event_chain


# =============================================================================
# region ROLLED-BACK CUSTOM STOCK PROOF
# =============================================================================


def run_custom_stock_proof():
	"""Prove receipt idempotency, remaining-stock use, production posting, and audit drafts without retained data."""
	frappe.db.savepoint("bulkbite_custom_stock_proof")
	try:
		ingredient = "BB-ING-PARBOILED-RICE"
		recipe = frappe.db.get_value("BulkBite Recipe", {"status": "Approved"}, "name", order_by="name")
		supplier = _ensure_proof_supplier()
		receipt = frappe.get_doc(
			{
				"doctype": "BulkBite Receipt Intake",
				"receipt_file": "/private/files/bulkbite-proof.txt",
				"business_name": "BulkBite",
				"supplier": supplier,
				"supplier_invoice_number": "PROOF-ONCE",
				"invoice_date": getdate(),
				"currency": "ZAR",
				"default_location": "Ingredients",
				"items": [{"item_code": ingredient, "qty": 20, "rate": 70, "location": "Ingredients"}],
			}
		).insert(ignore_permissions=True)
		first_receipt = receive_stock_from_receipt(receipt.name)
		second_receipt = receive_stock_from_receipt(receipt.name)
		receipt_events = frappe.db.count(
			"BulkBite Stock Event", {"reference_doctype": receipt.doctype, "reference_name": receipt.name}
		)

		opening_events = []
		expectation = frappe.get_doc("BulkBite Recipe", recipe)
		for row in expectation.ingredients:
			if get_stock_balance(row.item_code, "Ingredients") >= flt(row.qty) / flt(expectation.nominal_output_qty):
				continue
			opening_events.append(
				append_stock_event(
					"Opening",
					row.item_code,
					"Ingredients",
					10,
					row.theory_rate,
					"BulkBite Recipe",
					recipe,
				)
			)
		run = frappe.get_doc(
			{
				"doctype": "BulkBite Production Run",
				"production_date": getdate(),
				"business_name": "BulkBite",
				"recipe": recipe,
				"planned_output_qty": 1,
				"actual_output_qty": 1,
				"source_location": "Ingredients",
				"target_location": "Finished Meals",
			}
		).insert(ignore_permissions=True)
		first_row = run.ingredients[0]
		remaining = max(flt(first_row.available_before_measurement) - 0.06, 0)
		measurements = [
			{
				"item_code": row.item_code,
				"measurement_method": "Remaining" if row.name == first_row.name else "Used",
				"remaining_qty": remaining if row.name == first_row.name else None,
				"actual_qty": row.actual_qty,
			}
			for row in run.ingredients
		]
		update_production_actuals(run.name, 1, measurements)
		run.reload().submit()
		output_balance = get_stock_balance(run.finished_item, "Finished Meals")
		proof = {
			"receipt": receipt.name,
			"receipt_first": first_receipt,
			"receipt_second": second_receipt,
			"receipt_event_count": receipt_events,
			"receipt_balance": get_stock_balance(ingredient, "Ingredients"),
			"production_run": run.name,
			"production_stock_event_count": frappe.db.count(
				"BulkBite Stock Event", {"reference_doctype": run.doctype, "reference_name": run.name}
			),
			"output_balance": output_balance,
			"truth_hash_length": len(frappe.get_cached_value("BulkBite Truth Event", run.truth_event, "event_hash") or ""),
			"first_measurement_method": run.ingredients[0].measurement_method,
			"first_actual_qty": run.ingredients[0].actual_qty,
		}
		assert receipt_events == 1
		assert first_receipt["name"] == second_receipt["name"]
		assert output_balance == 1
		assert proof["truth_hash_length"] == 64
		assert proof["first_measurement_method"] == "Remaining"
		return proof
	finally:
		frappe.db.rollback(save_point="bulkbite_custom_stock_proof")


def run_custom_workflow_proof():
	"""Prove audit approval, document review, accountant export, and balance rebuild, then roll back."""
	frappe.db.savepoint("bulkbite_custom_workflow_proof")
	physical_file = None
	try:
		item = "BB-ING-PARBOILED-RICE"
		opening = append_stock_event(
			"Opening",
			item,
			"Ingredients",
			5,
			10,
			"BulkBite Item",
			item,
		)
		audit = create_stock_count_draft(
			{
				"posting_date": today(),
				"items": [{"item_code": item, "location": "Ingredients", "qty": 4.25}],
			}
		)
		approved = approve_stock_audit(audit["name"])
		audit_doc = frappe.get_doc("BulkBite Stock Audit", audit["name"])
		reconciliation_event = audit_doc.items[0].stock_event

		file_doc = save_file(
			"bulkbite-worker-proof.txt",
			b"Parboiled Rice 3.75 kg",
			None,
			None,
			is_private=1,
		)
		physical_file = Path(frappe.get_site_path("private", "files", file_doc.file_name))
		intake = create_document_extraction_draft(
			{
				"document_type": "Stock Audit",
				"source_file": file_doc.file_url,
				"business_name": "BulkBite",
				"default_location": "Ingredients",
				"raw_text": "Parboiled Rice 3.75 kg",
			}
		)
		row = intake["rows"][0]
		row["accepted"] = 1
		reviewed = review_document_extraction(intake["name"], [row])
		applied = apply_document_measurements(reviewed["name"])
		applied_audit = frappe.get_doc("BulkBite Stock Audit", applied["name"])

		export = get_accountant_export(today(), today())
		balance_before_rebuild = get_stock_balance(item, "Ingredients")
		rebuild_stock_balances()
		balance_after_rebuild = get_stock_balance(item, "Ingredients")
		projection_check = verify_stock_balances()
		result = {
			"audit": audit_doc.name,
			"audit_docstatus": approved["docstatus"],
			"audit_stock_event": reconciliation_event,
			"reconciled_balance": balance_before_rebuild,
			"document_intake": intake["name"],
			"document_status": frappe.db.get_value("BulkBite Document Intake", intake["name"], "status"),
			"document_audit": applied_audit.name,
			"document_audit_docstatus": applied_audit.docstatus,
			"export_stock_event_count": len(export["stock_events"]),
			"export_closing_stock_count": len(export["closing_stock"]),
			"balance_after_rebuild": balance_after_rebuild,
			"projection_valid": projection_check["valid"],
			"opening_event": opening.name,
		}
		assert result["audit_docstatus"] == 1
		assert reconciliation_event
		assert result["reconciled_balance"] == 4.25
		assert result["document_status"] == "Applied"
		assert result["document_audit_docstatus"] == 0
		assert result["export_stock_event_count"] >= 2
		assert result["balance_after_rebuild"] == balance_before_rebuild
		assert result["projection_valid"]
		return result
	finally:
		frappe.db.rollback(save_point="bulkbite_custom_workflow_proof")
		if physical_file:
			physical_file.unlink(missing_ok=True)


def run_integrity_proof():
	"""Prove rejection and hash-chain controls against real custom records, then roll back."""
	frappe.db.savepoint("bulkbite_integrity_proof")
	try:
		item = "BB-ING-PARBOILED-RICE"
		event = append_stock_event("Opening", item, "Ingredients", 1, 10, "BulkBite Item", item)
		truth = append_truth_event("INTEGRITY_PROOF", "BulkBite Item", item, {"item_code": item, "quantity": 1})
		stock_edit_rejected = _operation_rejected("stock_edit", event.name)
		stock_delete_rejected = _operation_rejected("stock_delete", event.name)
		truth_edit_rejected = _operation_rejected("truth_edit", truth.name)
		balance_edit_rejected = _operation_rejected("balance_edit", frappe.db.get_value("BulkBite Stock Balance", {"item_code": item, "location": "Ingredients"}, "name"))
		frappe.db.savepoint("bulkbite_negative_stock")
		negative_stock_rejected = False
		try:
			append_stock_event("Consumption", item, "Ingredients", -2, 10, "BulkBite Item", item)
		except Exception:
			negative_stock_rejected = True
			frappe.db.rollback(save_point="bulkbite_negative_stock")
		stock_chain = verify_stock_event_chain()
		truth_chain = verify_truth_event_chain()
		projection = verify_stock_balances()
		result = {
			"stock_edit_rejected": stock_edit_rejected,
			"stock_delete_rejected": stock_delete_rejected,
			"truth_edit_rejected": truth_edit_rejected,
			"balance_edit_rejected": balance_edit_rejected,
			"negative_stock_rejected": negative_stock_rejected,
			"stock_chain_valid": stock_chain["valid"],
			"truth_chain_valid": truth_chain["valid"],
			"projection_valid": projection["valid"],
		}
		assert all(result.values())
		return result
	finally:
		frappe.db.rollback(save_point="bulkbite_integrity_proof")


def _operation_rejected(operation, name):
	frappe.db.savepoint(f"bulkbite_{operation}")
	try:
		if operation == "stock_edit":
			doc = frappe.get_doc("BulkBite Stock Event", name)
			doc.unit_cost = 99
			doc.save(ignore_permissions=True)
		elif operation == "stock_delete":
			frappe.delete_doc("BulkBite Stock Event", name, ignore_permissions=True)
		elif operation == "truth_edit":
			doc = frappe.get_doc("BulkBite Truth Event", name)
			doc.event_type = "CHANGED"
			doc.save(ignore_permissions=True)
		elif operation == "balance_edit":
			doc = frappe.get_doc("BulkBite Stock Balance", name)
			doc.actual_qty = 99
			doc.save(ignore_permissions=True)
		return False
	except Exception:
		frappe.db.rollback(save_point=f"bulkbite_{operation}")
		return True


def _ensure_proof_supplier():
	name = "BulkBite Proof Supplier"
	if not frappe.db.exists("BulkBite Supplier", name):
		frappe.get_doc({"doctype": "BulkBite Supplier", "supplier_name": name, "enabled": 1}).insert(
			ignore_permissions=True
		)
	return name


# endregion ROLLED-BACK CUSTOM STOCK PROOF
