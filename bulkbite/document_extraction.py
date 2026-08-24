from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import flt


# =============================================================================
# region PRIVATE SOURCE EVIDENCE
# =============================================================================


def resolve_private_source(file_url):
	file_doc = frappe.db.get_value(
		"File", {"file_url": file_url}, ["name", "file_name", "is_private", "owner"], as_dict=True
	)
	if not file_doc or not file_doc.is_private:
		frappe.throw(_("Upload the worker document as a private file."))
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles() and file_doc.owner != frappe.session.user:
		frappe.throw(_("You can only process private files uploaded by your account."), frappe.PermissionError)
	path = Path(frappe.get_site_path("private", "files", file_doc.file_name))
	return file_doc, path, hashlib.sha256(path.read_bytes()).hexdigest()


# endregion PRIVATE SOURCE EVIDENCE


# =============================================================================
# region TEXT TO MEASUREMENT CANDIDATES
# =============================================================================


def extract_measurement_rows(raw_text, proposed_rows=None):
	"""Parse text or schema-validated AI proposals into review candidates. Never post stock."""
	items = _item_candidates()
	if proposed_rows:
		return [_build_row(row["source_quote"], row["item_name"], row["quantity"], row["unit"], items, row) for row in proposed_rows]
	rows = []
	for source_line in str(raw_text or "").splitlines():
		line = source_line.strip()
		if not line:
			continue
		parsed = _parse_line(line)
		if not parsed:
			rows.append(_unmatched_row(line, _("No quantity and unit could be read.")))
			continue
		rows.append(_build_row(line, *parsed, items))
	return rows


def _parse_line(line):
	match = re.match(
		r"^\s*(?:[-*•]|\d+[.)])?\s*(.+?)\s*[:=,\-]?\s*(-?\d+(?:[.,]\d+)?)\s*(kg|kgs?|g|grams?|l|lt|litres?|ml|each|ea|units?|pcs?)\b.*$",
		line,
		re.IGNORECASE,
	)
	if not match:
		return None
	return match.group(1).strip(), match.group(2).replace(",", "."), match.group(3).strip()


def _normalize_quantity(qty, value):
	aliases = {
		"g": ("Kg", 0.001), "gram": ("Kg", 0.001), "grams": ("Kg", 0.001),
		"kg": ("Kg", 1), "kgs": ("Kg", 1),
		"l": ("Litre", 1), "lt": ("Litre", 1), "litre": ("Litre", 1), "litres": ("Litre", 1),
		"ml": ("Litre", 0.001), "each": ("Each", 1), "ea": ("Each", 1),
		"unit": ("Each", 1), "units": ("Each", 1), "pc": ("Each", 1), "pcs": ("Each", 1),
	}
	uom, multiplier = aliases.get(str(value).strip().lower(), (None, 1))
	return flt(qty) * multiplier, uom


def _build_row(source_line, written_name, qty, written_uom, items, evidence=None):
	match = _match_item(written_name, items)
	quantity, uom = _normalize_quantity(qty, written_uom)
	warnings = []
	if not match or match["confidence"] < 75:
		warnings.append(_("Item match needs review."))
	if not uom:
		warnings.append(_("Unit is not supported by BulkBite stock."))
	if quantity < 0:
		warnings.append(_("Quantity cannot be negative."))
	if match and uom and match["stock_uom"] != uom:
		warnings.append(_("Written unit does not match the item's stock unit."))
	if evidence and evidence.get("uncertainty"):
		warnings.append(str(evidence["uncertainty"]))
	match_confidence = match["confidence"] if match else 0
	if evidence:
		match_confidence = min(match_confidence, flt(evidence.get("confidence")) * 100)
	warning = " ".join(dict.fromkeys(warnings))
	return {
		"source_line": source_line,
		"source_page": evidence.get("source_page") if evidence else None,
		"source_quote": evidence.get("source_quote") if evidence else source_line,
		"proposed_item_name": written_name,
		"item_code": match["item_code"] if match else None,
		"qty": quantity,
		"uom": uom,
		"confidence": match_confidence,
		"warning": warning,
		"accepted": 1 if match and match_confidence >= 90 and not warning else 0,
	}


def _item_candidates():
	return frappe.get_all(
		"BulkBite Item", filters={"track_stock": 1, "enabled": 1}, fields=["item_code", "item_name", "stock_uom"]
	)


def _match_item(written_name, items):
	needle = _clean_name(written_name)
	best = None
	for item in items:
		for candidate in {item.item_code, item.item_name}:
			score = round(difflib.SequenceMatcher(None, needle, _clean_name(candidate)).ratio() * 100, 1)
			if not best or score > best["confidence"]:
				best = {"item_code": item.item_code, "stock_uom": item.stock_uom, "confidence": score}
	return best


def _clean_name(value):
	return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _unmatched_row(line, warning):
	return {"source_line": line, "source_quote": line, "proposed_item_name": line, "confidence": 0, "warning": warning, "accepted": 0}


# endregion TEXT TO MEASUREMENT CANDIDATES
