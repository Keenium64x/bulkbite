from __future__ import annotations

import re

import frappe
import requests

from bulkbite.invoice_schema import CostInvoiceExtraction


# =============================================================================
# region GEMINI COST INVOICE EXTRACTION
# =============================================================================


_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
_DOCUMENT_TYPES = [
	"General Supplier Invoice", "Utilities", "Rent and Property", "Delivery and Logistics",
	"Professional Services", "Equipment and Maintenance", "Insurance and Compliance",
	"Marketing", "Telecoms and Software", "Other",
]
_COST_CATEGORIES = [
	"Labour", "Packaging", "Delivery", "Utilities", "Rent", "Kitchen Consumables",
	"Transaction Fees", "Other Production Overhead",
]


def extract_cost_invoice_with_gemini(raw_text, known_expense_types=None):
	"""Convert local OCR text into a dedicated Pydantic cost-invoice proposal."""
	if not frappe.conf.get("gemini_private_receipt_approved"):
		raise PermissionError("Private invoice transmission to Gemini is not approved.")
	api_key = frappe.conf.get("gemini_api_key")
	if not api_key or not str(raw_text or "").strip():
		return None
	model = str(frappe.conf.get("document_ai_model") or _DEFAULT_MODEL)
	if not _MODEL_PATTERN.fullmatch(model):
		raise ValueError("The configured Gemini model name is invalid.")
	response = requests.post(
		f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
		headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
		json={
			"contents": [{"parts": [{"text": _invoice_prompt(raw_text, known_expense_types or [])}]}],
			"generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": _response_schema()},
		},
		timeout=90,
	)
	if not response.ok:
		raise RuntimeError(f"Gemini invoice extraction returned HTTP {response.status_code}.")
	payload = response.json()
	parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
	text = "".join(str(part.get("text") or "") for part in parts).strip()
	if not text:
		raise RuntimeError("Gemini invoice extraction returned no structured result.")
	return CostInvoiceExtraction.model_validate_json(text)


def _invoice_prompt(raw_text, known_expense_types):
	known = ", ".join(row.get("expense_type_name") for row in known_expense_types if row.get("expense_type_name")) or "None configured"
	return f"""Extract this invoice into the supplied JSON schema for reviewed operating expenses.

Rules:
- Use only facts supported by the OCR text. Never invent missing values.
- This is not a food receipt. Each line becomes a proposed miscellaneous actual expense after human review.
- Prefer an existing expense type when its meaning fits. Existing expense types: {known}.
- If no existing type fits, propose a short reusable expense_type_name. A manager must approve its creation later.
- Choose document_type from: {', '.join(_DOCUMENT_TYPES)}.
- Choose cost_category from: {', '.join(_COST_CATEGORIES)}.
- line_amount is the amount for the expense line before document-level tax unless the invoice clearly presents tax as line-inclusive.
- quantity and unit_rate must reproduce line_amount when the invoice supports them. Otherwise use quantity 1 and unit_rate equal to line_amount.
- vat_amount is line VAT only when the invoice explicitly supports it. Document-level VAT belongs in tax.
- source_quote must contain the shortest exact OCR text supporting the line.
- confidence is from 0 to 1 for that specific line. uncertainty says what the reviewer must check.
- Dates must be YYYY-MM-DD when confidently recoverable, otherwise null.

OCR TEXT START
{str(raw_text)[:60000]}
OCR TEXT END"""


def _response_schema():
	line = {
		"type": "OBJECT",
		"properties": {
			"description": {"type": "STRING"},
			"expense_type_name": {"type": "STRING", "nullable": True},
			"cost_category": {"type": "STRING", "enum": _COST_CATEGORIES},
			"quantity": {"type": "NUMBER"},
			"unit_rate": {"type": "NUMBER", "nullable": True},
			"line_amount": {"type": "NUMBER"},
			"vat_amount": {"type": "NUMBER"},
			"accounting_category": {"type": "STRING", "nullable": True},
			"source_quote": {"type": "STRING"},
			"confidence": {"type": "NUMBER"},
			"notes": {"type": "STRING", "nullable": True},
			"uncertainty": {"type": "STRING", "nullable": True},
		},
		"required": ["description", "cost_category", "quantity", "line_amount", "vat_amount", "source_quote", "confidence"],
	}
	return {
		"type": "OBJECT",
		"properties": {
			"payee": {"type": "STRING", "nullable": True},
			"invoice_number": {"type": "STRING", "nullable": True},
			"invoice_date": {"type": "STRING", "nullable": True},
			"due_date": {"type": "STRING", "nullable": True},
			"document_type": {"type": "STRING", "enum": _DOCUMENT_TYPES},
			"currency": {"type": "STRING"},
			"subtotal": {"type": "NUMBER", "nullable": True},
			"tax": {"type": "NUMBER", "nullable": True},
			"total": {"type": "NUMBER", "nullable": True},
			"lines": {"type": "ARRAY", "items": line},
			"notes": {"type": "STRING", "nullable": True},
			"confidence": {"type": "NUMBER"},
		},
		"required": ["document_type", "currency", "lines", "confidence"],
	}


# endregion GEMINI COST INVOICE EXTRACTION
