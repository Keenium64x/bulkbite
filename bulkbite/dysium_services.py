from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal

import frappe

# =============================================================================
# region DYSIUM OPERATIONS SERVICES
# =============================================================================

APPROVED_DECISIONS = {"approved", "approve", "posted", "commit"}
REJECTED_DECISIONS = {"rejected", "reject", "cancelled", "blocked"}
VALID_IMPORT_STATUSES = {"preview", "valid", "invalid", "committed", "skipped", "error"}


def _require_manager():
	"""Keep generated Dysium operations behind the same backend permission boundary."""
	frappe.only_for(["System Manager"])


def _as_decimal(value):
	if value in (None, ""):
		return Decimal("0")
	return Decimal(str(value))


def _as_json(value, fallback=None):
	if value in (None, ""):
		return deepcopy(fallback)
	if isinstance(value, str):
		return json.loads(value)
	return deepcopy(value)


def _normalize_decision(value):
	return str(value or "").strip().lower()


def calculate_stock_truth(
	opening_stock=0,
	approved_receipts=0,
	approved_production_usage=0,
	physical_count=None,
	approved_count_adjustments=0,
	approved_stock_events=None,
	variance_threshold=0,
):
	"""Calculate the stock proof used by forms, reports, and backend tests."""
	closing_stock = _as_decimal(opening_stock) + _as_decimal(approved_receipts) - _as_decimal(approved_production_usage) + _as_decimal(approved_count_adjustments)
	physical = closing_stock if physical_count is None else _as_decimal(physical_count)
	reconciliation_variance = physical - closing_stock
	events = _as_json(approved_stock_events, []) or []
	export_total = sum((_as_decimal(event.get("amount") or event.get("quantity") or 0) for event in events), Decimal("0"))
	return {
		"closing_stock": float(closing_stock),
		"reconciliation_variance": float(reconciliation_variance),
		"export_total": float(export_total),
		"manager_exceptions": abs(reconciliation_variance) > _as_decimal(variance_threshold),
	}


def build_review_proposal(source, payload=None, confidence_notes=None):
	"""Return proposal state only; this never posts stock or accounting records."""
	if not source:
		frappe.throw("A source is required for review proposals.")
	return {
		"status": "proposal",
		"source": source,
		"field_values": _as_json(payload, {}) or {},
		"confidence_notes": confidence_notes or "",
		"posts_records": False,
	}


def approve_review_proposal(reference_doctype, reference_name, decision="approved", reason=None):
	"""Resolve a review decision without exposing ledger implementation to Vue."""
	if not reference_doctype or not reference_name:
		frappe.throw("A review decision requires a reference doctype and name.")
	normalized = _normalize_decision(decision)
	if normalized in APPROVED_DECISIONS:
		status = "approved"
	elif normalized in REJECTED_DECISIONS:
		status = "rejected"
	else:
		frappe.throw("Decision must approve or reject the referenced proposal.")
	return {
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"decision": status,
		"reason": reason or "",
		"posts_records": status == "approved",
	}


def validate_import_header_set(required_headers, supplied_headers):
	required = {str(header).strip() for header in _as_json(required_headers, []) if str(header).strip()}
	supplied = {str(header).strip() for header in _as_json(supplied_headers, []) if str(header).strip()}
	missing = sorted(required - supplied)
	return {"valid": not missing, "missing": missing, "required": sorted(required), "supplied": sorted(supplied)}


def preview_import_rows(rows, required_headers=None):
	rows = _as_json(rows, []) or []
	required = _as_json(required_headers, []) or []
	preview = []
	for index, row in enumerate(rows, start=1):
		header_result = validate_import_header_set(required, list(row.keys())) if required else {"valid": True, "missing": []}
		preview.append({
			"row_number": index,
			"row_payload": row,
			"row_status": "valid" if header_result["valid"] else "invalid",
			"error_message": ", ".join(header_result["missing"]),
		})
	return {"rows": preview, "committed": False}


