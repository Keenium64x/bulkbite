from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bulkbite.api import _assert_offline_version, sync_offline_mutation


# =============================================================================
# region OFFLINE SYNCHRONIZATION PROOF
# =============================================================================


class TestOfflineSynchronization(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def test_completed_mutation_replays_the_saved_result_exactly_once(self):
		mutation_id = self._mutation_id("replay")
		with patch("bulkbite.api._apply_offline_draft", return_value={"name": "DRAFT-001"}) as apply_draft:
			first = sync_offline_mutation(mutation_id, "save_production_draft", {"name": "DRAFT-001"})
			second = sync_offline_mutation(mutation_id, "save_production_draft", {"name": "DRAFT-001"})

		self.assertEqual(second, first)
		apply_draft.assert_called_once()

	def test_mutation_id_cannot_be_reused_with_another_payload(self):
		mutation_id = self._mutation_id("payload")
		with patch("bulkbite.api._apply_offline_draft", return_value={"name": "DRAFT-002"}):
			sync_offline_mutation(mutation_id, "save_production_draft", {"name": "DRAFT-002"})

		with self.assertRaises(frappe.PermissionError):
			sync_offline_mutation(mutation_id, "save_production_draft", {"name": "DIFFERENT-DRAFT"})

	def test_conflict_contains_mutable_server_fields(self):
		category = frappe.get_doc({
			"doctype": "BulkBite Item Category",
			"category_name": f"Offline conflict {frappe.generate_hash(length=8)}",
			"enabled": 1,
		}).insert()

		with self.assertRaises(frappe.TimestampMismatchError) as conflict:
			_assert_offline_version(category.doctype, category.name, "2000-01-01 00:00:00", False)

		message = str(conflict.exception)
		self.assertIn("CONFLICT:", message)
		self.assertIn('"server_modified"', message)
		self.assertIn('"category_name"', message)
		self.assertNotIn('"modified_by"', message)

	def test_failed_mutation_keeps_a_retryable_failure_record(self):
		mutation_id = self._mutation_id("failure")
		with (
			patch("bulkbite.api._apply_offline_draft", side_effect=frappe.ValidationError("Proof failure")),
			patch.object(frappe.db, "commit") as commit,
		):
			with self.assertRaises(frappe.ValidationError):
				sync_offline_mutation(mutation_id, "save_production_draft", {"name": "DRAFT-FAIL"})

			failure = frappe.db.get_value("BulkBite Offline Mutation", mutation_id, ["status", "result_json"], as_dict=True)

		self.assertEqual(failure.status, "Failed")
		self.assertIn("Proof failure", failure.result_json)
		commit.assert_called_once()

	def test_posting_operations_are_never_available_offline(self):
		with self.assertRaises(frappe.PermissionError):
			sync_offline_mutation(self._mutation_id("posting"), "receive_stock_from_receipt", {"name": "RECEIPT"})

	def test_ad_hoc_production_draft_uses_the_safe_draft_pipeline(self):
		payload = {
			"direction_action": "Off Plan",
			"recipe": "RECIPE-001",
			"planned_output_qty": 20,
			"actual_output_qty": 18,
			"production_date": "2026-08-29",
			"source_location": "Ingredients",
			"target_location": "Finished Meals",
			"ingredients": [],
			"employees": [],
		}
		with (
			patch("bulkbite.api.create_ad_hoc_production_run", return_value={"name": "AD-HOC-DRAFT"}) as create,
			patch("bulkbite.api.update_production_actuals", return_value={"name": "AD-HOC-DRAFT"}) as measure,
			patch("bulkbite.api.save_production_employees", return_value={"name": "AD-HOC-DRAFT"}) as save_team,
		):
			result = sync_offline_mutation(self._mutation_id("ad-hoc"), "save_production_draft", payload)

		self.assertEqual(result["result"]["name"], "AD-HOC-DRAFT")
		create.assert_called_once_with("RECIPE-001", 20, "2026-08-29", "Ingredients", "Finished Meals")
		measure.assert_called_once()
		save_team.assert_called_once()

	def _mutation_id(self, suffix):
		return f"proof-{suffix}-{frappe.generate_hash(length=12)}"


# endregion OFFLINE SYNCHRONIZATION PROOF
