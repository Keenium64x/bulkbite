from __future__ import annotations

import re

import frappe
import requests

from bulkbite.price_import_schema import AIPriceImportSuggestions


# =============================================================================
# region GEMINI PRICE CATALOGUE SUGGESTIONS
# =============================================================================


_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def improve_price_proposal_with_gemini(rows, known_records):
	"""Suggest ambiguous catalogue identities and pack facts without writing records."""
	if not frappe.conf.get("gemini_private_receipt_approved"):
		raise PermissionError("Private spreadsheet transmission to Gemini is not approved.")
	api_key = frappe.conf.get("gemini_api_key")
	if not api_key:
		raise RuntimeError("Gemini is not configured for this site.")
	model = str(frappe.conf.get("document_ai_model") or _DEFAULT_MODEL)
	if not _MODEL_PATTERN.fullmatch(model):
		raise ValueError("The configured Gemini model name is invalid.")
	prompt = _prompt(rows, known_records)
	response = requests.post(
		f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
		headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
		json={
			"contents": [{"parts": [{"text": prompt}]}],
			"generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": _response_schema()},
		},
		timeout=90,
	)
	if not response.ok:
		raise RuntimeError(f"Gemini price catalogue review returned HTTP {response.status_code}.")
	parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
	text = "".join(str(part.get("text") or "") for part in parts).strip()
	if not text:
		raise RuntimeError("Gemini returned no price catalogue suggestions.")
	return AIPriceImportSuggestions.model_validate_json(text)


def _prompt(rows, known_records):
	return f"""You review supplier price spreadsheet rows for a prepared-meal stock system.
Return one suggestion for every input row, preserving row_number.
Prefer exact known supplier, item, and category names when a defensible match exists.
Create a concise stable ingredient name only when no known item matches.
Use units_per_pack for inner pack count, unit_size for the amount in each inner pack, and purchase_uom from g, Kg, ml, Litre, Each.
Do not invent prices, special dates, barcodes, or supplier SKUs.
Confidence is 0 to 1. Reason is one short sentence describing the evidence or uncertainty.

Known records:
{frappe.as_json(known_records)}

Spreadsheet proposals:
{frappe.as_json(rows)}
"""


def _response_schema():
	row = {
		"type": "OBJECT",
		"properties": {
			"row_number": {"type": "INTEGER"}, "item_code": {"type": "STRING"},
			"item_name": {"type": "STRING"}, "supplier": {"type": "STRING"},
			"item_category": {"type": "STRING"}, "units_per_pack": {"type": "NUMBER"},
			"unit_size": {"type": "NUMBER"}, "purchase_uom": {"type": "STRING", "enum": ["g", "Kg", "ml", "Litre", "Each"]},
			"confidence": {"type": "NUMBER"}, "reason": {"type": "STRING"},
		},
		"required": ["row_number", "item_code", "item_name", "supplier", "item_category", "confidence", "reason"],
	}
	return {"type": "OBJECT", "properties": {"rows": {"type": "ARRAY", "items": row}, "notes": {"type": "STRING"}}, "required": ["rows", "notes"]}


# endregion GEMINI PRICE CATALOGUE SUGGESTIONS
