from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# region REVIEWED PRICE CATALOGUE CONTRACT
# =============================================================================


class PriceSetupProposal(BaseModel):
	model_config = ConfigDict(extra="forbid")

	kind: Literal["supplier", "category", "item"]
	source_key: str
	name: str
	status: Literal["insert", "update", "unchanged", "error"] = "insert"
	item_code: str = ""
	item_name: str = ""
	item_category: str = ""
	stock_uom: Literal["Kg", "Litre", "Each"] | str = "Kg"
	default_supplier: str = ""
	confidence: float = Field(default=1, ge=0, le=1)
	reason: str = ""
	errors: list[str] = Field(default_factory=list)

	@field_validator("source_key", "name", "item_code", "item_name", "item_category", "default_supplier", mode="before")
	@classmethod
	def clean_text(cls, value):
		return str(value or "").strip()


class PriceOfferProposal(BaseModel):
	model_config = ConfigDict(extra="allow")

	row_number: int
	record_name: str = ""
	item_code: str
	item_name: str
	supplier: str
	item_category: str = ""
	status: Literal["insert", "update", "unchanged", "error"] = "insert"
	confidence: float = Field(default=1, ge=0, le=1)
	reason: str = ""
	errors: list[str] = Field(default_factory=list)
	values: dict = Field(default_factory=dict)


class PriceImportProposal(BaseModel):
	model_config = ConfigDict(extra="forbid")

	mapping: dict[str, str] = Field(default_factory=dict)
	suppliers: list[PriceSetupProposal] = Field(default_factory=list)
	categories: list[PriceSetupProposal] = Field(default_factory=list)
	items: list[PriceSetupProposal] = Field(default_factory=list)
	offers: list[PriceOfferProposal] = Field(default_factory=list)
	ai_used: bool = False
	ai_notes: str = ""


class AIPriceSuggestion(BaseModel):
	model_config = ConfigDict(extra="forbid")

	row_number: int
	item_code: str = ""
	item_name: str = ""
	supplier: str = ""
	item_category: str = ""
	units_per_pack: float | None = Field(default=None, gt=0)
	unit_size: float | None = Field(default=None, gt=0)
	purchase_uom: Literal["g", "Kg", "ml", "Litre", "Each"] | None = None
	confidence: float = Field(default=0.5, ge=0, le=1)
	reason: str = ""


class AIPriceImportSuggestions(BaseModel):
	model_config = ConfigDict(extra="forbid")

	rows: list[AIPriceSuggestion] = Field(default_factory=list)
	notes: str = ""


# endregion REVIEWED PRICE CATALOGUE CONTRACT
