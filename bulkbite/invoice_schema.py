from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# region COST INVOICE EXTRACTION CONTRACT
# =============================================================================


class CostInvoiceLineExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	description: str
	expense_type_name: str | None = None
	cost_category: str = "Other Production Overhead"
	quantity: float = Field(default=1, gt=0)
	unit_rate: float | None = Field(default=None, ge=0)
	line_amount: float = Field(ge=0)
	vat_amount: float = Field(default=0, ge=0)
	accounting_category: str | None = None
	source_quote: str
	confidence: float = Field(default=0, ge=0, le=1)
	notes: str | None = None
	uncertainty: str | None = None

	@field_validator("description", "expense_type_name", "cost_category", "accounting_category", "source_quote", "notes", "uncertainty")
	@classmethod
	def normalize_text(cls, value):
		return " ".join(str(value or "").split())[:500] if value is not None else None


class CostInvoiceExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	payee: str | None = None
	invoice_number: str | None = None
	invoice_date: str | None = Field(default=None, description="ISO date in YYYY-MM-DD format")
	due_date: str | None = Field(default=None, description="ISO date in YYYY-MM-DD format")
	document_type: str = "General Supplier Invoice"
	currency: str = "ZAR"
	subtotal: float | None = Field(default=None, ge=0)
	tax: float | None = Field(default=None, ge=0)
	total: float | None = Field(default=None, ge=0)
	lines: list[CostInvoiceLineExtraction] = Field(default_factory=list)
	notes: str | None = None
	confidence: float = Field(default=0, ge=0, le=1)

	@field_validator("payee", "invoice_number", "invoice_date", "due_date", "document_type", "currency", "notes")
	@classmethod
	def normalize_header_text(cls, value):
		return " ".join(str(value or "").split())[:500] if value is not None else None


# endregion COST INVOICE EXTRACTION CONTRACT
