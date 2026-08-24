from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MeasurementLineExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	item_name: str = Field(description="Ingredient or stock item as written")
	quantity: float = Field(ge=0)
	unit: str
	source_page: int | None = Field(default=None, ge=1)
	source_quote: str = Field(description="Exact source text supporting this measurement")
	confidence: float = Field(default=0, ge=0, le=1)
	uncertainty: str | None = None

	@field_validator("item_name", "unit", "source_quote")
	@classmethod
	def normalize_text(cls, value):
		return " ".join(str(value or "").split())[:500]


class MeasurementDocumentExtraction(BaseModel):
	model_config = ConfigDict(extra="forbid")

	document_kind: Literal["Remaining Stock Sheet", "Usage Sheet", "Stock Audit"]
	lines: list[MeasurementLineExtraction] = Field(default_factory=list)
	notes: str | None = None
	confidence: float = Field(default=0, ge=0, le=1)
