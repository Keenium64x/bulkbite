from __future__ import annotations

import re

import frappe
import requests

from bulkbite.kitchen_instruction_schema import KitchenInstructionProposal


# =============================================================================
# region AI KITCHEN METHOD PROPOSAL
# =============================================================================


_DEFAULT_MODEL = "gemini-2.5-flash-lite"
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def kitchen_ai_is_available():
	return bool(frappe.conf.get("gemini_api_key") and frappe.conf.get("gemini_private_receipt_approved"))


def propose_kitchen_tasks(recipe_context, ingredients, equipment, team_size, timing_evidence=None):
	"""Ask Gemini for method detail only. Quantities and scheduling stay deterministic."""
	if not kitchen_ai_is_available():
		return None
	model = str(frappe.conf.get("document_ai_model") or _DEFAULT_MODEL)
	if not _MODEL_PATTERN.fullmatch(model):
		raise ValueError("The configured Gemini model name is invalid.")
	try:
		response = requests.post(
			f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
			headers={"Content-Type": "application/json", "x-goog-api-key": frappe.conf.get("gemini_api_key")},
			json={
				"contents": [{"parts": [{"text": _prompt(recipe_context, ingredients, equipment, team_size, timing_evidence)}]}],
				"generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": _response_schema()},
			},
			timeout=90,
		)
	except requests.RequestException as exc:
		raise RuntimeError("Gemini kitchen planning could not be reached.") from exc
	if not response.ok:
		raise RuntimeError(f"Gemini kitchen planning returned HTTP {response.status_code}.")
	parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
	text = "".join(str(part.get("text") or "") for part in parts).strip()
	if not text:
		raise RuntimeError("Gemini returned no kitchen method proposal.")
	return KitchenInstructionProposal.model_validate_json(text)


def _prompt(recipe_context, ingredients, equipment, team_size, timing_evidence=None):
	return f"""Design a practical kitchen task graph for the supplied BulkBite production run.

The ingredients and quantities are authoritative. Never add, remove, replace, or recalculate ingredients. Do not write any ingredient quantity inside objective or substep prose because BulkBite displays the authoritative quantities separately. Use only the supplied ingredient item codes and equipment type IDs. The task graph must be connected, acyclic, and cover preparation, cooking, combining, quality checks, and packing where applicable.

Each task needs a realistic per-batch duration, dependencies, minimum workers, one explicit equipment type where equipment is used, and detailed ordered substeps. BulkBite will turn the equipment capacity and prepared ingredient load into the required batch nodes, so do not multiply duration by the number of batches. Substeps must explain the physical method clearly enough for a worker to follow, such as rinsing lentils, preparing stock, boiling, simmering, and checking doneness. Prefer safe observable checks when the supplied recipe guidance does not justify an exact temperature or time. Split hands-on starting or checking work from unattended simmering, baking, resting, or cooling. Set requires_active_worker to false only for a genuinely unattended interval. That interval must still retain its equipment and dependency truth. Set can_run_concurrently only for preparation or portioning work where another free worker can safely help. Identify tasks that can happen at the same time through their dependencies. Use recent timing evidence only to improve the estimate. Do not copy a prior duration blindly when output, team, equipment, or method differs. Do not assign final workers, calculate batch counts, or calculate CPM values. BulkBite does that deterministically.

Recipe context:
{frappe.as_json(recipe_context)}

Authoritative ingredients:
{frappe.as_json(ingredients)}

Available equipment:
{frappe.as_json(equipment)}

Recent actual timing evidence for this recipe:
{frappe.as_json(timing_evidence or [])}

Available workers: {max(int(team_size or 1), 1)}
"""


def _response_schema():
	substep = {
		"type": "OBJECT",
		"properties": {"instruction": {"type": "STRING"}, "check": {"type": "STRING"}},
		"required": ["instruction", "check"],
	}
	task = {
		"type": "OBJECT",
		"properties": {
			"task_id": {"type": "STRING"},
			"title": {"type": "STRING"},
			"objective": {"type": "STRING"},
			"ingredient_item_codes": {"type": "ARRAY", "items": {"type": "STRING"}},
			"equipment_type": {"type": "STRING", "nullable": True},
			"depends_on_task_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
			"duration_minutes": {"type": "NUMBER"},
			"minimum_workers": {"type": "INTEGER"},
			"can_run_concurrently": {"type": "BOOLEAN"},
			"requires_active_worker": {"type": "BOOLEAN"},
			"worker_role": {"type": "STRING"},
			"quality_checkpoint": {"type": "STRING"},
			"substeps": {"type": "ARRAY", "items": substep},
		},
		"required": ["task_id", "title", "objective", "ingredient_item_codes", "depends_on_task_ids", "duration_minutes", "minimum_workers", "can_run_concurrently", "requires_active_worker", "worker_role", "quality_checkpoint", "substeps"],
	}
	return {"type": "OBJECT", "properties": {"tasks": {"type": "ARRAY", "items": task}, "notes": {"type": "STRING"}}, "required": ["tasks", "notes"]}


# endregion AI KITCHEN METHOD PROPOSAL
