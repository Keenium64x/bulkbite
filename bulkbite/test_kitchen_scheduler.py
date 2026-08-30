from unittest import TestCase

from bulkbite.kitchen_scheduler import KitchenScheduleError, calculate_kitchen_schedule, validate_task_graph


class TestKitchenScheduler(TestCase):
	def test_cpm_and_worker_lanes_are_deterministic(self):
		tasks = validate_task_graph([
			{"task_id": "rice", "title": "Cook rice", "duration_minutes": 20, "ingredient_item_codes": ["RICE"], "equipment_type": "POT", "depends_on_task_ids": [], "substeps": ["Rinse rice"]},
			{"task_id": "lentils", "title": "Cook lentils", "duration_minutes": 15, "ingredient_item_codes": ["LENTILS"], "equipment_type": "POT", "depends_on_task_ids": [], "substeps": ["Rinse lentils"]},
			{"task_id": "combine", "title": "Combine", "duration_minutes": 5, "ingredient_item_codes": ["RICE", "LENTILS"], "depends_on_task_ids": ["rice", "lentils"], "minimum_workers": 2},
		], {"RICE", "LENTILS"}, {"POT"})
		result = calculate_kitchen_schedule(tasks, 2, {"POT": 2}, 0)
		by_id = {task["task_id"]: task for task in result["tasks"]}

		self.assertEqual(result["critical_path_minutes"], 25)
		self.assertEqual(result["resource_constrained_minutes"], 25)
		self.assertTrue(by_id["rice"]["is_critical"])
		self.assertEqual(by_id["combine"]["assigned_workers"], [1, 2])

	def test_unknown_ingredient_and_cycles_are_rejected(self):
		with self.assertRaises(KitchenScheduleError):
			validate_task_graph([{"task_id": "x", "title": "X", "duration_minutes": 1, "ingredient_item_codes": ["UNKNOWN"]}], {"RICE"}, set())
		with self.assertRaises(KitchenScheduleError):
			validate_task_graph([
				{"task_id": "a", "title": "A", "duration_minutes": 1, "depends_on_task_ids": ["b"]},
				{"task_id": "b", "title": "B", "duration_minutes": 1, "depends_on_task_ids": ["a"]},
			], set(), set())
		with self.assertRaises(KitchenScheduleError):
			validate_task_graph([{"task_id": "x", "title": "X", "objective": "Add 5 kg rice", "duration_minutes": 1, "ingredient_item_codes": ["RICE"]}], {"RICE"}, set())
