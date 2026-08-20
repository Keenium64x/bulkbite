from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime


# =============================================================================
# region STOCK JOURNAL
# =============================================================================


def append_stock_event(
	event_type,
	item_code,
	location,
	quantity_delta,
	unit_cost,
	reference_doctype,
	reference_name,
	reference_line=None,
	reversal_of=None,
):
	"""Append one immutable stock movement and update its deterministic balance projection."""
	_validate_event_input(event_type, item_code, location, quantity_delta, reference_doctype, reference_name)
	_lock_stock_chain()
	previous = _load_previous_event()
	sequence = (previous.event_sequence if previous else 0) + 1
	previous_hash = previous.event_hash if previous else ""
	posting_datetime = now_datetime()
	uom = frappe.get_cached_value("BulkBite Item", item_code, "stock_uom")
	quantity = flt(quantity_delta)
	rate = flt(unit_cost)
	payload = {
		"actor": frappe.session.user,
		"event_sequence": sequence,
		"event_type": event_type,
		"item_code": item_code,
		"location": location,
		"posting_datetime": posting_datetime,
		"quantity_delta": quantity,
		"reference_doctype": reference_doctype,
		"reference_line": reference_line or "",
		"reference_name": reference_name,
		"reversal_of": reversal_of or "",
		"unit_cost": rate,
		"uom": uom,
		"value_delta": quantity * rate,
	}
	canonical_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
	event_hash = hashlib.sha256(f"{previous_hash}|{canonical_payload}".encode()).hexdigest()

	frappe.flags.bulkbite_stock_append = True
	try:
		event = frappe.get_doc(
			{
				"doctype": "BulkBite Stock Event",
				**payload,
				"previous_hash": previous_hash,
				"event_hash": event_hash,
				"payload_json": canonical_payload,
			}
		).insert(ignore_permissions=True)
	finally:
		frappe.flags.bulkbite_stock_append = False
	_update_balance(event)
	return event


def reverse_stock_event(event_name, reference_doctype, reference_name):
	original = frappe.get_doc("BulkBite Stock Event", event_name)
	if frappe.db.exists("BulkBite Stock Event", {"reversal_of": original.name}):
		frappe.throw(_("Stock event {0} was already reversed.").format(original.name))
	return append_stock_event(
		"Reversal",
		original.item_code,
		original.location,
		-flt(original.quantity_delta),
		original.unit_cost,
		reference_doctype,
		reference_name,
		reversal_of=original.name,
	)


def _validate_event_input(event_type, item_code, location, quantity_delta, reference_doctype, reference_name):
	if event_type not in {"Opening", "Receipt", "Consumption", "Production Output", "Reconciliation", "Reversal"}:
		frappe.throw(_("Unsupported stock event type {0}.").format(event_type))
	if not frappe.db.exists("BulkBite Item", item_code):
		frappe.throw(_("BulkBite item {0} does not exist.").format(item_code))
	if not frappe.db.exists("BulkBite Location", location):
		frappe.throw(_("BulkBite location {0} does not exist.").format(location))
	if not flt(quantity_delta):
		frappe.throw(_("A stock event must change quantity."))
	if not reference_doctype or not reference_name:
		frappe.throw(_("A stock event needs a source record."))


def _lock_stock_chain():
	frappe.db.sql("select name from `tabDocType` where name = %s for update", ("BulkBite Stock Event",))


def _load_previous_event():
	row = frappe.db.get_value(
		"BulkBite Stock Event", {}, ["event_sequence", "event_hash"], order_by="event_sequence desc", as_dict=True
	)
	return frappe._dict(row) if row else None


# endregion STOCK JOURNAL


# =============================================================================
# region BALANCE PROJECTION
# =============================================================================


def get_stock_balance(item_code, location):
	if not item_code or not location:
		return 0
	return flt(frappe.db.get_value("BulkBite Stock Balance", {"item_code": item_code, "location": location}, "actual_qty"))


def get_valuation_rate(item_code, location=None):
	if location:
		rate = frappe.db.get_value(
			"BulkBite Stock Balance", {"item_code": item_code, "location": location}, "valuation_rate"
		)
		if rate is not None:
			return flt(rate)
	return flt(frappe.db.get_value("BulkBite Item", item_code, "theory_valuation_rate"))


