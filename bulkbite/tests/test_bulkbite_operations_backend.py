from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from unittest import TestCase

# =============================================================================
# region DYSIUM BACKEND PROOF
# =============================================================================


class FakeFrappe(types.ModuleType):
	def __init__(self):
		super().__init__("frappe")
		self.session = SimpleNamespace(user="Administrator")
		self.allowed_roles = []

	def only_for(self, roles):
		self.allowed_roles.append(tuple(roles))

	def throw(self, message):
		raise ValueError(message)

	def whitelist(self, **_options):
		def decorator(fn):
			return fn
		return decorator


def install_fake_frappe():
	frappe = FakeFrappe()
	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		doctype = None

	document.Document = Document
	frappe.model = model
	model.document = document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return frappe


class BulkBiteOperationsBackendProof(TestCase):
	def setUp(self):
		self.frappe = install_fake_frappe()
		for name in list(sys.modules):
			if name.startswith("bulkbite.dysium") or name.startswith("bulkbite.bulkbite.doctype.bulkbite_operations"):
				sys.modules.pop(name)
		self.services = importlib.import_module("bulkbite.dysium_services")
		self.validation = importlib.import_module("bulkbite.dysium_validation")

	def test_permission_boundaries(self):
		result = self.services.bulkbite_operations_permission_service(user="worker@example.com")

		self.assertTrue(result["allowed"])
		self.assertEqual(result["roles"], ["System Manager"])
		self.assertIn(("System Manager",), self.frappe.allowed_roles)

	def test_command_idempotency_and_calculations(self):
		payload = {
			"stock": {
				"opening_stock": 10,
				"approved_receipts": 5,
				"approved_production_usage": 3,
				"physical_count": 11,
				"approved_stock_events": [{"quantity": 4}, {"amount": 6}],
				"variance_threshold": 0,
			}
		}

		first = self.services.bulkbite_operations_command_service(**payload)
		second = self.services.bulkbite_operations_command_service(**payload)

		self.assertEqual(first, second)
		self.assertEqual(first["result"]["closing_stock"], 12.0)
		self.assertEqual(first["result"]["reconciliation_variance"], -1.0)
		self.assertEqual(first["result"]["export_total"], 10.0)
		self.assertTrue(first["result"]["manager_exceptions"])

	def test_ai_extraction_is_proposal_only(self):
		proposal = self.services.bulkbite_operations_ai_extraction_proposal_service(
			source="receipt.pdf",
			field_values={"supplier": "Bulk Supplier", "total": 125},
			confidence_notes="OCR matched supplier and total.",
		)

		self.assertEqual(proposal["status"], "proposal")
		self.assertFalse(proposal["posts_records"])
		self.assertEqual(proposal["field_values"]["total"], 125)

	def test_review_approval_gates_deterministic_submit(self):
		rejected = self.services.bulkbite_operations_review_decision_service(
			reference_doctype="BulkBite Operations Extracted Draft",
			reference_name="DRAFT-1",
			decision="rejected",
		)
		approved = self.services.bulkbite_operations_deterministic_submit_service(
			reference_doctype="BulkBite Operations Extracted Draft",
			reference_name="DRAFT-1",
			decision="approved",
			stock={"opening_stock": 2, "approved_receipts": 3},
		)

		self.assertFalse(rejected["posts_records"])
		self.assertTrue(approved["decision"]["posts_records"])
		self.assertEqual(approved["stock"]["closing_stock"], 5.0)

	def test_schema_validation_rejects_malformed_ai_output(self):
		doc = SimpleNamespace(doctype="BulkBite Operations Extracted Draft", upload_batch="UPLOAD-1", field_values="{bad", validation_errors=None)

		with self.assertRaises(ValueError):
			self.validation.validate_json_fields(doc, ["field_values"])

	def test_required_headers_are_validated(self):
		result = self.services.bulkbite_operations_import_template_service(
			required_headers=["item", "quantity", "uom"],
			supplied_headers=["item", "quantity"],
		)

		self.assertFalse(result["valid"])
		self.assertEqual(result["missing"], ["uom"])

	def test_row_preview_does_not_commit_records(self):
		result = self.services.bulkbite_operations_import_preview_service(
			required_headers=["item", "quantity"],
			rows=[{"item": "flour", "quantity": 2}, {"item": "sugar"}],
		)

		self.assertFalse(result["committed"])
		self.assertEqual(result["rows"][0]["row_status"], "valid")
		self.assertEqual(result["rows"][1]["row_status"], "invalid")

	def test_commit_returns_created_skipped_and_error_counts(self):
		result = self.services.bulkbite_operations_import_commit_service(
			rows=[
				{"row_status": "valid"},
				{"row_status": "valid"},
				{"row_status": "skipped"},
				{"row_status": "invalid"},
			]
		)

		self.assertEqual(result, {"created": 2, "skipped": 1, "errors": 1})

	def test_frontend_pages_must_not_decide_business_validity(self):
		query = self.services.bulkbite_operations_query_service(stock={"opening_stock": 1})

		self.assertEqual(query["status"], "ready")
		self.assertIn("stock", query)
		self.assertNotIn("ledger_posting_rules", query)

	def test_all_state_transitions_belong_in_backend_services_or_doctype_controllers(self):
		with self.assertRaises(ValueError):
			self.services.bulkbite_operations_command_service(action="frontend-post")

	def test_protected_history_and_audit_events_are_explicit_backend_concerns(self):
		event = self.services.audit_event_service(event_type="approval", subject="DRAFT-1", payload={"decision": "approved"})

		self.assertEqual(event["event_type"], "approval")
		self.assertEqual(event["payload"]["decision"], "approved")

	def test_doctype_required_field_validation(self):
		doc = SimpleNamespace(doctype="BulkBite Operations Task", title="")

		with self.assertRaises(ValueError):
			self.validation.require_fields(doc, ["title"])

	def test_doctype_status_and_decision_validation(self):
		self.validation.validate_status(SimpleNamespace(doctype="BulkBite Operations Task", status="Approved"))
		self.validation.validate_decision(SimpleNamespace(doctype="BulkBite Operations Review Decision", decision="rejected"))

		with self.assertRaises(ValueError):
			self.validation.validate_decision(SimpleNamespace(doctype="BulkBite Operations Review Decision", decision="maybe"))


# endregion DYSIUM BACKEND PROOF
