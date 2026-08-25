from __future__ import annotations

import re

import frappe
from frappe.utils import flt, getdate

from bulkbite.document_text import extract_private_text
from bulkbite.invoice_ai import extract_cost_invoice_with_gemini
from bulkbite.invoice_schema import CostInvoiceExtraction, CostInvoiceLineExtraction


# =============================================================================
# region COST INVOICE EXTRACTION AND MATCHING
# =============================================================================


def extract_cost_invoice_review(source_paths, progress=None):
	"""Extract all invoice pages once and return editable, expense-type-aware review rows."""
	progress = progress or (lambda _stage: None)
	progress("extracting_text")
	text_results = [extract_private_text(path) for path in source_paths]
	raw_text = "\n\n".join(f"FILE {index + 1}\n{result.get('raw_text') or ''}" for index, result in enumerate(text_results))
	progress("structuring")
	extraction, parser_mode, warning = _structured_invoice(raw_text)
	progress("matching_expense_types")
	expense_types = _expense_types()
	lines = [_review_line(row, expense_types) for row in extraction.lines]
	warnings = [result.get("warning") for result in text_results if result.get("warning")]
	if warning:
		warnings.append(warning)
	if not lines:
		warnings.append("No expense lines were extracted. Add one miscellaneous expense line manually before saving.")
	return {
		"parser_mode": parser_mode,
		"ocr_provider": ", ".join(dict.fromkeys(result.get("provider") for result in text_results if result.get("provider"))),
		"ocr_text": raw_text,
		"ocr_evidence": [result.get("evidence") for result in text_results],
		"payee": extraction.payee,
		"invoice_number": extraction.invoice_number,
		"invoice_date": _safe_date(extraction.invoice_date),
		"due_date": _safe_date(extraction.due_date),
		"document_type": extraction.document_type,
		"currency": extraction.currency or "ZAR",
		"subtotal_amount": extraction.subtotal,
		"tax_amount": extraction.tax,
		"total_amount": extraction.total,
		"confidence": extraction.confidence,
		"notes": extraction.notes,
		"warnings": list(dict.fromkeys(value for value in warnings if value)),
		"cost_lines": lines,
	}


def _structured_invoice(raw_text):
	if frappe.conf.get("gemini_api_key") and frappe.conf.get("gemini_private_receipt_approved") and raw_text.strip():
		try:
			return extract_cost_invoice_with_gemini(raw_text, _expense_types()), "Gemini structured invoice parser", None
		except Exception:
			frappe.log_error(title="BulkBite Gemini invoice extraction failed")
			return _local_invoice(raw_text), "Local invoice parser", "Gemini could not complete this extraction. Local suggestions are shown instead."
	return _local_invoice(raw_text), "Local invoice parser", None


def _local_invoice(raw_text):
	amounts = [float(value.replace(",", ".")) for value in re.findall(r"(?:R\s*)?(\d+[.,]\d{2})", str(raw_text or ""), re.IGNORECASE)]
	lines = []
	if amounts:
		amount = amounts[-1]
		lines.append(CostInvoiceLineExtraction(
			description="Invoice total requiring review", expense_type_name="General operating expense",
			quantity=1, unit_rate=amount, line_amount=amount, source_quote=f"R {amount:.2f}", confidence=0.35,
			notes="The local parser found an amount but could not safely separate invoice lines.",
			uncertainty="Confirm the payee, invoice type, VAT, total, and expense description.",
		))
	return CostInvoiceExtraction(lines=lines, total=amounts[-1] if amounts else None, confidence=0.35, notes="Local invoice OCR was validated with Pydantic.")


def _expense_types():
	return frappe.get_all(
		"BulkBite Expense Type", filters={"enabled": 1},
		fields=["name", "expense_type_name", "cost_category", "document_type", "default_vat_treatment", "accounting_category"],
		order_by="expense_type_name",
	)


def _review_line(line, expense_types):
	match, score = _match_expense_type(line.expense_type_name or line.description, expense_types)
	quantity = flt(line.quantity) or 1
	amount = round(flt(line.line_amount), 2)
	unit_rate = round(flt(line.unit_rate) or (amount / quantity if quantity else amount), 2)
	return {
		"description": line.description,
		"expense_type": match.name if match else None,
		"proposed_expense_type": line.expense_type_name or line.description,
		"create_expense_type": 0,
		"cost_rule": None,
		"cost_category": match.cost_category if match else line.cost_category,
		"quantity": quantity,
		"unit_rate": unit_rate,
		"amount": amount,
		"vat_amount": round(flt(line.vat_amount), 2),
		"accounting_category": match.accounting_category if match and match.accounting_category else line.accounting_category,
		"confidence": round(min(flt(line.confidence) * 100, score if match else flt(line.confidence) * 100), 1),
		"source_quote": line.source_quote,
		"notes": line.notes,
		"uncertainty": line.uncertainty or (None if match else "Choose an existing expense type or approve the proposed new type."),
	}


def _match_expense_type(description, expense_types):
	needle = _tokens(description)
	best, score = None, 0
	for expense_type in expense_types:
		candidate = _tokens(expense_type.expense_type_name)
		current = len(needle & candidate) / len(candidate) if candidate else 0
		if current > score:
			best, score = expense_type, current
	return (best, round(score * 100, 1)) if score >= 0.5 else (None, 0)


def _tokens(value):
	return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 2}


def _safe_date(value):
	if not value:
		return None
	try:
		return str(getdate(value))
	except Exception:
		return None


# endregion COST INVOICE EXTRACTION AND MATCHING
