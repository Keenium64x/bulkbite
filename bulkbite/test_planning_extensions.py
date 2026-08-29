from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bulkbite.bulkbite.doctype.bulkbite_finished_food_allocation.bulkbite_finished_food_allocation import _lock_finished_food_position, get_reservation_remaining, get_unallocated_finished_food
from bulkbite.planning import _delivery_threshold_recommendation, _supplier_minimum_position, build_plan_snapshot
from bulkbite.stock_ledger import append_stock_event, get_stock_balance


class TestFinishedFoodBuyingCoverage(TestCase):
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