def summarize_import_commit(rows):
	rows = _as_json(rows, []) or []
	counts = {"created": 0, "skipped": 0, "errors": 0}
	for row in rows:
		status = str(row.get("row_status") or row.get("status") or "valid").lower()
		if status == "valid":
			counts["created"] += 1
		elif status == "skipped":
			counts["skipped"] += 1
		else:
			counts["errors"] += 1
	return counts


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_query_service(**kwargs):
	"""Return a compact operations snapshot for generated Dysium route views."""
	_require_manager()
	stock = calculate_stock_truth(**(kwargs.get("stock") or {}))
	return {
		"status": "ready",
		"workflow": ["review-today", "complete-workflow", "manage-exceptions", "maintain-system"],
		"stock": stock,
	}


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_command_service(**kwargs):
	"""Run deterministic command calculations without letting Vue own business rules."""
	_require_manager()
	action = str(kwargs.get("action") or "calculate-stock-truth")
	if action != "calculate-stock-truth":
		frappe.throw(f"Unsupported Dysium command: {action}")
	return {"action": action, "result": calculate_stock_truth(**(kwargs.get("stock") or kwargs))}


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_permission_service(**kwargs):
	"""Expose the backend permission decision used by generated routes."""
	_require_manager()
	return {
		"user": kwargs.get("user") or getattr(frappe.session, "user", None),
		"allowed": True,
		"roles": ["System Manager"],
	}


@frappe.whitelist(allow_guest=False)
def mobile_refresh_service(**kwargs):
	"""Return the smallest refresh payload required by the mobile shell."""
	_require_manager()
	return {"status": "ready", "refresh": "delta", "payload": bulkbite_operations_query_service(**kwargs)}


@frappe.whitelist(allow_guest=False)
def audit_event_service(**kwargs):
	"""Prepare an explicit audit event payload for the backend event ledger."""
	_require_manager()
	event_type = kwargs.get("event_type") or "dysium-operation"
	subject = kwargs.get("subject") or "bulkbite-operations"
	return {"event_type": event_type, "subject": subject, "payload": _as_json(kwargs.get("payload"), {}) or {}}


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_upload_intake_service(**kwargs):
	"""Create upload proposal state without posting records."""
	_require_manager()
	return build_review_proposal(kwargs.get("source") or kwargs.get("file_url") or "upload", kwargs.get("payload"), kwargs.get("confidence_notes"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_ai_extraction_proposal_service(**kwargs):
	"""Normalize AI extraction output as a reviewable proposal."""
	_require_manager()
	return build_review_proposal(kwargs.get("source") or "ai-extraction", kwargs.get("field_values") or kwargs.get("payload"), kwargs.get("confidence_notes"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_review_decision_service(**kwargs):
	"""Approve or reject a proposal through one deterministic decision contract."""
	_require_manager()
	return approve_review_proposal(kwargs.get("reference_doctype"), kwargs.get("reference_name"), kwargs.get("decision"), kwargs.get("reason"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_deterministic_submit_service(**kwargs):
	"""Submit only after approval, then return stock-proof output for the caller."""
	_require_manager()
	decision = approve_review_proposal(kwargs.get("reference_doctype"), kwargs.get("reference_name"), kwargs.get("decision", "approved"), kwargs.get("reason"))
	if not decision["posts_records"]:
		frappe.throw("Only approved proposals can be submitted.")
	return {"decision": decision, "stock": calculate_stock_truth(**(kwargs.get("stock") or {}))}


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_import_template_service(**kwargs):
	"""Validate the import template header contract."""
	_require_manager()
	return validate_import_header_set(kwargs.get("required_headers"), kwargs.get("supplied_headers"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_workbook_validation_service(**kwargs):
	"""Validate workbook rows without committing records."""
	_require_manager()
	return preview_import_rows(kwargs.get("rows"), kwargs.get("required_headers"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_import_preview_service(**kwargs):
	"""Preview structured import rows; preview never writes business records."""
	_require_manager()
	return preview_import_rows(kwargs.get("rows"), kwargs.get("required_headers"))


@frappe.whitelist(allow_guest=False)
def bulkbite_operations_import_commit_service(**kwargs):
	"""Return deterministic import commit counts from validated preview rows."""
	_require_manager()
	return summarize_import_commit(kwargs.get("rows"))


# endregion DYSIUM OPERATIONS SERVICES
