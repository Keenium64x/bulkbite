from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime


# =============================================================================
# region TRUTH EVENT CHAIN
# =============================================================================


def calculate_event_hash(previous_hash, payload):
	canonical_payload = canonicalize_payload(payload)
	return hashlib.sha256(f"{previous_hash or ''}|{canonical_payload}".encode()).hexdigest()


def canonicalize_payload(payload):
	return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def append_truth_event(event_type, reference_doctype, reference_name, payload):
	"""Append one hash-linked event. The caller's database transaction owns commit or rollback."""
	_lock_truth_chain()
	previous = _load_previous_event()
	sequence = (previous.event_sequence if previous else 0) + 1
	previous_hash = previous.event_hash if previous else ""
	canonical_payload = canonicalize_payload(payload)
	event_hash = calculate_event_hash(previous_hash, payload)

	frappe.flags.bulkbite_truth_append = True
	try:
		event = frappe.get_doc(
			{
				"doctype": "BulkBite Truth Event",
				"event_sequence": sequence,
				"event_timestamp": now_datetime(),
				"event_type": event_type,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"actor": frappe.session.user,
				"previous_hash": previous_hash,
				"event_hash": event_hash,
				"payload_json": canonical_payload,
			}
		).insert(ignore_permissions=True)
	finally:
		frappe.flags.bulkbite_truth_append = False
	return event


def _lock_truth_chain():
	"""Serialize event appends until the current database transaction completes."""
	frappe.db.sql(
		"select name from `tabDocType` where name = %s for update",
		("BulkBite Truth Event",),
	)


def _load_previous_event():
	row = frappe.db.get_value(
		"BulkBite Truth Event",
		{},
		["event_sequence", "event_hash"],
		order_by="event_sequence desc",
		as_dict=True,
	)
	return frappe._dict(row) if row else None


def verify_truth_event_chain():
	"""Recalculate every truth-event hash and sequence without changing stored records."""
	previous_hash = ""
	expected_sequence = 1
	errors = []
	for event in frappe.get_all(
		"BulkBite Truth Event",
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


# endregion TRUTH EVENT CHAIN
