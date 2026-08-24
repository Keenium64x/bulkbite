from __future__ import annotations

import difflib
import re

import frappe
from frappe.utils import flt, getdate

from bulkbite.document_text import extract_private_text
from bulkbite.purchase_measurement import calculate_purchase_prices, normalize_purchase_measurement
from bulkbite.receipt_ai import extract_receipt_with_gemini, gemini_receipt_is_approved, gemini_receipt_is_configured
from bulkbite.receipt_schema import ReceiptExtraction, ReceiptLineExtraction


# =============================================================================
# region RECEIPT EXTRACTION AND MATCHING
# =============================================================================


def extract_receipt_review(source_path, progress=None):
	progress = progress or (lambda _stage: None)
	progress("extracting_text")
	text_result = extract_private_text(source_path)
	raw_text = text_result.get("raw_text") or ""
	progress("structuring")
	extraction, parser_mode, ai_warning = _structured_extraction(raw_text)
	progress("matching")
	rows = [_review_row(row) for row in extraction.lines]
	warnings = [text_result.get("warning")] if text_result.get("warning") else []
	if ai_warning:
		warnings.append(ai_warning)
	if not rows:
		warnings.append("No purchase lines were extracted. Add the receipt lines manually before saving.")
	supplier, supplier_score = _match_supplier(extraction.supplier_name)
	return {
		"parser_mode": parser_mode,
		"ocr_provider": text_result.get("provider"),
		"ocr_text": raw_text,
		"ocr_evidence": text_result.get("evidence"),
		"supplier": supplier,
		"proposed_supplier": extraction.supplier_name,
		"supplier_confidence": supplier_score,
		"supplier_invoice_number": extraction.invoice_number,
		"invoice_date": _safe_date(extraction.invoice_date),
		"currency": extraction.currency or "ZAR",
		"subtotal_amount": extraction.subtotal,
		"tax_amount": extraction.tax,
		"total_amount": extraction.total,
		"confidence": extraction.confidence,
		"notes": extraction.notes,
		"warnings": list(dict.fromkeys(warning for warning in warnings if warning)),
		"lines": rows,
	}


def _structured_extraction(raw_text):
	if gemini_receipt_is_configured() and gemini_receipt_is_approved() and raw_text.strip():
		try:
			return extract_receipt_with_gemini(raw_text), "Gemini structured receipt parser", None
		except Exception:
			frappe.log_error(title="BulkBite Gemini receipt extraction failed")
			warning = "Gemini could not complete this extraction. Local suggestions are shown instead."
			return _local_extraction(raw_text), "Local receipt parser", warning
	return _local_extraction(raw_text), "Local receipt parser", None


def _local_extraction(raw_text):
	lines = _parse_complete_receipt_lines(raw_text)
	lines.extend(_parse_receipt_stream(raw_text, {row.source_quote for row in lines}))
	confidence = sum(row.confidence for row in lines) / len(lines) if lines else 0.45
	return ReceiptExtraction(
		lines=lines,
		confidence=min(confidence, 0.82),
		notes="Local OCR candidates were converted to structured receipt lines and validated with Pydantic.",
	)


def _parse_complete_receipt_lines(raw_text):
	rows = []
	pattern = re.compile(
		r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*(kg|kgs?|g|grams?|l|lt|litres?|ml|each|ea|units?|pcs?)\s+(?:R\s*)?(\d+(?:[.,]\d{1,2})?)$",
		re.IGNORECASE,
	)
	for source_line in str(raw_text or "").splitlines():
		match = pattern.match(source_line.strip())
		if not match:
			continue
		rows.append(
			ReceiptLineExtraction(
				description=match.group(1),
				packs_bought=1,
				units_per_pack=1,
				unit_size=float(match.group(2).replace(",", ".")),
				purchase_uom=match.group(3),
				line_total=float(match.group(4).replace(",", ".")),
				source_quote=source_line.strip(),
				confidence=0.55,
				notes="Quantity, written unit, and line total were read from one OCR line. The rate is calculated from that line total.",
				uncertainty="Local parsing needs review.",
			)
		)
	return rows


def _parse_receipt_stream(raw_text, existing_quotes):
	"""Read OCR where product descriptions and Rand amounts alternate across one or more lines."""
	text = " ".join(str(raw_text or "").split())
	amounts = list(re.finditer(r"\bR\s*(\d+(?:[.,]\d{2}))\b", text, re.IGNORECASE))
	rows, cursor, pending_amount = [], 0, None
	for amount in amounts:
		candidate = text[cursor:amount.start()].strip(" |-:")
		pack = _pack_at_end(candidate)
		if pack:
			row = _receipt_line_from_pack(pack, amount.group(1), f"{candidate} {amount.group(0)}")
			if row.source_quote not in existing_quotes:
				rows.append(row)
				existing_quotes.add(row.source_quote)
			pending_amount = None
		else:
			pending_amount = amount.group(1)
		cursor = amount.end()
	if pending_amount:
		candidate = text[cursor:].strip(" |-:")
		pack = _pack_at_end(candidate)
		if pack:
			row = _receipt_line_from_pack(pack, pending_amount, f"R {pending_amount} {candidate}", price_precedes_item=True)
			if row.source_quote not in existing_quotes:
				rows.append(row)
	return rows


