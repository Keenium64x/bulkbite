from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import frappe
from frappe import _
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat


# =============================================================================
# region PRIVATE DOCUMENT OCR
# =============================================================================


SUPPORTED_IMAGES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class OcrPage:
	page_number: int
	text: str
	engine: str
	quality_score: float
	warnings: tuple[str, ...]


def extract_private_document(path):
	images = _document_images(Path(path))
	pages = [_extract_page(image, index + 1) for index, image in enumerate(images)]
	raw_text = "\n\n".join(page.text for page in pages).strip()
	evidence = json.dumps({"pages": [asdict(page) for page in pages]}, ensure_ascii=False)
	warnings = [warning for page in pages for warning in page.warnings]
	return {"raw_text": raw_text, "provider": "Local Tesseract OCR", "evidence": evidence, "warning": "\n".join(dict.fromkeys(warnings))}


def _document_images(path):
	if not path.exists():
		frappe.throw(_("The private source file could not be found."))
	if path.suffix.lower() == ".pdf":
		return _pdf_images(path)
	if path.suffix.lower() not in SUPPORTED_IMAGES:
		frappe.throw(_("Use PDF, PNG, JPEG, TIFF, BMP, or WebP for document extraction."))
	with Image.open(path) as image:
		return [_normalize_image(image.copy())]


def _pdf_images(path):
	if not shutil.which("pdftoppm"):
		frappe.throw(_("PDF extraction requires poppler-utils (pdftoppm)."))
	with tempfile.TemporaryDirectory(prefix="bulkbite-document-") as directory:
		prefix = Path(directory) / "page"
		result = subprocess.run(
			["pdftoppm", "-jpeg", "-r", "260", str(path), str(prefix)],
			check=False,
			capture_output=True,
			timeout=120,
		)
		if result.returncode:
			frappe.throw(_("The PDF could not be prepared for OCR."))
		return [_normalize_image(Image.open(file_path).copy()) for file_path in sorted(Path(directory).glob("page-*.jpg"))]


def _extract_page(image, page_number):
	warnings, quality = _quality(image)
	candidates = []
	for variant_name, variant in _variants(image):
		for segmentation in (4, 6, 11, 12):
			text = _run_tesseract(variant, segmentation)
			if text:
				candidates.append((f"Tesseract {variant_name} PSM {segmentation}", text))
	if not candidates:
		frappe.throw(_("Local OCR could not read any text from the uploaded document."))
	engine, text = max(candidates, key=lambda candidate: _text_score(candidate[1]))
	return OcrPage(page_number, text, engine, quality, warnings)


def _run_tesseract(image, segmentation):
	if not shutil.which("tesseract"):
		frappe.throw(_("Local document extraction requires Tesseract OCR."))
	with tempfile.NamedTemporaryFile(prefix="bulkbite-ocr-", suffix=".png") as source:
		image.save(source.name, format="PNG")
		result = subprocess.run(
			["tesseract", source.name, "stdout", "--oem", "3", "--psm", str(segmentation)],
			check=False,
			capture_output=True,
			text=True,
			timeout=90,
		)
	return result.stdout.strip() if result.returncode == 0 else ""


def _normalize_image(image):
	image = ImageOps.exif_transpose(image).convert("RGB")
	if max(image.size) > 3600:
		image.thumbnail((3600, 3600), Image.Resampling.LANCZOS)
	return image


def _variants(image):
	gray = ImageOps.grayscale(image)
	scale = max(1, min(3, round(2400 / max(1, min(gray.size)))))
	if scale > 1:
		gray = gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS)
	enhanced = ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.SHARPEN)
	threshold = enhanced.point(lambda pixel: 255 if pixel > 165 else 0)
	return (("grayscale", gray), ("enhanced", enhanced), ("threshold", threshold))


def _quality(image):
	gray = ImageOps.grayscale(image)
	contrast = ImageStat.Stat(gray).stddev[0]
	edges = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
	warnings = []
	if min(gray.size) < 900:
		warnings.append("Low resolution")
	if contrast < 28:
		warnings.append("Low contrast")
	if edges < 8:
		warnings.append("Possible blur")
	resolution_score = min(1.0, min(gray.size) / 1500)
	quality = round(100 * (0.45 * resolution_score + 0.3 * min(1, contrast / 55) + 0.25 * min(1, edges / 20)), 1)
	return tuple(warnings), quality


def _text_score(text):
	lines = [line.strip() for line in text.splitlines() if line.strip()]
	alphanumeric = sum(character.isalnum() for character in text)
	measurement_hints = sum(any(character.isdigit() for character in line) for line in lines)
	return alphanumeric + measurement_hints * 30


# endregion PRIVATE DOCUMENT OCR
