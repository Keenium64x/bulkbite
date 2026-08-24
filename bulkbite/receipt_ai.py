from __future__ import annotations

import re

import frappe
import requests

from bulkbite.receipt_schema import ReceiptExtraction


# =============================================================================
# region GEMINI RECEIPT EXTRACTION
# =============================================================================


_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def gemini_receipt_is_configured():
	return bool(frappe.conf.get("gemini_api_key"))


def gemini_receipt_is_approved():
	"""Require an explicit site flag before private OCR text may leave BulkBite."""
	return bool(frappe.conf.get("gemini_private_receipt_approved"))


def extract_receipt_with_gemini(raw_text):
	"""Convert local OCR text into a Pydantic-validated receipt proposal."""
	if not gemini_receipt_is_approved():
		raise PermissionError("Private receipt transmission to Gemini is not approved.")
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
			"contents": [{"parts": [{"text": _receipt_prompt(raw_text)}]}],
			"generationConfig": {
				"temperature": 0,
				"responseMimeType": "application/json",
				"responseSchema": _response_schema(),
			},
		},
		timeout=90,
	)
	if not response.ok:
		raise RuntimeError(f"Gemini receipt extraction returned HTTP {response.status_code}.")
	payload = response.json()
	parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
	text = "".join(str(part.get("text") or "") for part in parts).strip()
	if not text:
		raise RuntimeError("Gemini receipt extraction returned no structured result.")
	return ReceiptExtraction.model_validate_json(text)


def _receipt_prompt(raw_text):
	return f"""Extract this South African supplier receipt into the supplied JSON schema.

Rules:
- Use only facts supported by the OCR text. Never invent missing values.
- Keep each purchased stock line separate.
- packs_bought is the number of sale packs or cases charged on the receipt. Use 1 when only one sale pack is evidenced.
- units_per_pack is the number of inner units in each sale pack. For "6 x 200g", use 6.
- unit_size is the measurement of one inner unit. For "6 x 200g", use 200.
- purchase_uom is the unit attached to unit_size, such as g, kg, ml, l, or each.
- line_total is the full amount charged for all packs on that line.
- source_quote must reproduce the shortest exact OCR text that supports the line.
- confidence is from 0 to 1 and reflects extraction certainty for that specific line.
- notes explain useful interpretation. uncertainty states exactly what the reviewer must check.
- Use ZAR unless the receipt clearly states another currency.
- Dates must be YYYY-MM-DD when confidently recoverable, otherwise null.

OCR TEXT START
{str(raw_text)[:60000]}
OCR TEXT END"""


def _response_schema():
	line = {
		"type": "OBJECT",
		"properties": {
			"description": {"type": "STRING"},
			"packs_bought": {"type": "NUMBER"},
			"units_per_pack": {"type": "NUMBER"},
			"unit_size": {"type": "NUMBER"},
			"purchase_uom": {"type": "STRING", "nullable": True},
			"line_total": {"type": "NUMBER", "nullable": True},
			"barcode": {"type": "STRING", "nullable": True},
			"source_quote": {"type": "STRING"},
			"confidence": {"type": "NUMBER"},
			"notes": {"type": "STRING", "nullable": True},
			"uncertainty": {"type": "STRING", "nullable": True},
		},
		"required": ["description", "packs_bought", "units_per_pack", "unit_size", "source_quote", "confidence"],
	}
	return {
		"type": "OBJECT",
		"properties": {
			"supplier_name": {"type": "STRING", "nullable": True},
			"invoice_number": {"type": "STRING", "nullable": True},
			"invoice_date": {"type": "STRING", "nullable": True},
			"currency": {"type": "STRING"},
			"subtotal": {"type": "NUMBER", "nullable": True},
			"tax": {"type": "NUMBER", "nullable": True},
			"total": {"type": "NUMBER", "nullable": True},
			"lines": {"type": "ARRAY", "items": line},
			"notes": {"type": "STRING", "nullable": True},
			"confidence": {"type": "NUMBER"},
		},
		"required": ["currency", "lines", "confidence"],
	}


# endregion GEMINI RECEIPT EXTRACTION
