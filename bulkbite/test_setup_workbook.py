from io import BytesIO
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from openpyxl import Workbook

from bulkbite.setup_workbook import apply_workspace_import, get_workspace_contract, inspect_workspace_file, preview_workspace_import


# =============================================================================
# region CONTROLLED SPREADSHEET WORKSPACE PROOF
# =============================================================================


class TestControlledSpreadsheetWorkspace(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def test_recipe_workbook_previews_new_items_then_applies_without_stock(self):
		suffix = frappe.generate_hash(length=8).upper()
		finished_item = f"MEAL-{suffix}"
		ingredient_item = f"ING-{suffix}"
		file_doc, file_path = self._workbook_file(
			["Recipe Name", "Finished Item Code", "Finished Item Name", "Recipe Output (Kg)", "Ingredient Item Code", "Ingredient Item Name", "Ingredient Quantity"],
			[[f"Proof recipe {suffix}", finished_item, f"Proof meal {suffix}", 10, ingredient_item, f"Proof ingredient {suffix}", 2.5]],
		)
		try:
			stock_before = frappe.db.count("BulkBite Stock Event")
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"], {"total": 1, "insert": 1, "update": 0, "unchanged": 0, "error": 0})

			applied = apply_workspace_import(preview["name"])
			self.assertEqual(applied["status"], "Applied")
			self.assertTrue(frappe.db.exists("BulkBite Item", finished_item))
			self.assertTrue(frappe.db.exists("BulkBite Item", ingredient_item))
			self.assertEqual(frappe.db.count("BulkBite Stock Event"), stock_before)
		finally:
			if file_path.exists():
				file_path.unlink()

	def test_new_recipe_item_without_name_is_blocked_in_review(self):
		file_doc, file_path = self._workbook_file(
			["Recipe Name", "Finished Item Code", "Recipe Output (Kg)", "Ingredient Item Code", "Ingredient Quantity"],
			[["Incomplete recipe", f"MEAL-{frappe.generate_hash(length=8)}", 10, f"ING-{frappe.generate_hash(length=8)}", 2]],
		)
		try:
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"]["error"], 1)
			self.assertIn("Finished Item Name is required", " ".join(preview["recipes"][0]["errors"]))
		finally:
			if file_path.exists():
				file_path.unlink()

	def test_advanced_setup_targets_are_allowlisted(self):
		contract = get_workspace_contract("setup")
		self.assertIn("BulkBite Employee", {row["value"] for row in contract["setup_targets"]})
		with self.assertRaises(frappe.PermissionError):
			get_workspace_contract("setup", "User")

	def _workbook_file(self, headers, rows):
		workbook = Workbook()
		sheet = workbook.active
		sheet.append(headers)
		for row in rows:
			sheet.append(row)
		stream = BytesIO()
		workbook.save(stream)
		file_doc = frappe.get_doc({
			"doctype": "File",
			"file_name": f"spreadsheet-workspace-proof-{frappe.generate_hash(length=8)}.xlsx",
			"is_private": 1,
			"content": stream.getvalue(),
		}).insert()
		return file_doc, Path(file_doc.get_full_path())


# endregion CONTROLLED SPREADSHEET WORKSPACE PROOF
