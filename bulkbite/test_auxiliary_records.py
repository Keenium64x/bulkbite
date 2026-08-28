from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from bulkbite.api import (
	_auxiliary_deletion_plan,
	delete_auxiliary_records,
)


class TestAuxiliaryRecordDeletion(TestCase):
	def document(self, doctype, name):
		return frappe._dict(
			doctype=doctype,
			name=name,
			docstatus=0,
			supplier_name=name if doctype == "BulkBite Supplier" else None,
			offer_name=name if doctype == "BulkBite Supplier Offer" else None,
			has_permission=lambda permission: True,
			get=lambda fieldname: name,
		)

	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._auxiliary_title_field", return_value=None)
	@patch("bulkbite.api.frappe.get_meta")
	@patch("bulkbite.api._auxiliary_delete_links")
	@patch("bulkbite.api._load_auxiliary_delete_document")
	def test_plan_orders_managed_dependency_before_selected_root(self, load_doc, links, _meta, _title, _reason):
		_meta.return_value.get_field.return_value = frappe._dict(reqd=0)
		load_doc.side_effect = lambda doctype, name: (self.document(doctype, name), None)
		links.side_effect = lambda doc: [{
			"doctype": "BulkBite Supplier Offer",
			"name": "OFFER-1",
			"field": "supplier",
			"field_label": "Supplier",
			"storage_doctype": "BulkBite Supplier Offer",
			"storage_names": ["OFFER-1"],
		}] if doc.doctype == "BulkBite Supplier" else []
		plan = _auxiliary_deletion_plan("BulkBite Supplier", ["SUP-1"])
		self.assertEqual(plan.delete_order[0]["name"], "OFFER-1")
		self.assertEqual(plan.delete_order[-1]["name"], "SUP-1")
		self.assertEqual(plan.public["dependencies"][0]["linked_by"][0]["field_label"], "Supplier")
		self.assertTrue(plan.public["plan_token"])

	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._auxiliary_title_field", return_value=None)
	@patch("bulkbite.api.frappe.get_meta")
	@patch("bulkbite.api._auxiliary_delete_links")
	@patch("bulkbite.api._load_auxiliary_delete_document")
	def test_plan_blocks_unmanaged_operational_reference(self, load_doc, links, _meta, _title, _reason):
		_meta.return_value.get_field.return_value = frappe._dict(reqd=0)
		def load(doctype, name):
			if doctype == "BulkBite Receipt Intake":
				return None, "This connected record belongs to operational history."
			return self.document(doctype, name), None
		load_doc.side_effect = load
		links.side_effect = lambda doc: [{
			"doctype": "BulkBite Receipt Intake",
			"name": "REC-1",
			"field": "supplier",
			"field_label": "Supplier",
			"storage_doctype": "BulkBite Receipt Intake",
			"storage_names": ["REC-1"],
		}] if doc.doctype == "BulkBite Supplier" else []
		plan = _auxiliary_deletion_plan("BulkBite Supplier", ["SUP-1"])
		self.assertEqual(plan.public["blockers"][0]["doctype"], "BulkBite Receipt Intake")

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._", side_effect=lambda message: message)
	@patch("bulkbite.api.frappe.throw", side_effect=frappe.PermissionError("Final deletion approval is required."))
	def test_executor_requires_explicit_final_approval(self, _throw, _translate, _require):
		with self.assertRaises(frappe.PermissionError):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "token", approved=False)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._", side_effect=lambda message: message)
	@patch("bulkbite.api.frappe.throw", side_effect=frappe.ValidationError)
	@patch("bulkbite.api._auxiliary_deletion_plan")
	def test_executor_rejects_a_stale_plan_token(self, deletion_plan, _throw, _translate, _require):
		deletion_plan.return_value = frappe._dict(public={"plan_token": "fresh"})
		with self.assertRaises(frappe.ValidationError):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "stale", outcome="unlink", approved=True)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._", side_effect=lambda message: message)
	@patch("bulkbite.api.frappe.throw", side_effect=frappe.ValidationError)
	def test_executor_requires_an_explicit_outcome(self, _throw, _translate, _require):
		with self.assertRaises(frappe.ValidationError):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "fresh", approved=True)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._clear_auxiliary_delete_plan_links")
	@patch("bulkbite.api.frappe.delete_doc", side_effect=RuntimeError("delete failed"))
	@patch("bulkbite.api.frappe.get_doc")
	@patch("bulkbite.api.frappe.db", new_callable=MagicMock)
	@patch("bulkbite.api._auxiliary_deletion_plan")
	def test_executor_rolls_back_the_complete_plan_on_failure(self, deletion_plan, database, get_doc, _delete, _clear, _reason, _require):
		doc = frappe._dict(check_permission=lambda permission: True)
		get_doc.return_value = doc
		node = {"doctype": "BulkBite Supplier", "name": "SUP-1", "title": "Supplier"}
		deletion_plan.return_value = frappe._dict(
			public={"roots": [node], "plan_token": "fresh", "outcomes": {"recursive": {"allowed": True}}},
			delete_edges=[],
			unlink_edges=[],
			delete_order=[node],
		)
		with self.assertRaisesRegex(RuntimeError, "delete failed"):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "fresh", outcome="recursive", approved=True)
		database.rollback.assert_called_once_with(save_point="bulkbite_auxiliary_record_deletion")

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._unlink_auxiliary_delete_plan")
	@patch("bulkbite.api.frappe.delete_doc")
	@patch("bulkbite.api.frappe.get_doc")
	@patch("bulkbite.api.frappe.db", new_callable=MagicMock)
	@patch("bulkbite.api._auxiliary_deletion_plan")
	def test_unlink_deletes_only_roots_and_preserves_dependencies(self, deletion_plan, _database, get_doc, delete_doc, unlink, _reason, _require):
		get_doc.return_value = frappe._dict(check_permission=lambda permission: True)
		root = {"doctype": "BulkBite Supplier", "name": "SUP-1", "title": "Supplier"}
		dependency = {"doctype": "BulkBite Supplier Offer", "name": "OFFER-1", "title": "Offer"}
		edge = {"from": ("BulkBite Supplier", "SUP-1"), "to": ("BulkBite Supplier Offer", "OFFER-1")}
		deletion_plan.return_value = frappe._dict(
			public={"roots": [root], "dependencies": [dependency], "plan_token": "fresh", "outcomes": {"unlink": {"allowed": True}}},
			delete_edges=[edge],
			unlink_edges=[edge],
			delete_order=[dependency, root],
		)
		result = delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "fresh", outcome="unlink", approved=True)
		unlink.assert_called_once_with([edge])
		delete_doc.assert_called_once_with("BulkBite Supplier", "SUP-1")
		self.assertEqual(result["dependency_count"], 0)
