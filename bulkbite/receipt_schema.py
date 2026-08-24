from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReceiptLineExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	description: str
	packs_bought: float = Field(default=1, gt=0)
	units_per_pack: float = Field(default=1, gt=0)
	unit_size: float = Field(gt=0)
	purchase_uom: str | None = None
	line_total: float | None = Field(default=None, ge=0)
	barcode: str | None = None
	source_quote: str
	confidence: float = Field(default=0, ge=0, le=1)
	notes: str | None = None
	uncertainty: str | None = None

	@field_validator("description", "purchase_uom", "barcode", "source_quote", "notes", "uncertainty")
	@classmethod
	def normalize_text(cls, value):
		return " ".join(str(value or "").split())[:500] if value is not None else None


class ReceiptExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	supplier_name: str | None = None
	invoice_number: str | None = None
	invoice_date: str | None = Field(default=None, description="ISO date in YYYY-MM-DD format")
	currency: str = "ZAR"
	subtotal: float | None = Field(default=None, ge=0)
	tax: float | None = Field(default=None, ge=0)
	total: float | None = Field(default=None, ge=0)
	lines: list[ReceiptLineExtraction] = Field(default_factory=list)
	notes: str | None = None
	confidence: float = Field(default=0, ge=0, le=1)

	@field_validator("supplier_name", "invoice_number", "invoice_date", "currency", "notes")
	@classmethod
	def normalize_header_text(cls, value):
		return " ".join(str(value or "").split())[:500] if value is not None else None
