from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import frappe
from frappe import _


# =============================================================================
# region PRIVATE TEXT EXTRACTION
# =============================================================================


def extract_private_text(path):
	"""Read supplied text or an existing PDF text layer. This never performs image OCR."""
	path = Path(path)
	if not path.exists():
		frappe.throw(_("The private source file could not be found."))
	suffix = path.suffix.lower()
	if suffix in {".txt", ".csv", ".tsv", ".md"}:
		text = path.read_text(encoding="utf-8", errors="replace").strip()
		return _result(text, "File text", None)
	if suffix == ".pdf":
		if not shutil.which("pdftotext"):
			frappe.throw(_("PDF text extraction requires poppler-utils (pdftotext)."))
		result = subprocess.run(
			["pdftotext", "-layout", str(path), "-"],
			check=False,
			capture_output=True,
			text=True,
			timeout=60,
		)
		text = result.stdout.strip() if result.returncode == 0 else ""
		if text:
			return _result(text, "PDF text layer", None)
		from bulkbite.document_ocr import extract_private_document

		return extract_private_document(path)
	if suffix in {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
		from bulkbite.document_ocr import extract_private_document

		return extract_private_document(path)
	return _result("", "No text extractor", _("This file type needs transcribed text before it can be parsed."))


def _result(text, provider, warning):
	evidence = json.dumps({"provider": provider, "lines": text.splitlines()}, ensure_ascii=False)
	return {"raw_text": text, "provider": provider, "evidence": evidence, "warning": warning}


# endregion PRIVATE TEXT EXTRACTION
