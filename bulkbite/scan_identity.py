from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, unquote, urlparse

import frappe
from frappe import _


# =============================================================================
# region SCAN CODE NORMALIZATION
# =============================================================================


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_INTERNAL_QR_PREFIXES = ("bulkbite:item:", "bb:item:")


def normalize_scan_code(value):
	"""Return one stable product identity without stripping meaningful zeroes."""
	raw = _CONTROL_CHARACTERS.sub("", str(value or "")).strip()
	if not raw:
		frappe.throw(_("Scan or enter a QR code or barcode."))
	if len(raw) > 500:
		frappe.throw(_("The scanned value is too long to be a product code."))
	return _structured_item_code(raw) or raw


def item_scan_codes(item):
	return {
		normalize_scan_code(line)
		for line in str(item.scan_codes or "").splitlines()
		if _CONTROL_CHARACTERS.sub("", line).strip()
	}


def find_scan_owner(code, exclude_item=None):
	normalized = normalize_scan_code(code)
	for item in frappe.get_all("BulkBite Item", fields=["item_code", "scan_codes", "enabled"]):
		if item.item_code == exclude_item:
			continue
		if normalized == item.item_code or normalized in item_scan_codes(item):
			return item
	return None


def validate_item_scan_codes(item):
	written_codes = [line for line in str(item.scan_codes or "").splitlines() if line.strip()]
	codes = list(item_scan_codes(item))
	if len(codes) != len(written_codes):
		frappe.throw(_("Scan codes must be unique within the item."))
	for code in codes:
		owner = find_scan_owner(code, exclude_item=item.name or item.item_code)
		if owner:
			frappe.throw(_("Scan code {0} is already assigned to item {1}.").format(code, owner.item_code))
	item.scan_codes = "\n".join(sorted(codes))


def _structured_item_code(raw):
	lower = raw.lower()
	for prefix in _INTERNAL_QR_PREFIXES:
		if lower.startswith(prefix):
			return unquote(raw[len(prefix) :]).strip()
	if raw.startswith("{"):
		try:
			payload = json.loads(raw)
		except (TypeError, ValueError):
			return None
		if str(payload.get("type") or "").lower() in {"bulkbite-item", "bulkbite:item"}:
			return str(payload.get("item_code") or "").strip() or None
	try:
		parsed = urlparse(raw)
	except ValueError:
		return None
	if parsed.scheme not in {"http", "https"}:
		return None
	host = (parsed.hostname or "").lower()
	if host not in {"bulkbite.co.za", "www.bulkbite.co.za", "bulkbite.localhost"}:
		return None
	query = parse_qs(parsed.query)
	if query.get("item"):
		return str(query["item"][0]).strip()
	match = re.search(r"/(?:stock/)?item/([^/?#]+)", parsed.path, re.IGNORECASE)
	return unquote(match.group(1)).strip() if match else None


# endregion SCAN CODE NORMALIZATION
