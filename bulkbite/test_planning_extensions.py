from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from datetime import date

import frappe
from frappe.tests import IntegrationTestCase

from bulkbite.api import _next_production_station
from bulkbite.bulkbite.doctype.bulkbite_finished_food_allocation.bulkbite_finished_food_allocation import _lock_finished_food_position, get_reservation_remaining, get_unallocated_finished_food
from bulkbite.planning import _delivery_threshold_recommendation, _next_planned_production_date, _supplier_minimum_position, _supplier_order_deadline, build_plan_snapshot
from bulkbite.stock_ledger import append_stock_event, get_stock_balance
from bulkbite.workforce import calculate_capacity_forecast
from bulkbite.workforce import _select_required_output_runs


class TestFinishedFoodBuyingCoverage(TestCase):
	def test_balanced_runs_share_remaining_output_by_capacity_after_custom_run(self):
		runs = [
			{"run_number": 1, "output_mode": "Fixed", "planned_output_qty": 20, "scheduled_elapsed_hours": 4, "planned_people": 1},
			{"run_number": 2, "output_mode": "Auto", "planned_output_qty": 0, "scheduled_elapsed_hours": 4, "planned_people": 10},
			{"run_number": 3, "output_mode": "Auto", "planned_output_qty": 0, "scheduled_elapsed_hours": 8, "planned_people": 10},
		]
		selected = _select_required_output_runs(runs, 0, 80, 60)
		self.assertEqual([row["planned_output_qty"] for row in selected], [20.0, 20.0, 40.0])

	def test_balanced_runs_redistribute_output_when_one_run_hits_capacity(self):
		runs = [
			{"run_number": 1, "output_mode": "Auto", "planned_output_qty": 0, "scheduled_elapsed_hours": 2, "planned_people": 1},
			{"run_number": 2, "output_mode": "Auto", "planned_output_qty": 0, "scheduled_elapsed_hours": 8, "planned_people": 1},
		]
		selected = _select_required_output_runs(runs, 0, 8, 60)
		self.assertEqual([row["planned_output_qty"] for row in selected], [1.6, 6.4])

	def test_partial_production_keeps_the_same_meal_and_returns_the_remaining_target(self):
		rows = [{"name": "ROW-1", "week_number": 1, "planned_output_qty": 20}, {"name": "ROW-2", "week_number": 2, "planned_output_qty": 10}]
		runs = [SimpleNamespace(name="RUN-1", docstatus=1, direction_action="Advance Direction", cycle_number=1, plan_week_number=1, production_plan_row="ROW-1", production_date=date(2026, 8, 29), creation="2026-08-29 10:00:00", actual_output_qty=7)]

		station = _next_production_station(rows, runs)

		self.assertEqual(station["state"], "remaining")
		self.assertEqual(station["row"]["name"], "ROW-1")
		self.assertEqual(station["row"]["completed_output_qty"], 7)
		self.assertEqual(station["row"]["remaining_output_qty"], 13)

	def test_cumulative_production_advances_only_after_the_meal_target_is_complete(self):
		rows = [{"name": "ROW-1", "week_number": 1, "planned_output_qty": 20}, {"name": "ROW-2", "week_number": 2, "planned_output_qty": 10}]
		runs = [
			SimpleNamespace(name="RUN-1", docstatus=1, direction_action="Advance Direction", cycle_number=1, plan_week_number=1, production_plan_row="ROW-1", production_date=date(2026, 8, 29), creation="2026-08-29 10:00:00", actual_output_qty=7),
			SimpleNamespace(name="RUN-2", docstatus=1, direction_action="Advance Direction", cycle_number=1, plan_week_number=1, production_plan_row="ROW-1", production_date=date(2026, 8, 29), creation="2026-08-29 12:00:00", actual_output_qty=13),
		]

		station = _next_production_station(rows, runs)

		self.assertEqual(station["state"], "ready")
		self.assertEqual(station["row"]["name"], "ROW-2")
		self.assertEqual(station["cycle_number"], 1)

	def test_fixed_surplus_reduces_later_auto_runs(self):
		mix = [{"plan_type": "Proof", "customer_count": 10, "meals_per_day": 1, "days_per_week": 1, "serving_size_g": 1000}]
		runs = [
			{"week_number": 1, "run_number": 1, "output_mode": "Fixed", "planned_output_qty": 25, "scheduled_elapsed_hours": 5, "planned_people": 5},
			*[
				{"week_number": week, "run_number": 1, "output_mode": "Auto", "planned_output_qty": 10, "scheduled_elapsed_hours": 2, "planned_people": 5}
				for week in range(2, 5)
			],
		]
		weeks = calculate_capacity_forecast(mix, mix, 4, [], 60, runs)

		self.assertEqual([row["planned_output_qty"] for row in weeks], [25.0, 0, 5.0, 10.0])
		self.assertEqual([row["run_count"] for row in weeks], [1, 0, 1, 1])
		self.assertEqual([row["capacity_state"] for row in weeks], ["ready", "idle", "ready", "ready"])

	def test_fixed_run_remains_deliberate_even_when_opening_food_covers_week(self):
		mix = [{"plan_type": "Proof", "customer_count": 10, "meals_per_day": 1, "days_per_week": 1, "serving_size_g": 1000}]
		runs = [
			{"week_number": 1, "run_number": 1, "output_mode": "Fixed", "planned_output_qty": 20, "scheduled_elapsed_hours": 4, "planned_people": 5},
			{"week_number": 2, "run_number": 1, "output_mode": "Fixed", "planned_output_qty": 5, "scheduled_elapsed_hours": 1, "planned_people": 5},
		]
		weeks = calculate_capacity_forecast(mix, mix, 2, [], 60, runs)

		self.assertEqual(weeks[1]["planned_output_qty"], 5)
		self.assertEqual(weeks[1]["closing_output_balance_qty"], 5)

	def test_supplier_deadline_uses_first_saved_cooking_session(self):
		plan = SimpleNamespace(
			period_start=date(2026, 8, 24),
			capacity_runs=[SimpleNamespace(week_number=1, day_of_week="Friday")],
		)
		production_date = _next_planned_production_date(plan, date(2026, 8, 24))
		with patch("bulkbite.planning.frappe.db.get_value", return_value=SimpleNamespace(delivery_lead_time_days=4, order_safety_days=1)):
			deadline = _supplier_order_deadline(plan, "Makro", date(2026, 8, 24), production_date)

		self.assertEqual(deadline["production_date"], date(2026, 8, 28))
		self.assertEqual(deadline["customer_delivery_date"], date(2026, 8, 30))
		self.assertEqual(deadline["order_by_date"], date(2026, 8, 23))

	def test_finished_food_position_uses_a_shared_item_location_lock(self):
		with patch("bulkbite.bulkbite.doctype.bulkbite_finished_food_allocation.bulkbite_finished_food_allocation.frappe.db.sql") as sql:
			_lock_finished_food_position("MEAL-001", "Finished Meals")

		self.assertEqual(sql.call_count, 2)
		self.assertEqual(sql.call_args_list[1].args[1], ("MEAL-001", "Finished Meals"))

	def test_finished_food_covers_early_weeks_before_ingredient_demand(self):
		plan = SimpleNamespace(plan_rows=[
			SimpleNamespace(name=f"row-{week}", week_number=week, planned_date=None, finished_item="MEAL", recipe="RECIPE", weekly_servings=10, planned_output_qty=10, uom="Kg")
			for week in range(1, 5)
		])
		item = SimpleNamespace(item_category="Dry", purchasable=True)

		def expected_usage(_recipe, quantity, _location):
			return {"ingredients": [{"item_code": "RICE", "item_name": "Rice", "uom": "Kg", "expected_qty": quantity / 2, "available_before_measurement": 0}]}

		with (
			patch("bulkbite.planning.get_available_stock", side_effect=lambda code, _location: 25 if code == "MEAL" else 0),
			patch("bulkbite.planning.load_expected_usage", side_effect=expected_usage),
			patch("bulkbite.planning.frappe.get_cached_doc", return_value=item),
			patch("bulkbite.planning.frappe.get_cached_value", return_value="Meal"),
		):
			sessions, requirements = build_plan_snapshot(plan, "Ingredients", 4, True)

		self.assertEqual([row["production_required_qty"] for row in sessions], [0, 0, 5, 10])
		self.assertEqual(requirements[0]["required_qty"], 7.5)

	def test_delivery_threshold_does_not_claim_unverified_stock_is_safe(self):
		with patch("bulkbite.planning.frappe.get_all", return_value=[SimpleNamespace(adjustment_type="Delivery Fee", value=80, threshold_amount=600, effective_from=None, effective_to=None)]):
			result = _delivery_threshold_recommendation("Supplier", 550, SimpleNamespace(), [], 4)

		self.assertEqual(result["pull_forward_candidates"], [])
		self.assertIn("Paying delivery", result["pull_forward_recommendation"])

	def test_supplier_order_minimum_is_advisory(self):
		rule = SimpleNamespace(adjustment_type="Minimum Order", threshold_amount=600, effective_from=None, effective_to=None)
		with patch("bulkbite.planning.frappe.get_all", return_value=[rule]):
			result = _supplier_minimum_position("Supplier", 475, SimpleNamespace())

		self.assertEqual(result["supplier_order_minimum"], 600)
		self.assertEqual(result["supplier_order_minimum_gap"], 125)
		self.assertFalse(result["supplier_order_minimum_met"])


