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

	def test_one_worker_follows_reviewed_recipe_order(self):
		tasks = validate_task_graph([
			{"task_id": "first", "title": "First", "duration_minutes": 2},
			{"task_id": "second", "title": "Second", "duration_minutes": 3},
			{"task_id": "third", "title": "Third", "duration_minutes": 20},
		], set(), set())

		result = calculate_kitchen_schedule(tasks, 1)

		self.assertEqual(
			[step["step_number"] for step in result["worker_lanes"][0]["steps"]],
			[1, 2, 3],
		)

	def test_idle_worker_is_directed_to_safe_parallel_preparation(self):
		tasks = validate_task_graph([
			{"task_id": "rice", "title": "Start rice", "duration_minutes": 10},
			{
				"task_id": "vegetables",
				"title": "Prepare vegetables",
				"duration_minutes": 20,
				"can_run_concurrently": True,
			},
			{
				"task_id": "combine",
				"title": "Combine",
				"duration_minutes": 5,
				"depends_on_task_ids": ["rice", "vegetables"],
			},
		], set(), set())

		result = calculate_kitchen_schedule(tasks, 2)
		assists = [
			step
			for lane in result["worker_lanes"]
			for step in lane["steps"]
			if step.get("kind") == "assist"
		]

		self.assertEqual(len(assists), 1)
		self.assertEqual(assists[0]["step_number"], 2)
		self.assertEqual(assists[0]["start_minute"], 10)
		self.assertEqual(assists[0]["end_minute"], 20)

	def test_unattended_cooking_occupies_equipment_without_occupying_worker(self):
		tasks = validate_task_graph([
			{"task_id": "start", "title": "Start rice", "duration_minutes": 5, "equipment_type": "POT"},
			{
				"task_id": "simmer",
				"title": "Simmer rice",
				"duration_minutes": 20,
				"equipment_type": "POT",
				"depends_on_task_ids": ["start"],
				"requires_active_worker": False,
			},
			{"task_id": "vegetables", "title": "Prepare vegetables", "duration_minutes": 12, "can_run_concurrently": True},
			{"task_id": "finish", "title": "Finish meal", "duration_minutes": 3, "depends_on_task_ids": ["simmer", "vegetables"]},
		], set(), {"POT"})

		result = calculate_kitchen_schedule(tasks, 1, {"POT": 1})
		by_id = {task["task_id"]: task for task in result["tasks"]}

		self.assertEqual(by_id["simmer"]["assigned_workers"], [])
		self.assertEqual(by_id["simmer"]["scheduled_start"], 5)
		self.assertEqual(by_id["vegetables"]["scheduled_start"], 5)
		self.assertEqual([step["step_number"] for step in result["worker_lanes"][0]["steps"]], [1, 3, 4])
