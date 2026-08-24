from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils import flt, getdate, today
from frappe.utils.file_manager import save_file

from bulkbite.api import (
	_next_production_station,
	apply_document_measurements,
	approve_stock_audit,
	create_run_from_plan,
	create_document_extraction_draft,
	process_receipt_extraction_job,
	create_stock_count_draft,
	discard_production_run,
	get_accountant_export,
	get_production_plan_snapshot,
	get_purchase_price_history,
	receive_stock_from_receipt,
	review_document_extraction,
	save_monthly_production_plan,
	submit_production_run,
	update_production_actuals,
	cancel_production_plan,
)
from bulkbite.stock_ledger import (
	append_stock_event,
	get_stock_balance,
	rebuild_stock_balances,
	verify_stock_balances,
	verify_stock_event_chain,
)
from bulkbite.planning import calculate_customer_demand
from bulkbite.truth_ledger import append_truth_event, verify_truth_event_chain


# =============================================================================
# region ROLLED-BACK CUSTOM STOCK PROOF
# =============================================================================


def run_planning_math_proof():
	"""Prove the public-plan customer calculation used by monthly production planning."""
	mix = [
		frappe._dict({"plan_type": "Lite", "customer_count": 10}),
		frappe._dict({"plan_type": "Full", "customer_count": 30}),
	]
	demand = calculate_customer_demand(mix)
	assert demand["total_customers"] == 40
	assert demand["weekly_servings"] == 560
	assert demand["weekly_output_qty"] == 294
	assert demand["mix"][0]["weekly_output_qty"] == 42
	assert demand["mix"][1]["weekly_output_qty"] == 252
	return {**demand, "four_week_output_qty": demand["weekly_output_qty"] * 4}


def run_planned_production_draft_proof():
	"""Prove rolling selection, clean quantities, resumable drafts, and explicit discard."""
	frappe.db.savepoint("bulkbite_planned_production_draft_proof")
	try:
		snapshot = get_production_plan_snapshot(location="Ingredients")
		station = snapshot["next_production"]
		assert station["state"] in {"ready", "draft"}
		row = station["row"]
		assert any(item["available_qty"] > 0 for item in row["ingredients"])
		first = create_run_from_plan(snapshot["name"], row["name"], today(), "Ingredients", "Finished Meals")
		second = create_run_from_plan(snapshot["name"], row["name"], today(), "Ingredients", "Finished Meals")
		assert first["name"] == second["name"]
		assert first["docstatus"] == 0
		assert not _contains_float_tail(first)
		original_expected = [item["expected_qty"] for item in first["ingredients"]]
		updated_customer_mix = [dict(item) for item in snapshot["customer_mix"]]
		updated_customer_mix[0]["customer_count"] += 1
		routes_by_category = {item["item_category"]: dict(item) for item in snapshot["purchase_routes"]}
		fallback_supplier = next(iter(routes_by_category.values()))["supplier"]
		for category in frappe.get_all("BulkBite Item Category", filters={"enabled": 1}, fields=["name", "default_supplier"]):
			routes_by_category.setdefault(
				category.name,
				{
					"item_category": category.name,
					"supplier": category.default_supplier or fallback_supplier,
					"use_discounted_price": False,
				},
			)
		updated = save_monthly_production_plan(
			{
				"name": snapshot["name"],
				"plan_title": snapshot["plan_title"],
				"customer_mix": updated_customer_mix,
				"purchase_routes": list(routes_by_category.values()),
				"plan_rows": snapshot["rows"],
				"location": snapshot["location"],
			}
		)
		frozen_draft = frappe.get_doc("BulkBite Production Run", first["name"])
		assert [round(flt(item.expected_qty), 3) for item in frozen_draft.ingredients] == original_expected
		assert updated["customer_demand"]["total_customers"] == snapshot["customer_demand"]["total_customers"] + 1

		discarded = discard_production_run(first["name"])
		assert discarded["discarded"]
		assert not frappe.db.exists("BulkBite Production Run", first["name"])
		cancelled = cancel_production_plan(snapshot["name"])
		assert cancelled["deleted"]
		assert not frappe.db.exists("BulkBite Production Plan", snapshot["name"])

		cycle = _next_production_station(
			snapshot["rows"],
			[
				frappe._dict(
					{
						"name": "posted-week-four",
						"production_plan_row": snapshot["rows"][3]["name"],
						"plan_week_number": 4,
						"cycle_number": 2,
						"production_date": getdate(),
						"creation": "2026-08-24 12:00:00",
						"docstatus": 1,
					}
				)
			],
		)
		assert cycle["row"]["week_number"] == 1
		assert cycle["cycle_number"] == 3
		return {
			"plan": snapshot["name"],
			"week": row["week_number"],
			"run": first["name"],
			"resumed_run": second["name"],
			"discarded": discarded["discarded"],
			"direction_update_kept_draft_theory": True,
			"unused_direction_deleted": cancelled["deleted"],
			"wrapped_to_week": cycle["row"]["week_number"],
			"next_cycle": cycle["cycle_number"],
			"available_items": sum(1 for item in row["ingredients"] if item["available_qty"] > 0),
		}
	finally:
		frappe.db.rollback(save_point="bulkbite_planned_production_draft_proof")