class TestFinishedFoodAllocationLifecycle(IntegrationTestCase):
	def test_reservation_and_fulfilment_change_stock_exactly_once(self):
		frappe.set_user("Administrator")
		item = frappe.db.get_value("BulkBite Item", {"item_type": "Finished Meal", "enabled": 1}, "name")
		self.assertTrue(item)
		location = "Finished Meals"
		opening = get_stock_balance(item, location)
		append_stock_event("Production Output", item, location, 5, 10, "BulkBite Item", item)

		reservation = frappe.get_doc({
			"doctype": "BulkBite Finished Food Allocation",
			"finished_item": item,
			"source_location": location,
			"allocation_type": "Future Customers",
			"demand_period": "Proof future week",
			"quantity": 2,
		}).insert()
		reservation.submit()
		self.assertEqual(get_stock_balance(item, location), opening + 5)
		self.assertEqual(get_reservation_remaining(reservation.name), 2)
		self.assertEqual(get_unallocated_finished_food(item, location), opening + 3)

		fulfilment = frappe.get_doc({
			"doctype": "BulkBite Finished Food Allocation",
			"finished_item": item,
			"source_location": location,
			"allocation_type": "Future Customer Fulfilment",
			"source_reservation": reservation.name,
			"quantity": 1.5,
		}).insert()
		fulfilment.submit()
		self.assertEqual(get_stock_balance(item, location), opening + 3.5)
		self.assertEqual(get_reservation_remaining(reservation.name), 0.5)
		self.assertEqual(get_unallocated_finished_food(item, location), opening + 3)
		self.assertEqual(frappe.db.count("BulkBite Stock Event", {"reference_doctype": fulfilment.doctype, "reference_name": fulfilment.name}), 1)

		with self.assertRaises(frappe.ValidationError):
			over_fulfilment = frappe.get_doc({
				"doctype": "BulkBite Finished Food Allocation",
				"finished_item": item,
				"source_location": location,
				"allocation_type": "Future Customer Fulfilment",
				"source_reservation": reservation.name,
				"quantity": 1,
			}).insert()
			over_fulfilment.submit()
