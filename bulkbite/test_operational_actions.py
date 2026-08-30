from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from bulkbite.operational_actions import build_operational_action_snapshot


class TestOperationalNextAction(TestCase):
	def test_overdue_recurring_work_has_priority_over_buying_and_production(self):
		calendar = {
			"actions": [SimpleNamespace(display_status="Missed", title="Stock count", action_type="Stock Reconciliation", consequence_note="Count stock.", due_date="2026-08-01", target_section="stock")],
			"counts": {},
		}
		containers = {"overdue": 0}
		plan = {
			"buying": {"lines": [{"supplier": "Makro", "shortage_qty": 2}], "suppliers": [{"supplier": "Makro", "production_date": "2026-09-05", "order_by_date": "2026-09-01"}]},
			"next_production": {"row": {"planned_output_qty": 20}},
		}
		with patch("bulkbite.operational_actions.get_operational_calendar_snapshot", return_value=calendar), patch("bulkbite.operational_actions.get_container_position_snapshot", return_value=containers):
			result = build_operational_action_snapshot(plan)

		self.assertEqual(result["primary"]["title"], "Stock count")
		self.assertEqual(result["primary"]["severity"], "overdue")

	def test_empty_queue_reports_operations_on_track(self):
		calendar = {"actions": [], "counts": {}}
		containers = {"overdue": 0}
		with patch("bulkbite.operational_actions.get_operational_calendar_snapshot", return_value=calendar), patch("bulkbite.operational_actions.get_container_position_snapshot", return_value=containers):
			result = build_operational_action_snapshot({})

		self.assertEqual(result["primary"]["severity"], "ready")
		self.assertEqual(result["primary"]["title"], "Operations are on track")
