from unittest import TestCase

from frappe import _dict

from bulkbite.api import _resolve_employee_availability


# =============================================================================
# region KITCHEN PLAN AVAILABILITY PROOF
# =============================================================================


class TestKitchenPlanAvailability(TestCase):
	def test_automatic_employee_uses_the_shared_kitchen_window(self):
		hours, custom = _resolve_employee_availability(
			_dict(available_hours=3, custom_hours=False), 7.5, True, 4
		)

		self.assertEqual(hours, 7.5)
		self.assertFalse(custom)

	def test_custom_employee_keeps_the_manually_entered_hours(self):
		hours, custom = _resolve_employee_availability(
			_dict(available_hours=3.25, custom_hours=True), 7.5, True, 4
		)

		self.assertEqual(hours, 3.25)
		self.assertTrue(custom)

	def test_saved_custom_employee_keeps_availability_during_actual_capture(self):
		hours, custom = _resolve_employee_availability(
			_dict(available_hours=3.25, custom_hours=True), 7.5, False, 4
		)

		self.assertEqual(hours, 3.25)
		self.assertTrue(custom)


# endregion KITCHEN PLAN AVAILABILITY PROOF
