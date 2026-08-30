from __future__ import annotations

from pydantic import BaseModel, Field


class KitchenSubstepProposal(BaseModel):
	instruction: str
	check: str = ""


class KitchenTaskProposal(BaseModel):
	task_id: str
	title: str
	objective: str
	ingredient_item_codes: list[str] = Field(default_factory=list)
	equipment_type: str | None = None
	depends_on_task_ids: list[str] = Field(default_factory=list)
	duration_minutes: float = Field(gt=0)
	minimum_workers: int = Field(default=1, ge=1)
	can_run_concurrently: bool = False
	requires_active_worker: bool = True
	worker_role: str = ""
	quality_checkpoint: str = ""
	substeps: list[KitchenSubstepProposal] = Field(default_factory=list)


class KitchenInstructionProposal(BaseModel):
	tasks: list[KitchenTaskProposal]
	notes: str = ""
