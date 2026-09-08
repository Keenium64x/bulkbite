from __future__ import annotations

import json

import frappe

# =============================================================================
# region DYSIUM DOCTYPE VALIDATION
# =============================================================================

VALID_STATUSES = {"draft", "open", "in review", "approved", "posted", "committed", "skipped", "error", "closed"}
VALID_DECISIONS = {"approved", "rejected"}


def _has_value(value):
	return value not in (None, "")


def require_fields(doc, fields):
	for field in fields:
		if not _has_value(getattr(doc, field, None)):
			frappe.throw(f"{doc.doctype or doc.__class__.__name__}: {field} is required.")


def validate_json_fields(doc, fields):
	for field in fields:
		value = getattr(doc, field, None)
		if not _has_value(value) or isinstance(value, (dict, list)):
			continue
		if isinstance(value, str):
			json.loads(value)
			continue
		frappe.throw(f"{doc.doctype or doc.__class__.__name__}: {field} must be JSON.")


def validate_status(doc, field="status", allowed=VALID_STATUSES):
	value = getattr(doc, field, None)
	if _has_value(value) and str(value).strip().lower() not in allowed:
		frappe.throw(f"{doc.doctype or doc.__class__.__name__}: {field} is invalid.")


def validate_decision(doc):
	value = getattr(doc, "decision", None)
	if _has_value(value) and str(value).strip().lower() not in VALID_DECISIONS:
		frappe.throw(f"{doc.doctype or doc.__class__.__name__}: decision must be approved or rejected.")


# endregion DYSIUM DOCTYPE VALIDATION
