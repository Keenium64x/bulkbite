from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from bulkbite.kitchen_assignment import (
	_assigned_employee,
	_link_status,
	_restricted_instruction_projection,
	_token_hash,
	generate_kitchen_assignment_link,
)


# =============================================================================
# region KITCHEN ASSIGNMENT SECURITY PROOF
# =============================================================================

class TestKitchenAssignmentLinks(TestCase):
	def test_link_status_distinguishes_active_expired_and_revoked(self):
		active = SimpleNamespace(expires_at="2026-09-07 12:00:00", revoked_at=None)
		expired = SimpleNamespace(expires_at="2026-08-30 12:00:00", revoked_at=None)
		revoked = SimpleNamespace(expires_at="2026-09-07 12:00:00", revoked_at="2026-08-31 12:00:00")
		self.assertEqual(_link_status(active, "2026-08-31 12:00:00"), "Active")
		self.assertEqual(_link_status(expired, "2026-08-31 12:00:00"), "Expired")
		self.assertEqual(_link_status(revoked, "2026-08-31 12:00:00"), "Revoked")

	def test_employee_must_still_be_assigned_to_the_run(self):
		run = SimpleNamespace(employees=[])
		with (
			patch("bulkbite.kitchen_assignment.frappe.get_doc", return_value=run),
			patch("bulkbite.kitchen_assignment.frappe.throw", side_effect=ValueError("not assigned")),
			self.assertRaisesRegex(ValueError, "not assigned"),
		):
			_assigned_employee("RUN-001", "EMP-001")

	def test_generated_token_is_returned_once_and_only_its_hash_is_stored(self):
		stored = {}
		link = SimpleNamespace(
			employee="EMP-001",
			creation="2026-08-31 12:00:00",
			expires_at="2026-09-07 12:00:00",
			revoked_at=None,
		)

		def capture_link(payload):
			stored.update(payload)
			link.insert = MagicMock()
			return link

		with (
			patch("bulkbite.kitchen_assignment._require_manager"),
			patch("bulkbite.kitchen_assignment._assigned_employee", return_value=(SimpleNamespace(name="RUN-001", docstatus=0), SimpleNamespace(employee_name="Keenan"))),
			patch("bulkbite.kitchen_assignment._revoke_active_links") as revoke,
			patch("bulkbite.kitchen_assignment.now_datetime", return_value="2026-08-31 12:00:00"),
			patch("bulkbite.kitchen_assignment.add_days", return_value="2026-09-07 12:00:00"),
			patch("bulkbite.kitchen_assignment.frappe.get_doc", side_effect=capture_link),
		):
			result = generate_kitchen_assignment_link("RUN-001", "EMP-001")

		raw_token = result["path"].split("#", 1)[-1]
		self.assertEqual(result["path"].split("#", 1)[0], "/bulkbite/kitchen-assignment")
		self.assertNotEqual(raw_token, stored["token_hash"])
		self.assertEqual(stored["token_hash"], _token_hash(raw_token))
		self.assertNotIn("token", stored)
		self.assertNotIn(raw_token, str(stored))
		revoke.assert_called_once_with("RUN-001", "EMP-001", revoked_at="2026-08-31 12:00:00")
		link.insert.assert_called_once_with(ignore_permissions=True)

	def test_worker_projection_excludes_other_lanes_and_manager_data(self):
		instructions = {
			"estimated_elapsed_minutes": 90,
			"critical_path_minutes": 80,
			"warnings": [],
			"ingredients": [{"item_code": "RICE", "item_name": "Rice", "quantity": 5, "uom": "Kg", "supplier_price": 999}],
			"equipment": [{"name": "POT", "equipment_type_name": "Pot", "capacity_qty": 10, "capacity_uom": "Kg", "private_notes": "manager only"}],
			"steps": [{"task_id": "cook", "step_number": 1, "step_name": "Cook rice", "instruction": "Cook it", "assigned_workers": [1, 2], "manager_notes": "hidden"}],
			"worker_lanes": [{"lane": 1}, {"lane": 2}],
			"stock": {"available": 50},
		}

		result = _restricted_instruction_projection(instructions)

		self.assertNotIn("worker_lanes", result)
		self.assertNotIn("stock", result)
		self.assertNotIn("supplier_price", result["ingredients"][0])
		self.assertNotIn("private_notes", result["equipment"][0])
		self.assertNotIn("assigned_workers", result["steps"][0])
		self.assertNotIn("manager_notes", result["steps"][0])


# endregion KITCHEN ASSIGNMENT SECURITY PROOF