def _update_balance(event):
	filters = {"item_code": event.item_code, "location": event.location}
	name = frappe.db.get_value("BulkBite Stock Balance", filters, "name")
	if name:
		frappe.db.sql("select name from `tabBulkBite Stock Balance` where name = %s for update", (name,))
		balance = frappe.get_doc("BulkBite Stock Balance", name)
	else:
		balance = frappe.get_doc({"doctype": "BulkBite Stock Balance", **filters, "actual_qty": 0, "stock_value": 0})

	old_qty = flt(balance.actual_qty)
	old_value = flt(balance.stock_value)
	new_qty = old_qty + flt(event.quantity_delta)
	if new_qty < -0.000001:
		frappe.throw(
			_("{0} would fall below zero at {1}. Available: {2}, movement: {3}.").format(
				event.item_code, event.location, old_qty, event.quantity_delta
			)
		)
	if event.event_type in {"Receipt", "Opening", "Production Output"} and flt(event.quantity_delta) > 0:
		new_value = old_value + flt(event.value_delta)
	elif event.event_type == "Reconciliation":
		new_value = max(new_qty, 0) * flt(event.unit_cost)
	else:
		new_value = old_value + flt(event.quantity_delta) * flt(event.unit_cost)
	if abs(new_qty) < 0.000001:
		new_qty = 0
		new_value = 0
	new_rate = new_value / new_qty if new_qty else flt(event.unit_cost)

	balance.update(
		{
			"actual_qty": new_qty,
			"uom": event.uom,
			"valuation_rate": new_rate,
			"stock_value": new_value,
			"last_event": event.name,
			"last_posting_datetime": event.posting_datetime,
		}
	)
	frappe.flags.bulkbite_balance_projection = True
	try:
		if balance.is_new():
			balance.insert(ignore_permissions=True)
		else:
			balance.save(ignore_permissions=True)
	finally:
		frappe.flags.bulkbite_balance_projection = False


def rebuild_stock_balances():
	"""Rebuild projections from immutable events. Use only for validation and repair."""
	frappe.flags.bulkbite_balance_projection = True
	try:
		for name in frappe.get_all("BulkBite Stock Balance", pluck="name"):
			frappe.delete_doc("BulkBite Stock Balance", name, ignore_permissions=True, force=True)
	finally:
		frappe.flags.bulkbite_balance_projection = False
	for event_name in frappe.get_all("BulkBite Stock Event", pluck="name", order_by="event_sequence asc"):
		_update_balance(frappe.get_doc("BulkBite Stock Event", event_name))


def verify_stock_balances():
	"""Compare stored balance projections with the sum of their immutable stock events."""
	event_rows = frappe.db.sql(
		"""
		select item_code, location, sum(quantity_delta) as event_qty
		from `tabBulkBite Stock Event`
		group by item_code, location
		""",
		as_dict=True,
	)
	event_quantities = {(row.item_code, row.location): flt(row.event_qty) for row in event_rows}
	balances = frappe.get_all("BulkBite Stock Balance", fields=["name", "item_code", "location", "actual_qty"])
	stored_quantities = {(row.item_code, row.location): flt(row.actual_qty) for row in balances}
	keys = sorted(set(event_quantities) | set(stored_quantities))
	mismatches = []
	for item_code, location in keys:
		event_qty = event_quantities.get((item_code, location), 0)
		stored_qty = stored_quantities.get((item_code, location), 0)
		if abs(event_qty - stored_qty) > 0.000001:
			mismatches.append(
				{
					"item_code": item_code,
					"location": location,
					"event_qty": event_qty,
					"stored_qty": stored_qty,
				}
			)
	return {"checked": len(keys), "mismatches": mismatches, "valid": not mismatches}


def verify_stock_event_chain():
	"""Recalculate every stock-event hash and sequence without changing stored records."""
	previous_hash = ""
	expected_sequence = 1
	errors = []
	for event in frappe.get_all(
		"BulkBite Stock Event",
		fields=["name", "event_sequence", "previous_hash", "event_hash", "payload_json"],
		order_by="event_sequence asc",
	):
		calculated_hash = hashlib.sha256(f"{previous_hash}|{event.payload_json}".encode()).hexdigest()
		if event.event_sequence != expected_sequence:
			errors.append({"event": event.name, "error": "sequence", "expected": expected_sequence, "actual": event.event_sequence})
		if (event.previous_hash or "") != previous_hash:
			errors.append({"event": event.name, "error": "previous_hash"})
		if event.event_hash != calculated_hash:
			errors.append({"event": event.name, "error": "event_hash"})
		previous_hash = event.event_hash
		expected_sequence += 1
	return {"checked": expected_sequence - 1, "errors": errors, "valid": not errors}


# endregion BALANCE PROJECTION
