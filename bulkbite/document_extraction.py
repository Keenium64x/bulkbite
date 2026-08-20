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
	file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name", "is_private"], as_dict=True)
	if not file_doc or not file_doc.is_private:
		frappe.throw(_("Upload the worker document as a private file."))
	path = Path(frappe.get_site_path("private", "files", file_doc.file_name))
	return file_doc, hashlib.sha256(path.read_bytes()).hexdigest()


# endregion PRIVATE SOURCE EVIDENCE


# =============================================================================
# region TEXT TO MEASUREMENT CANDIDATES
# =============================================================================


def extract_measurement_rows(raw_text):
	"""Parse OCR text into review candidates. This function never posts stock."""
	items = _item_candidates()
	rows = []
	for source_line in str(raw_text or "").splitlines():
		line = source_line.strip()
		if not line:
			continue
		parsed = _parse_line(line)
		if not parsed:
			rows.append(_unmatched_row(line, _("No quantity and unit could be read.")))
			continue
		written_name, qty, written_uom = parsed
		match = _match_item(written_name, items)
		uom = _normalize_uom(written_uom)
		warning = ""
		if not match or match["confidence"] < 75:
			warning = _("Item match needs review.")
		if uom not in {"Kg", "Litre", "Each"}:
			warning = " ".join(filter(None, [warning, _("Unit is not supported by BulkBite stock." )]))
		rows.append(
			{
				"source_line": line,
				"proposed_item_name": written_name,
				"item_code": match["item_code"] if match else None,
				"qty": flt(qty),
				"uom": uom if uom in {"Kg", "Litre", "Each"} else None,
				"confidence": match["confidence"] if match else 0,
				"warning": warning,
				"accepted": 1 if match and match["confidence"] >= 90 and not warning else 0,
			}
		)
	return rows


def _parse_line(line):
	match = re.match(r"^\s*(.+?)\s*[:=,-]?\s*(-?\d+(?:[.,]\d+)?)\s*([A-Za-z]+)\s*$", line)
	if not match:
		return None
	return match.group(1).strip(), match.group(2).replace(",", "."), match.group(3).strip()


def _normalize_uom(value):
	aliases = {"g": "Gram", "gram": "Gram", "grams": "Gram", "kg": "Kg", "kgs": "Kg", "l": "Litre", "lt": "Litre", "litre": "Litre", "litres": "Litre", "ml": "Millilitre"}
	return aliases.get(str(value).strip().lower(), str(value).strip())


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
				best = {"item_code": item.item_code, "confidence": score}
	return best


def _clean_name(value):
	return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _unmatched_row(line, warning):
	return {"source_line": line, "proposed_item_name": line, "confidence": 0, "warning": warning, "accepted": 0}


# endregion TEXT TO MEASUREMENT CANDIDATES
