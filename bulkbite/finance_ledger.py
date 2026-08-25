from __future__ import annotations

import hashlib
import io
import json

import frappe
from frappe.utils import flt, getdate, now_datetime
from openpyxl import Workbook

from bulkbite.truth_ledger import canonicalize_payload


# =============================================================================
# region IMMUTABLE FINANCE EVENT CHAIN
# =============================================================================


def create_actual_expense(values, event_type="Actual Expense", reference_doctype=None, reference_name=None, reference_line=None, ignore_permissions=False):
	"""Create one actual cost and its finance event in the caller's transaction."""
	frappe.flags.bulkbite_cost_entry_append = True
	try:
		cost_entry = frappe.get_doc({"doctype": "BulkBite Cost Entry", **values}).insert(ignore_permissions=ignore_permissions)
	finally:
		frappe.flags.bulkbite_cost_entry_append = False
	event = append_finance_event(
		event_type,
		cost_entry,
		reference_doctype or cost_entry.doctype,
		reference_name or cost_entry.name,
		reference_line,
	)
	cost_entry.db_set("finance_event", event.name, update_modified=False)
	return cost_entry, event


def append_finance_event(event_type, cost_entry, reference_doctype, reference_name, reference_line=None):
	"""Append one accountant-facing event after an actual cost has been created."""
	_lock_finance_chain()
	previous = _load_previous_event()
	sequence = (previous.event_sequence if previous else 0) + 1
	previous_hash = previous.event_hash if previous else ""
	payload = _cost_payload(cost_entry, event_type, reference_doctype, reference_name, reference_line)
	canonical_payload = canonicalize_payload(payload)
	event_hash = hashlib.sha256(f"{previous_hash}|{canonical_payload}".encode()).hexdigest()
	frappe.flags.bulkbite_finance_append = True
	try:
		return frappe.get_doc({
			"doctype": "BulkBite Finance Event",
			"event_sequence": sequence,
			"event_timestamp": now_datetime(),
			"posting_date": cost_entry.cost_date,
			"event_type": event_type,
			"expense_type": cost_entry.expense_type,
			"cost_category": cost_entry.cost_category,
			"payee": cost_entry.payee,
			"amount": flt(cost_entry.amount),
			"vat_amount": flt(cost_entry.vat_amount),
			"currency": cost_entry.currency or "ZAR",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"reference_line": reference_line,
			"cost_entry": cost_entry.name,
			"evidence_file": cost_entry.evidence_file,
			"accounting_category": cost_entry.accounting_category,
			"actor": frappe.session.user,
			"previous_hash": previous_hash,
			"event_hash": event_hash,
			"payload_json": canonical_payload,
		}).insert(ignore_permissions=True)
	finally:
		frappe.flags.bulkbite_finance_append = False


def get_finance_ledger(from_date, to_date):
	"""Return posted finance evidence and chain status without changing records."""
	start, end = getdate(from_date), getdate(to_date)
	rows = frappe.get_all(
		"BulkBite Finance Event",
		filters={"posting_date": ["between", [start, end]]},
		fields=[
			"event_sequence", "event_timestamp", "posting_date", "event_type", "expense_type",
			"cost_category", "payee", "amount", "vat_amount", "currency", "reference_doctype",
			"reference_name", "reference_line", "cost_entry", "evidence_file", "accounting_category",
			"actor", "previous_hash", "event_hash",
		],
		order_by="event_sequence asc",
	)
	return {
		"period": {"from_date": start, "to_date": end, "currency": "ZAR"},
		"summary": {
			"entry_count": len(rows),
			"total_amount": round(sum(flt(row.amount) for row in rows), 2),
			"net_amount": round(sum(flt(row.amount) - flt(row.vat_amount) for row in rows), 2),
			"vat_amount": round(sum(flt(row.vat_amount) for row in rows), 2),
			"chain": verify_finance_event_chain(),
		},
		"rows": rows,
	}


