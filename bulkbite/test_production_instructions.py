from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from bulkbite.production_instructions import build_run_instruction_plan


# =============================================================================
# region DETERMINISTIC PRODUCTION INSTRUCTION PROOF
# =============================================================================


class TestProductionInstructions(TestCase):
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
		equipment = {"POT": {"name": "POT", "equipment_type_name": "Cooking pot", "capacity_uom": "Kg", "total_concurrent_capacity": 10}}
		with (
			patch("bulkbite.production_instructions.frappe.get_doc", return_value=recipe),
			patch("bulkbite.production_instructions.frappe.db.get_value", side_effect=lambda _doctype, item_code, _fields, as_dict=True: {"prepared_yield_factor": 2.5 if item_code == "RICE" else 1, "average_piece_weight_g": 200 if item_code == "SAUCE" else 0, "piece_count_label": "medium sauce vegetables" if item_code == "SAUCE" else "", "preparation_yield_note": None}),
			patch("bulkbite.production_instructions.load_expected_usage", return_value=expectation),
			patch("bulkbite.production_instructions._equipment_position", return_value=equipment),
			patch("bulkbite.production_instructions.frappe.conf", {}),
		):
			result = build_run_instruction_plan("RECIPE-001", 25, 2)

		self.assertEqual(result["ingredients"][0]["quantity"], 15)
		self.assertEqual(result["ingredients"][0]["prepared_quantity"], 37.5)
		self.assertEqual(result["ingredients"][1]["piece_count_estimate"], 50)
		self.assertEqual(result["steps"][0]["batch_count"], 2)
		self.assertEqual(result["steps"][2]["depends_on_steps"], [1, 2])
		self.assertEqual(result["estimated_elapsed_minutes"], 25)
		self.assertEqual(len(result["worker_lanes"]), 2)
		self.assertEqual(result["equipment"], [equipment["POT"]])


# endregion DETERMINISTIC PRODUCTION INSTRUCTION PROOF