def _pack_at_end(candidate):
	pattern = re.compile(
		r"(?:\(\s*)?(?:(\d+(?:[.,]\d+)?)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*"
		r"(kg|kgs?|g|grams?|l|lt|litres?|ml|each|ea|units?|pcs?)(?:\s*\))?\s*$",
		re.IGNORECASE,
	)
	match = pattern.search(candidate)
	if not match:
		return None
	description = candidate[:match.start()].strip(" |<>()-:")
	description = re.sub(r"^\d+\s+items?\s+amount\s+", "", description, flags=re.IGNORECASE)
	if len(_clean(description)) < 3:
		return None
	return {
		"description": description,
		"pack_count": float((match.group(1) or "1").replace(",", ".")),
		"pack_size": float(match.group(2).replace(",", ".")),
		"unit": match.group(3),
		"written_pack": match.group(0).strip(),
	}


def _receipt_line_from_pack(pack, amount, source_quote, price_precedes_item=False):
	stock_quantity = pack["pack_count"] * pack["pack_size"]
	confidence = 0.72 if not price_precedes_item else 0.58
	note = f"Read {pack['written_pack']} as one purchased pack containing {pack['pack_count']:g} unit(s) of {pack['pack_size']:g} {pack['unit']}, totalling {stock_quantity:g} {pack['unit']}."
	if price_precedes_item:
		note += " The OCR placed the amount before the product, so confirm this price association."
	return ReceiptLineExtraction(
		description=pack["description"],
		packs_bought=1,
		units_per_pack=pack["pack_count"],
		unit_size=pack["pack_size"],
		purchase_uom=pack["unit"],
		line_total=float(str(amount).replace(",", ".")),
		source_quote=source_quote.strip(),
		confidence=confidence,
		notes=note,
		uncertainty="Confirm the item match, pack size, and line amount against the receipt.",
	)


def _review_row(row):
	items = frappe.get_all(
		"BulkBite Item",
		filters={"track_stock": 1, "enabled": 1},
		fields=["item_code", "item_name", "stock_uom", "scan_codes"],
	)
	match = _match_item(row, items, _prior_supplier_descriptions())
	measurement = normalize_purchase_measurement(row.packs_bought, row.units_per_pack, row.unit_size, row.purchase_uom)
	qty, uom = measurement["stock_qty"], measurement["stock_uom"]
	warnings = []
	if not match or match["confidence"] < 75:
		warnings.append("Item match needs review.")
	if not uom:
		warnings.append("Written unit needs review.")
	if match and uom and match["stock_uom"] != uom:
		warnings.append(f"Written unit converts to {uom}, but the item stocks in {match['stock_uom']}.")
	if row.uncertainty:
		warnings.append(row.uncertainty)
	line_total = flt(row.line_total)
	prices = calculate_purchase_prices(line_total, row.packs_bought, row.units_per_pack, qty)
	return {
		"item_code": match["item_code"] if match else None,
		"proposed_item_name": row.description,
		"purchase_qty": row.packs_bought,
		"units_per_pack": row.units_per_pack,
		"unit_size": row.unit_size,
		"purchase_uom": measurement["purchase_uom"] or row.purchase_uom,
		"qty": qty,
		"uom": uom,
		"rate": prices["price_per_stock_uom"],
		"price_per_pack": prices["price_per_pack"],
		"price_per_unit": prices["price_per_unit"],
		"amount": line_total,
		"source_quote": row.source_quote,
		"confidence": min(flt(row.confidence) * 100, match["confidence"] if match else 0),
		"notes": row.notes,
		"warning": " ".join(dict.fromkeys(warnings)),
	}


def _match_item(row, items, prior_descriptions=None):
	barcode = str(row.barcode or "").strip()
	if barcode:
		for item in items:
			if barcode in {value.strip() for value in str(item.scan_codes or "").splitlines() if value.strip()}:
				return {"item_code": item.item_code, "stock_uom": item.stock_uom, "confidence": 100.0}
	needle = _clean(row.description)
	needle_tokens = set(needle.split())
	best = None
	for item in items:
		candidates = {item.item_code, item.item_name}
		candidates.update((prior_descriptions or {}).get(item.item_code, set()))
		for candidate in candidates:
			clean_candidate = _clean(candidate)
			candidate_tokens = {token for token in clean_candidate.split() if token not in {"bb", "ing", "meal"}}
			sequence_score = difflib.SequenceMatcher(None, needle, clean_candidate).ratio() * 100
			candidate_coverage = 100 * len(candidate_tokens & needle_tokens) / len(candidate_tokens) if candidate_tokens else 0
			needle_coverage = 100 * len(candidate_tokens & needle_tokens) / len(needle_tokens) if needle_tokens else 0
			score = round(max(sequence_score, candidate_coverage, needle_coverage), 1)
			if not best or score > best["confidence"]:
				best = {"item_code": item.item_code, "stock_uom": item.stock_uom, "confidence": score}
	return best if best and best["confidence"] >= 58 else None


def _prior_supplier_descriptions():
	"""Reuse descriptions that a worker already reviewed against an existing item."""
	result = {}
	for row in frappe.get_all(
		"BulkBite Receipt Line",
		filters={"supplier_description": ["is", "set"]},
		fields=["item_code", "supplier_description"],
		limit_page_length=5000,
	):
		result.setdefault(row.item_code, set()).add(row.supplier_description)
	return result


def _match_supplier(value):
	if not value:
		return None, 0
	needle = _clean(value)
	best_name, best_score = None, 0
	for name in frappe.get_all("BulkBite Supplier", pluck="name"):
		score = round(difflib.SequenceMatcher(None, needle, _clean(name)).ratio() * 100, 1)
		if score > best_score:
			best_name, best_score = name, score
	return (best_name, best_score) if best_score >= 75 else (None, best_score)


def _safe_date(value):
	if not value:
		return None
	try:
		return str(getdate(value))
	except Exception:
		return None


def _clean(value):
	return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


# endregion RECEIPT EXTRACTION AND MATCHING
