from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from bulkbite.kitchen_scheduler import KitchenScheduleError
from bulkbite.production_instructions import _expand_equipment_batches, build_run_instruction_plan


# =============================================================================
# region DETERMINISTIC PRODUCTION INSTRUCTION PROOF
# =============================================================================


class TestProductionInstructions(TestCase):
	def test_equipment_batching_refuses_an_incompatible_capacity_unit(self):
		tasks = [{
			"task_id": "cook-pasta",
			"step_number": 1,
			"step_name": "Cook spaghetti",
			"title": "Cook spaghetti",
			"objective": "Cook the prepared spaghetti.",
			"instruction": "Cook the prepared spaghetti.",
			"ingredient_item_codes": ["SPAGHETTI"],
			"equipment_type": "TEN-LITRE-POT",
			"depends_on_task_ids": [],
			"duration_minutes": 10,
			"estimated_minutes": 10,
			"minimum_workers": 1,
			"requires_active_worker": True,
			"substeps": [],
		}]
		ingredients = [{"item_code": "SPAGHETTI", "prepared_quantity": 50, "uom": "Kg"}]
		equipment = {"TEN-LITRE-POT": {"equipment_type_name": "10 L pot", "capacity_qty": 10, "capacity_uom": "Litre"}}

		with self.assertRaisesRegex(KitchenScheduleError, "usable Kg capacity"):
			_expand_equipment_batches(tasks, ingredients, equipment)

	def test_recipe_quantities_batches_dependencies_and_lanes_are_deterministic(self):
		recipe = SimpleNamespace(
			name="RECIPE-001",
			recipe_name="Proof meal",
			output_uom="Kg",
			instruction_steps=[
				SimpleNamespace(step_number=1, step_name="Prepare rice", instruction="Wash and cook the rice.", ingredient_items="RICE", equipment_type="POT", depends_on_steps="", can_run_concurrently=1, duration_minutes=10, duration_per_kg_minutes=0, minimum_workers=1, worker_role="Cook", quality_checkpoint="Rice is clean."),
				SimpleNamespace(step_number=2, step_name="Prepare sauce", instruction="Cook the sauce.", ingredient_items="SAUCE", equipment_type="POT", depends_on_steps="", can_run_concurrently=1, duration_minutes=8, duration_per_kg_minutes=0, minimum_workers=1, worker_role="Cook", quality_checkpoint="Sauce is simmering."),
				SimpleNamespace(step_number=3, step_name="Combine", instruction="Combine and portion.", ingredient_items="RICE,SAUCE", equipment_type=None, depends_on_steps="1,2", can_run_concurrently=0, duration_minutes=5, duration_per_kg_minutes=0, minimum_workers=2, worker_role="Team", quality_checkpoint="Final weight matches."),
			],
		)
		expectation = {"ingredients": [
			{"item_code": "RICE", "item_name": "Rice", "expected_qty": 15, "uom": "Kg"},
			{"item_code": "SAUCE", "item_name": "Sauce", "expected_qty": 10, "uom": "Kg"},
		]}
		equipment = {"POT": {"name": "POT", "equipment_type_name": "10 kg cooking pot", "capacity_qty": 10, "capacity_uom": "Kg", "total_concurrent_capacity": 20, "quantity_available": 2, "concurrent_batch_limit": 1}}
		with (
			patch("bulkbite.production_instructions.frappe.get_doc", return_value=recipe),
			patch("bulkbite.production_instructions.frappe.db.get_value", side_effect=lambda _doctype, item_code, _fields, as_dict=True: {"prepared_yield_factor": 2.5 if item_code == "RICE" else 1, "average_piece_weight_g": 200 if item_code == "SAUCE" else 0, "piece_count_label": "medium sauce vegetables" if item_code == "SAUCE" else "", "preparation_yield_note": None}),
			patch("bulkbite.production_instructions.load_expected_usage", return_value=expectation),
			patch("bulkbite.production_instructions._equipment_position", return_value=equipment),
			patch("bulkbite.production_instructions.frappe.conf", {}),
			patch("bulkbite.production_instructions._instruction_settings", return_value={"kitchen_default_slack_minutes": 0, "use_ai_kitchen_instructions": False}),
		):
			result = build_run_instruction_plan("RECIPE-001", 25, 2)

		self.assertEqual(result["ingredients"][0]["quantity"], 15)
		self.assertEqual(result["ingredients"][0]["prepared_quantity"], 37.5)
		self.assertEqual(result["ingredients"][1]["piece_count_estimate"], 50)
		rice_batches = [step for step in result["steps"] if step["source_task_id"] == "1"]
		combine = next(step for step in result["steps"] if step["source_task_id"] == "3")
		self.assertEqual(len(rice_batches), 4)
		self.assertEqual(rice_batches[0]["batch_count"], 4)
		self.assertEqual(rice_batches[-1]["batch_load_qty"], 7.5)
		self.assertEqual(len(combine["depends_on_steps"]), 5)
		self.assertEqual(result["estimated_elapsed_minutes"], 33)
		self.assertEqual(result["critical_path_minutes"], 33)
		self.assertEqual(result["steps"][0]["early_start"], 0)
		self.assertEqual(result["steps"][2]["early_start"], 10)
		self.assertTrue(combine["is_critical"])
		self.assertEqual(combine["assigned_workers"], [1, 2])
		self.assertEqual(len(result["worker_lanes"]), 2)
		self.assertEqual(result["equipment"], [equipment["POT"]])


# endregion DETERMINISTIC PRODUCTION INSTRUCTION PROOF
