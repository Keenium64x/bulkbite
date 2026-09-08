from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from bulkbite.api import (
	_next_production_station,
	_production_calendar_slot,
	_skipped_production_weeks,
)


# =============================================================================
# region PRODUCTION CALENDAR PROOF
# =============================================================================


def plan_rows():
	return [
		{
			"name": f"row-{meal}",
			"week_number": meal,
			"cycle_week": meal,
			"recipe": f"recipe-{meal}",
			"finished_item": f"meal-{meal}",
			"finished_item_name": f"Meal {meal}",
			"customer_required_output_qty": 100,
			"planned_output_qty": 100,
		}
		for meal in range(1, 5)
	]


def posted_run(cycle_number, meal_number, output=100, direction_action="Advance Direction"):
	return SimpleNamespace(
		docstatus=1,
		cycle_number=cycle_number,
		plan_week_number=meal_number,
		actual_output_qty=output,
		direction_action=direction_action,
		production_plan_row=f"row-{meal_number}",
		production_date=date(2026, 8, 1),
		creation="2026-08-01 08:00:00",
	)


def draft_run(cycle_number, meal_number):
	return SimpleNamespace(
		docstatus=0,
		cycle_number=cycle_number,
		plan_week_number=meal_number,
		direction_action="Advance Direction",
		production_plan_row=f"row-{meal_number}",
		creation="2026-08-01 08:00:00",
		name="draft-run",
	)


class ProductionCalendarProof(TestCase):
	def test_calendar_slot_uses_upcoming_week_and_repeats_four_meals(self):
		slot = _production_calendar_slot(plan_rows(), date(2026, 8, 1), date(2026, 9, 8))

		self.assertEqual(slot["cycle_number"], 2)
		self.assertEqual(slot["row"]["week_number"], 3)
		self.assertEqual(slot["planned_date"], date(2026, 9, 12))

	def test_skipped_weeks_are_evidence_only_and_ignore_off_plan_runs(self):
		runs = [
			posted_run(1, 1),
			posted_run(1, 2),
			posted_run(2, 1, direction_action="Off Plan"),
		]

		skipped = _skipped_production_weeks(
			plan_rows(), runs, date(2026, 8, 1), date(2026, 9, 8)
		)

		self.assertEqual(len(skipped), 4)
		self.assertEqual(
			[(row["cycle_number"], row["meal_number"]) for row in skipped],
			[(1, 3), (1, 4), (2, 1), (2, 2)],
		)
		self.assertTrue(all(row["status"] == "Skipped" for row in skipped))

	def test_current_calendar_meal_keeps_partial_output_remaining(self):
		runs = [posted_run(2, 3, output=35)]

		station = _next_production_station(
			plan_rows(), runs, date(2026, 8, 1), date(2026, 9, 8)
		)

		self.assertEqual(station["state"], "remaining")
		self.assertEqual(station["cycle_number"], 2)
		self.assertEqual(station["row"]["week_number"], 3)
		self.assertEqual(station["row"]["completed_output_qty"], 35)
		self.assertEqual(station["row"]["remaining_output_qty"], 65)

	def test_completed_calendar_meal_moves_to_the_next_slot(self):
		station = _next_production_station(
			plan_rows(), [posted_run(2, 3)], date(2026, 8, 1), date(2026, 9, 8)
		)

		self.assertEqual(station["state"], "ready")
		self.assertEqual(station["row"]["week_number"], 4)
		self.assertEqual(station["row"]["planned_date"], date(2026, 9, 19))

	def test_existing_draft_resumes_and_reports_current_calendar_target(self):
		with patch("bulkbite.api.frappe.get_doc", return_value=SimpleNamespace()), patch(
			"bulkbite.api._serialize_run", return_value={"name": "draft-run"}
		):
			station = _next_production_station(
				plan_rows(), [draft_run(2, 1)], date(2026, 8, 1), date(2026, 9, 8)
			)

		self.assertEqual(station["state"], "draft")
		self.assertEqual(station["row"]["week_number"], 1)
		self.assertEqual(station["calendar"]["row"]["week_number"], 3)
		self.assertTrue(station["behind_calendar"])


# endregion PRODUCTION CALENDAR PROOF
