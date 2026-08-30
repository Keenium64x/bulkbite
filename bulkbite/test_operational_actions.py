from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from bulkbite.bulkbite.doctype.bulkbite_container_type.bulkbite_container_type import BulkBiteContainerType
from bulkbite.api import create_custom_operational_action
from bulkbite.operational_actions import _action_configuration, build_operational_action_snapshot, get_default_container_suggestion


class TestOperationalNextAction(TestCase):
	@patch("bulkbite.api.get_operational_calendar_snapshot", return_value={"actions": []})
	@patch("bulkbite.api.frappe.get_doc")
	@patch("bulkbite.api._require_roles")
	def test_custom_action_is_created_as_one_off_calendar_work(self, _require, get_doc, calendar):
		doc = MagicMock(name="BB-OA-2026-00001")
		doc.name = "BB-OA-2026-00001"
		get_doc.return_value.insert.return_value = doc

		result = create_custom_operational_action("Check freezer", "2026-09-02", "Frozen stock may be lost.", "stock", "Count and record temperatures.")

		payload = get_doc.call_args.args[0]
		self.assertEqual(payload["action_type"], "Custom")
		self.assertNotIn("schedule", payload)
		self.assertEqual(payload["target_section"], "stock")
		self.assertEqual(result["action"], "BB-OA-2026-00001")
		self.assertEqual(result["calendar"], {"actions": []})

	def test_recurring_occurrence_configures_its_schedule(self):
		target = _action_configuration(SimpleNamespace(name="ACTION-1", schedule="Monthly accountant export"))

		self.assertEqual(target["doctype"], "BulkBite Operational Schedule")
		self.assertEqual(target["name"], "Monthly accountant export")
		self.assertEqual(target["label"], "Configure schedule")

	def test_one_off_occurrence_configures_the_action_itself(self):
		target = _action_configuration(SimpleNamespace(name="ACTION-2", schedule=None))

		self.assertEqual(target["doctype"], "BulkBite Operational Action")
		self.assertEqual(target["name"], "ACTION-2")
		self.assertEqual(target["label"], "Configure action")

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

	def test_future_calendar_occurrences_wait_until_their_lead_window(self):
		calendar = {
			"actions": [
				SimpleNamespace(display_status="Due", title="Near task", action_type="Custom", consequence_note="Near.", due_date="2026-08-30", target_section="operations", schedule="NEAR"),
				SimpleNamespace(display_status="Due", title="Future task", action_type="Custom", consequence_note="Future.", due_date="2026-09-30", target_section="operations", schedule="FUTURE"),
			],
			"counts": {},
		}
		containers = {"overdue": 0}
		with (
			patch("bulkbite.operational_actions.nowdate", return_value="2026-08-30"),
			patch("bulkbite.operational_actions.frappe.get_cached_value", return_value=4),
			patch("bulkbite.operational_actions.get_operational_calendar_snapshot", return_value=calendar),
			patch("bulkbite.operational_actions.get_container_position_snapshot", return_value=containers),
		):
			result = build_operational_action_snapshot({})

		self.assertEqual([row["title"] for row in result["actions"]], ["Near task"])

	def test_production_action_uses_live_buying_production_date(self):
		calendar = {"actions": [], "counts": {}}
		containers = {"overdue": 0}
		plan = {
			"buying": {"production_date": "2026-09-05"},
			"next_production": {"row": {"planned_output_qty": 20, "planned_date": "2026-08-01"}},
		}
		with patch("bulkbite.operational_actions.get_operational_calendar_snapshot", return_value=calendar), patch("bulkbite.operational_actions.get_container_position_snapshot", return_value=containers):
			result = build_operational_action_snapshot(plan)

		self.assertEqual(result["primary"]["due_date"], "2026-09-05")

	def test_repeated_missed_schedule_occurrences_form_one_recovery_job(self):
		calendar = {
			"actions": [
				SimpleNamespace(name="ACTION-1", display_status="Missed", title="Container review", action_type="Container Reconciliation", consequence_note="Review returns.", due_date="2026-08-07", target_section="operations", schedule="WEEKLY-CONTAINERS"),
				SimpleNamespace(name="ACTION-2", display_status="Missed", title="Container review", action_type="Container Reconciliation", consequence_note="Review returns.", due_date="2026-08-14", target_section="operations", schedule="WEEKLY-CONTAINERS"),
			],
			"counts": {},
		}
		containers = {"overdue": 0}
		with patch("bulkbite.operational_actions.get_operational_calendar_snapshot", return_value=calendar), patch("bulkbite.operational_actions.get_container_position_snapshot", return_value=containers):
			result = build_operational_action_snapshot({})

		self.assertEqual(len(result["actions"]), 1)
		self.assertIn("2 occurrences", result["actions"][0]["reason"])

	def test_default_container_suggestion_rounds_up_without_forcing_the_recorded_count(self):
		with patch("bulkbite.operational_actions.frappe.db.get_value", return_value=SimpleNamespace(name="Standard 750 ml", container_type_name="Standard 750 ml", capacity_qty=0.75, capacity_uom="Kg", stock_item="PACK-750")):
			result = get_default_container_suggestion(5)

		self.assertEqual(result["suggested_count"], 7)
		self.assertEqual(result["implied_average_fill_qty"], 0.714)


class TestContainerTypeRules(TestCase):
	def test_stock_identity_requires_packaging_measured_in_each(self):
		doc = SimpleNamespace(stock_item="INGREDIENT")
		with patch("bulkbite.bulkbite.doctype.bulkbite_container_type.bulkbite_container_type.frappe.get_cached_value", return_value=("Ingredient", "Kg")):
			with self.assertRaises(frappe.ValidationError):
				BulkBiteContainerType._validate_stock_identity(doc)

	def test_only_one_enabled_default_container_is_allowed(self):
		doc = SimpleNamespace(name="Second container", default_for_production=1, enabled=1)
		with patch("bulkbite.bulkbite.doctype.bulkbite_container_type.bulkbite_container_type.frappe.db.exists", return_value="Standard container"):
			with self.assertRaises(frappe.ValidationError):
				BulkBiteContainerType._validate_default_for_production(doc)