def _contains_float_tail(value):
	"""Return whether serialized operational data exposes more than three decimals."""
	if isinstance(value, dict):
		quantity_fields = {
			"planned_output_qty",
			"actual_output_qty",
			"output_variance_qty",
			"expected_qty",
			"actual_qty",
			"remaining_qty",
			"available_before_measurement",
			"variance_qty",
		}
		return any(
			_contains_float_tail(item) if field in quantity_fields else _contains_float_tail(item) if isinstance(item, (dict, list)) else False
			for field, item in value.items()
		)
	if isinstance(value, list):
		return any(_contains_float_tail(item) for item in value)
	if isinstance(value, float):
		return len(f"{value:.12f}".rstrip("0").partition(".")[2]) > 3
	return False


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
				"items": [{
					"item_code": ingredient,
					"purchase_qty": 2,
					"units_per_pack": 1,
					"unit_size": 10,
					"purchase_uom": "Kg",
					"amount": 1400,
					"location": "Ingredients",
				}],
			}
		).insert(ignore_permissions=True)
		assert receipt.items[0].qty == 20
		assert receipt.items[0].rate == 70
		assert receipt.items[0].price_per_pack == 700
		first_receipt = receive_stock_from_receipt(receipt.name)
		second_receipt = receive_stock_from_receipt(receipt.name)
		price_history = get_purchase_price_history(item_code=ingredient, supplier=supplier)
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
		first_production = submit_production_run(run.name)
		second_production = submit_production_run(run.name)
		run.reload()
		output_balance = get_stock_balance(run.finished_item, "Finished Meals")
		proof = {
			"receipt": receipt.name,
			"receipt_first": first_receipt,
			"receipt_second": second_receipt,
			"receipt_event_count": receipt_events,
			"receipt_balance": get_stock_balance(ingredient, "Ingredients"),
			"receipt_price_history": next(row for row in price_history["rows"] if row["reference"] == receipt.name),
			"production_run": run.name,
			"production_first": first_production,
			"production_second": second_production,
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
		assert proof["receipt_price_history"]["stock_unit_price"] == 70
		assert first_production["output_stock_event"] == second_production["output_stock_event"]
		assert proof["production_stock_event_count"] == len(run.ingredients) + 1
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


def run_receipt_extraction_proof():
	"""Prove private receipt upload to editable suggestions without retaining a file or receipt."""
	frappe.db.savepoint("bulkbite_receipt_extraction_proof")
	physical_file = None
	try:
		ocr_text = (
			"6 Items Amount Tastic Long Grain Parboiled White Rice 10kg R 134.95 bat "
			"Rhodes Tomato And Onion Mix (6 x 410g) R 114.00 Knorrox Beef Stock Cubes 24 x 10g R 28.95 "
			"PO| tel F Robertsons Rajah Curry Powder Med Rajah (1 x 800g) R 167.95 "
			"Excella Sunflower Oil 2L R 72.95 R 36.20 <0 All Gold Tomato Puree 410g"
		)
		file_doc = save_file(
			"bulkbite-receipt-proof.txt",
			ocr_text.encode(),
			None,
			None,
			is_private=1,
		)
		physical_file = Path(frappe.get_site_path("private", "files", file_doc.file_name))
		result = process_receipt_extraction_job(file_doc.file_url)
		proof = {
			"private_file": file_doc.file_url.startswith("/private/files/"),
			"parser_mode": result["parser_mode"],
			"line_count": len(result["lines"]),
			"first_item": result["lines"][0]["item_code"],
			"quantities": [round(row["qty"], 3) for row in result["lines"]],
			"purchase_shapes": [
				[row["purchase_qty"], row["units_per_pack"], row["unit_size"], row["purchase_uom"]]
				for row in result["lines"]
			],
			"items": [row["item_code"] for row in result["lines"]],
			"confidence_present": all(row["confidence"] > 0 for row in result["lines"]),
			"ocr_text_present": result["ocr_text"] == ocr_text,
			"stock_event_count": frappe.db.count("BulkBite Stock Event"),
		}
		assert proof["private_file"]
		assert proof["line_count"] == 6
		assert proof["first_item"] == "BB-ING-PARBOILED-RICE"
		assert proof["quantities"] == [10, 2.46, 0.24, 0.8, 2, 0.41]
		assert proof["purchase_shapes"][1] == [1, 6, 410, "g"]
		assert proof["items"] == [
			"BB-ING-PARBOILED-RICE",
			"BB-ING-TOMATO-ONION-MIX",
			"BB-ING-STOCK-CUBES",
			"BB-ING-CURRY-POWDER",
			"BB-ING-SUNFLOWER-OIL",
			"BB-ING-TOMATO-PUREE",
		]
		assert proof["confidence_present"]
		assert proof["ocr_text_present"]
		return proof
	finally:
		frappe.db.rollback(save_point="bulkbite_receipt_extraction_proof")
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
			append_stock_event(
				"Consumption",
				item,
				"Ingredients",
				-(get_stock_balance(item, "Ingredients") + 1),
				10,
				"BulkBite Item",
				item,
			)
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
