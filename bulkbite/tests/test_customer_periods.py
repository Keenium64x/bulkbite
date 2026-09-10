from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from bulkbite.api import _customer_mix_changed, _validate_customer_mix_version_date
from bulkbite.customer_periods import calculate_customer_period_drivers, ensure_plan_customer_periods
from bulkbite.reporting_scope import is_demo_evidence


# =============================================================================
# region EFFECTIVE-DATED CUSTOMER PERIOD PROOF
# =============================================================================


class TestEffectiveDatedCustomerPeriods(TestCase):
	def test_customer_mix_change_ignores_row_order(self):
		saved = [frappe._dict(plan_type="Full", customer_count=1, price_basis="Normal"), frappe._dict(plan_type="Lite", customer_count=0, price_basis="Normal")]
		incoming = [{"plan_type": "Lite", "customer_count": 0, "price_basis": "Normal"}, {"plan_type": "Full", "customer_count": 1, "price_basis": "Normal"}]

		self.assertFalse(_customer_mix_changed(saved, incoming))
		incoming[1]["customer_count"] = 2
		self.assertTrue(_customer_mix_changed(saved, incoming))
		incoming[1]["customer_count"] = 1
		incoming[1]["price_basis"] = "Discounted"
		self.assertTrue(_customer_mix_changed(saved, incoming))

	def test_customer_changes_must_begin_after_the_existing_direction(self):
		plan = frappe._dict(name="PLAN-1", period_start=date(2026, 8, 1))

		with self.assertRaises(frappe.ValidationError):
			_validate_customer_mix_version_date(plan, date(2026, 8, 1))

	def test_dated_revenue_uses_each_periods_frozen_customer_count_and_price(self):
		periods = [
			frappe._dict(
				plan_type="Full", customer_count=1, effective_from=date(2026, 8, 1), effective_to=date(2026, 8, 28),
				evidence_status="Incomplete", serving_size_g=600, meals_per_day=2, days_per_week=7, cycle_weeks=4, cycle_price=2799.95,
			),
			frappe._dict(
				plan_type="Full", customer_count=2, effective_from=date(2026, 9, 12), effective_to=None,
				evidence_status="Incomplete", serving_size_g=600, meals_per_day=2, days_per_week=7, cycle_weeks=4, cycle_price=2799.95,
			),
		]

		with patch("bulkbite.customer_periods.get_customer_mix_periods", return_value=periods):
			drivers = calculate_customer_period_drivers(date(2026, 8, 1), date(2026, 10, 9))

		self.assertEqual(drivers["revenue"], 8399.85)
		self.assertEqual(drivers["customers"], 3)
		self.assertEqual(drivers["customer_period_count"], 2)
		self.assertEqual(drivers["incomplete_customer_period_count"], 2)
		self.assertEqual(drivers["kilograms"], 100.8)

	def test_demo_reporting_evidence_is_explicitly_excluded(self):
		self.assertTrue(is_demo_evidence(frappe._dict(notes="DEMO capacity example"), "notes"))
		self.assertTrue(is_demo_evidence(frappe._dict(supplier_invoice_number="DEMO-OPS-001"), "supplier_invoice_number"))
		self.assertFalse(is_demo_evidence(frappe._dict(notes="", supplier_invoice_number="MAKRO-001"), "notes", "supplier_invoice_number"))

	@patch("bulkbite.customer_periods.frappe.db.set_value")
	@patch("bulkbite.customer_periods.frappe.db.get_value", return_value="PERIOD-1")
	def test_existing_period_is_refrozen_from_its_plan_version(self, _get_value, set_value):
		plan = frappe._dict(
			name="PLAN-1",
			period_start=date(2026, 9, 12),
			period_end=None,
			customer_mix=[frappe._dict(
				plan_type="Full", customer_count=2, serving_size_g=600, meals_per_day=2,
				days_per_week=7, cycle_weeks=4, customer_price=2799.95, price_basis="Normal",
			)],
		)

		self.assertEqual(ensure_plan_customer_periods(plan), ["PERIOD-1"])
		values = set_value.call_args.args[2]
		self.assertEqual(values["cycle_price"], 2799.95)
		self.assertEqual(values["price_basis"], "Normal")


# endregion EFFECTIVE-DATED CUSTOMER PERIOD PROOF
