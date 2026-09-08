from unittest import TestCase

from bulkbite.workforce import calculate_weekly_capacity


# =============================================================================
# region WEEKLY CAPACITY PROOF
# =============================================================================


class WeeklyCapacityProof(TestCase):
	def test_more_people_have_diminishing_returns(self):
		result = calculate_weekly_capacity(
			100, 0, 10, [{"scheduled_elapsed_hours": 8, "planned_people": 4}]
		)

		self.assertEqual(result["raw_team_hours"], 32)
		self.assertEqual(result["sessions"][0]["effective_people"], 2.7)
		self.assertLess(result["effective_hours"], result["raw_team_hours"])

	def test_each_session_is_bounded_to_eight_hours(self):
		result = calculate_weekly_capacity(
			100, 0, 10, [{"scheduled_elapsed_hours": 14, "planned_people": 2}]
		)

		self.assertEqual(result["sessions"][0]["scheduled_elapsed_hours"], 8)

	def test_full_shift_gap_requires_another_run(self):
		result = calculate_weekly_capacity(
			300, 0, 60, [{"scheduled_elapsed_hours": 8, "planned_people": 2}]
		)

		self.assertFalse(result["ready"])
		self.assertTrue(result["additional_run_required"])

	def test_extra_output_requires_storage_without_inventing_capacity(self):
		result = calculate_weekly_capacity(
			100, 20, 5, [{"scheduled_elapsed_hours": 8, "planned_people": 4}]
		)

		self.assertEqual(result["storage"]["status"], "Not configured")
		self.assertFalse(result["storage"]["configured"])
		self.assertEqual(result["storage"]["required_qty"], 20)


# endregion WEEKLY CAPACITY PROOF