def build_finance_ledger_workbook(from_date, to_date):
	"""Build one plain XLSX worksheet from verified immutable finance events."""
	ledger = get_finance_ledger(from_date, to_date)
	columns = [
		("event_sequence", "Event sequence"), ("event_timestamp", "Event timestamp"), ("posting_date", "Posting date"),
		("event_type", "Event type"), ("expense_type", "Expense type"), ("cost_category", "Cost category"),
		("payee", "Payee"), ("amount", "Gross amount"), ("vat_amount", "VAT amount"), ("net_amount", "Net amount"),
		("currency", "Currency"), ("accounting_category", "Accounting category"), ("reference_doctype", "Reference DocType"),
		("reference_name", "Reference name"), ("reference_line", "Reference line"), ("cost_entry", "Cost entry"),
		("evidence_file", "Evidence file"), ("actor", "Actor"), ("previous_hash", "Previous hash"), ("event_hash", "Event hash"),
	]
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Finance Ledger"
	worksheet.append([label for _, label in columns])
	for row in ledger["rows"]:
		values = dict(row)
		values["net_amount"] = round(flt(values.get("amount")) - flt(values.get("vat_amount")), 2)
		worksheet.append([values.get(fieldname) for fieldname, _ in columns])
	for column in worksheet.columns:
		worksheet.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or "")) for cell in column) + 2, 44)
	stream = io.BytesIO()
	workbook.save(stream)
	return stream.getvalue()


def verify_finance_event_chain():
	"""Recalculate every finance hash and sequence without changing stored records."""
	previous_hash = ""
	expected_sequence = 1
	errors = []
	for event in frappe.get_all(
		"BulkBite Finance Event",
		fields=[
			"name", "event_sequence", "previous_hash", "event_hash", "payload_json",
			"posting_date", "event_type", "expense_type", "cost_category", "payee", "amount",
			"vat_amount", "currency", "reference_doctype", "reference_name", "reference_line",
			"cost_entry", "evidence_file", "accounting_category",
		],
		order_by="event_sequence asc",
	):
		calculated_hash = hashlib.sha256(f"{previous_hash}|{event.payload_json}".encode()).hexdigest()
		if event.event_sequence != expected_sequence:
			errors.append({"event": event.name, "error": "sequence", "expected": expected_sequence, "actual": event.event_sequence})
		if (event.previous_hash or "") != previous_hash:
			errors.append({"event": event.name, "error": "previous_hash"})
		if event.event_hash != calculated_hash:
			errors.append({"event": event.name, "error": "event_hash"})
		errors.extend(_verify_readable_event_fields(event))
		previous_hash = event.event_hash
		expected_sequence += 1
	return {"checked": expected_sequence - 1, "errors": errors, "valid": not errors}


def _verify_readable_event_fields(event):
	"""Prove that report columns still match the signed canonical payload."""
	try:
		payload = json.loads(event.payload_json)
	except (TypeError, ValueError):
		return [{"event": event.name, "error": "payload_json"}]
	readable = {
		"posting_date": str(event.posting_date),
		"event_type": event.event_type,
		"expense_type": event.expense_type,
		"cost_category": event.cost_category,
		"payee": event.payee,
		"amount": flt(event.amount),
		"vat_amount": flt(event.vat_amount),
		"currency": event.currency,
		"reference_doctype": event.reference_doctype,
		"reference_name": event.reference_name,
		"reference_line": event.reference_line,
		"cost_entry": event.cost_entry,
		"evidence_file": event.evidence_file,
		"accounting_category": event.accounting_category,
	}
	return [
		{"event": event.name, "error": "payload_mismatch", "field": fieldname}
		for fieldname, value in readable.items()
		if not _same_payload_value(fieldname, value, payload.get(fieldname))
	]


def _same_payload_value(fieldname, readable, signed):
	if fieldname in {"amount", "vat_amount"}:
		return flt(readable) == flt(signed)
	return (readable or None) == (signed or None)


def _cost_payload(cost_entry, event_type, reference_doctype, reference_name, reference_line):
	return {
		"event_type": event_type,
		"posting_date": cost_entry.cost_date,
		"expense_type": cost_entry.expense_type,
		"cost_category": cost_entry.cost_category,
		"payee": cost_entry.payee,
		"quantity": flt(cost_entry.quantity),
		"unit_rate": flt(cost_entry.unit_rate),
		"amount": flt(cost_entry.amount),
		"vat_amount": flt(cost_entry.vat_amount),
		"currency": cost_entry.currency or "ZAR",
		"accounting_category": cost_entry.accounting_category,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"reference_line": reference_line,
		"cost_entry": cost_entry.name,
		"evidence_file": cost_entry.evidence_file,
	}


def _lock_finance_chain():
	frappe.db.sql("select name from `tabDocType` where name = %s for update", ("BulkBite Finance Event",))


def _load_previous_event():
	row = frappe.db.get_value("BulkBite Finance Event", {}, ["event_sequence", "event_hash"], order_by="event_sequence desc", as_dict=True)
	return frappe._dict(row) if row else None


# endregion IMMUTABLE FINANCE EVENT CHAIN
