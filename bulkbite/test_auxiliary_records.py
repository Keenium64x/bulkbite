from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from bulkbite.api import (
	_archive_auxiliary_setup_record,
	_auxiliary_deletion_plan,
	_resolve_auxiliary_delete_execution,
	delete_auxiliary_records,
)


class TestAuxiliaryRecordDeletion(TestCase):
	def document(self, doctype, name):
		return frappe._dict(
			doctype=doctype,
			name=name,
			docstatus=0,
			has_permission=lambda permission: True,
			get=lambda fieldname: name,
		)

	def node(self, doctype, name, root=False, managed=True, preserve_reason=None):
		return {
			"doctype": doctype,
			"name": name,
			"title": name,
			"root": root,
			"managed": managed,
			"docstatus": 0,
			"can_write": managed,
			"can_delete": managed and not preserve_reason,
			"preserve_reason": preserve_reason,
		}

	def edge(self, source, target):
		return {
			"from": source,
			"to": target,
			"field": "supplier",
			"field_label": "Supplier",
			"storage_doctype": target[0],
			"storage_names": [target[1]],
		}

	def plan(self, nodes, edges, order=None, blockers=None):
		return frappe._dict(
			public={"roots": [node for node in nodes.values() if node.get("root")], "blockers": blockers or []},
			nodes=nodes,
			delete_edges=edges,
			delete_order=order or list(nodes.values()),
		)

	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._auxiliary_title_field", return_value=None)
	@patch("bulkbite.api._auxiliary_delete_links")
	@patch("bulkbite.api._load_auxiliary_delete_document")
	def test_plan_orders_managed_dependency_before_selected_root(self, load_doc, links, _title, _reason):
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

	@patch("bulkbite.api._auxiliary_edge_unlink_blocker", return_value=None)
	def test_delete_removes_mutable_dependency_child_first(self, _blocker):
		root_key = ("BulkBite Supplier", "SUP-1")
		child_key = ("BulkBite Supplier Offer", "OFFER-1")
		root = self.node(*root_key, root=True)
		child = self.node(*child_key)
		resolution = _resolve_auxiliary_delete_execution(
			self.plan({root_key: root, child_key: child}, [self.edge(root_key, child_key)], [child, root]),
			"delete",
		)
		self.assertEqual([node["name"] for node in resolution.delete_order], ["OFFER-1", "SUP-1"])
		self.assertFalse(resolution.archived)

	@patch("bulkbite.api._auxiliary_edge_unlink_blocker", return_value=None)
	def test_per_type_unlink_preserves_dependency_and_deletes_root(self, _blocker):
		root_key = ("BulkBite Supplier", "SUP-1")
		child_key = ("BulkBite Supplier Offer", "OFFER-1")
		root = self.node(*root_key, root=True)
		child = self.node(*child_key)
		edge = self.edge(root_key, child_key)
		resolution = _resolve_auxiliary_delete_execution(
			self.plan({root_key: root, child_key: child}, [edge], [child, root]),
			"delete",
			{"BulkBite Supplier Offer": "unlink"},
		)
		self.assertEqual([node["name"] for node in resolution.delete_order], ["SUP-1"])
		self.assertEqual(resolution.unlink_edges, [edge])
		self.assertIn(child, resolution.preserved)

	@patch("bulkbite.api.frappe.throw", side_effect=frappe.ValidationError)
	def test_unknown_related_type_override_is_rejected(self, _throw):
		root_key = ("BulkBite Supplier", "SUP-1")
		root = self.node(*root_key, root=True)
		with self.assertRaises(frappe.ValidationError):
			_resolve_auxiliary_delete_execution(
				self.plan({root_key: root}, []),
				"delete",
				{"Unknown Record Type": "unlink"},
			)

	@patch("bulkbite.api._auxiliary_edge_unlink_blocker")
	def test_immutable_reference_archives_identity_but_allows_mutable_cleanup(self, unlink_blocker):
		root_key = ("BulkBite Supplier", "SUP-1")
		offer_key = ("BulkBite Supplier Offer", "OFFER-1")
		receipt_key = ("BulkBite Receipt Intake", "REC-1")
		root = self.node(*root_key, root=True)
		offer = self.node(*offer_key)
		receipt = self.node(*receipt_key, managed=False, preserve_reason="Operational history")
		offer_edge = self.edge(root_key, offer_key)
		receipt_edge = self.edge(root_key, receipt_key)
		unlink_blocker.side_effect = lambda edge, nodes: "Operational history keeps its reference" if edge["to"] == receipt_key else None
		resolution = _resolve_auxiliary_delete_execution(
			self.plan({root_key: root, offer_key: offer, receipt_key: receipt}, [offer_edge, receipt_edge], [offer, receipt, root]),
			"delete",
		)
		self.assertEqual([node["name"] for node in resolution.delete_order], ["OFFER-1"])
		self.assertEqual([node["name"] for node in resolution.archived], ["SUP-1"])
		self.assertIn(receipt, resolution.preserved)
		self.assertNotIn(receipt_edge, resolution.unlink_edges)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._", side_effect=lambda message: message)
	@patch("bulkbite.api.frappe.throw", side_effect=frappe.PermissionError("Final deletion approval is required."))
	def test_executor_requires_explicit_final_approval(self, _throw, _translate, _require):
		with self.assertRaises(frappe.PermissionError):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "token", approved=False)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._", side_effect=lambda message: message)
	@patch("bulkbite.api.frappe.throw", side_effect=frappe.ValidationError)
	def test_executor_requires_an_explicit_outcome(self, _throw, _translate, _require):
		with self.assertRaises(frappe.ValidationError):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "fresh", approved=True)

	@patch("bulkbite.api._require_auxiliary_doctype")
	@patch("bulkbite.api._auxiliary_delete_plan_token", return_value="fresh")
	@patch("bulkbite.api._resolve_auxiliary_delete_execution")
	@patch("bulkbite.api._auxiliary_deletion_plan")
	@patch("bulkbite.api._auxiliary_delete_block_reason", return_value=None)
	@patch("bulkbite.api._clear_auxiliary_delete_plan_links")
	@patch("bulkbite.api._unlink_auxiliary_delete_plan")
	@patch("bulkbite.api.frappe.delete_doc", side_effect=RuntimeError("delete failed"))
	@patch("bulkbite.api.frappe.get_doc")
	@patch("bulkbite.api.frappe.db", new_callable=MagicMock)
	def test_executor_rolls_back_complete_plan_on_failure(self, database, get_doc, _delete, _unlink, _clear, _reason, deletion_plan, resolve, _token, _require):
		get_doc.return_value = frappe._dict(check_permission=lambda permission: True)
		node = self.node("BulkBite Supplier", "SUP-1", root=True)
		deletion_plan.return_value = frappe._dict(public={"roots": [node], "blockers": []})
		resolve.return_value = frappe._dict(
			allowed=True, blockers=[], delete_order=[node], delete_edges=[], unlink_edges=[],
			archived=[], preserved=[], outcomes_by_doctype={}, default_outcome="delete",
		)
		with self.assertRaisesRegex(RuntimeError, "delete failed"):
			delete_auxiliary_records("BulkBite Supplier", ["SUP-1"], "fresh", outcome="delete", approved=True)
		database.rollback.assert_called_once_with(save_point="bulkbite_auxiliary_record_deletion")

	@patch("bulkbite.api.frappe.get_meta")
	@patch("bulkbite.api.frappe.get_doc")
	@patch("bulkbite.api.now_datetime", return_value="2026-08-28 12:00:00")
	@patch("bulkbite.api.frappe.db.set_value")
	@patch("bulkbite.api.frappe.db.exists", side_effect=[False, True])
	def test_archive_is_idempotent_and_disables_identity(self, _exists, set_value, _now, get_doc, get_meta):
		get_meta.return_value.get_field.return_value = True
		archive_doc = MagicMock()
		get_doc.return_value = archive_doc
		node = self.node("BulkBite Supplier", "SUP-1")
		_archive_auxiliary_setup_record(node, "Immutable receipt reference")
		_archive_auxiliary_setup_record(node, "Immutable receipt reference")
		archive_doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(set_value.call_count, 2)
