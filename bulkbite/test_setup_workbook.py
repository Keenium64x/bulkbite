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

	def test_recipe_workbook_applies_reviewed_instruction_steps(self):
		suffix = frappe.generate_hash(length=8).upper()
		finished_item = f"MEAL-{suffix}"
		ingredient_item = f"ING-{suffix}"
		file_doc, file_path = self._workbook_file(
			["Recipe Name", "Finished Item Code", "Finished Item Name", "Recipe Output (Kg)", "Row Type", "Ingredient Item Code", "Ingredient Item Name", "Ingredient Quantity", "Ingredient Unit", "Instruction Step", "Instruction Name", "Instruction", "Instruction Ingredient Items", "Instruction Depends On Steps", "Instruction Minimum Workers", "Kitchen Planning Guidance"],
			[
				[f"Instruction recipe {suffix}", finished_item, f"Instruction meal {suffix}", 10, "Ingredient", ingredient_item, f"Instruction ingredient {suffix}", 2.5, "Kg", None, None, None, None, None, None, "Prepare ingredients before heating."],
				[f"Instruction recipe {suffix}", finished_item, f"Instruction meal {suffix}", 10, "Instruction", None, None, None, None, 1, "Prepare", "Measure the ingredient.", ingredient_item, None, 1, "Prepare ingredients before heating."],
				[f"Instruction recipe {suffix}", finished_item, f"Instruction meal {suffix}", 10, "Instruction", None, None, None, None, 2, "Cook", "Cook and verify the finished weight.", ingredient_item, "1", 2, "Prepare ingredients before heating."],
			],
		)
		try:
			stock_before = frappe.db.count("BulkBite Stock Event")
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"]["error"], 0)
			self.assertEqual(len(preview["recipes"][0]["instruction_steps"]), 2)
			applied = apply_workspace_import(preview["name"])
			recipe_name = applied["result"]["inserted"][0]
			recipe = frappe.get_doc("BulkBite Recipe", recipe_name)
			self.assertEqual([step.step_number for step in recipe.instruction_steps], [1, 2])
			self.assertEqual(recipe.instruction_guidance, "Prepare ingredients before heating.")
			self.assertEqual(frappe.db.count("BulkBite Stock Event"), stock_before)
		finally:
			if file_path.exists():
				file_path.unlink()

	def test_recipe_instruction_dependency_must_exist(self):
		suffix = frappe.generate_hash(length=8).upper()
		file_doc, file_path = self._workbook_file(
			["Recipe Name", "Finished Item Code", "Finished Item Name", "Recipe Output (Kg)", "Row Type", "Ingredient Item Code", "Ingredient Item Name", "Ingredient Quantity", "Ingredient Unit", "Instruction Step", "Instruction Name", "Instruction", "Instruction Depends On Steps"],
			[
				[f"Dependency recipe {suffix}", f"MEAL-{suffix}", f"Dependency meal {suffix}", 10, "Ingredient", f"ING-{suffix}", f"Dependency ingredient {suffix}", 2, "Kg", None, None, None, None],
				[f"Dependency recipe {suffix}", f"MEAL-{suffix}", f"Dependency meal {suffix}", 10, "Instruction", None, None, None, None, 1, "Cook", "Cook the meal.", "9"],
			],
		)
		try:
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"]["error"], 1)
			self.assertIn("dependencies do not exist", " ".join(preview["recipes"][0]["instruction_steps"][0]["errors"]))
		finally:
			if file_path.exists():
				file_path.unlink()

	def test_legacy_recipe_update_preserves_existing_instructions(self):
		recipe = frappe.get_doc("BulkBite Recipe", "BB-RECIPE-00004")
		if not recipe.instruction_steps:
			self.skipTest("The local demo recipe has no instruction steps.")
		original_steps = [step.step_name for step in recipe.instruction_steps]
		ingredient = recipe.ingredients[0]
		file_doc, file_path = self._workbook_file(
			["Recipe ID", "Recipe Name", "Finished Item Code", "Recipe Output (Kg)", "Ingredient Item Code", "Ingredient Quantity", "Ingredient Unit"],
			[[recipe.name, recipe.recipe_name, recipe.finished_item, recipe.nominal_output_qty, ingredient.item_code, ingredient.qty, ingredient.uom]],
		)
		try:
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"]["error"], 0)
			apply_workspace_import(preview["name"])
			self.assertEqual([step.step_name for step in frappe.get_doc("BulkBite Recipe", recipe.name).instruction_steps], original_steps)
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

	def test_master_workbook_finds_recipe_costing_and_groups_all_recipes(self):
		workbook = Workbook()
		workbook.active.title = "Dashboard"
		ingredients = workbook.create_sheet("Ingredients")
		ingredients.append(["BULKBITE INGREDIENTS"])
		ingredients.append(["Current source"])
		ingredients.append(["Ingredient", "Unit"])
		ingredients.append(["Sunflower Oil", "L"])
		ingredients.append(["Rice", "kg"])
		recipes = workbook.create_sheet("Recipe_Costing")
		recipes.append(["BULKBITE RECIPE COSTING"])
		recipes.append(["Quantities per 100 kg"])
		recipes.append(["Meal", "Ingredient", "Qty / 100 kg", "Unit", "Price / Unit"])
		recipes.append(["Meal A", "Sunflower Oil", 1.5, "kg", 20])
		recipes.append(["Meal A", "Rice", 15, "kg", 10])
		recipes.append(["Meal B", "Rice", 20, "kg", 10])
		file_doc, file_path = self._saved_workbook(workbook)
		try:
			inspection = inspect_workspace_file("recipes", file_doc.file_url)
			self.assertEqual(inspection["source_sheet"], "Recipe_Costing")
			self.assertEqual(inspection["header_row"], 3)
			self.assertEqual(inspection["suggested_mapping"]["Ingredient Unit"], "ingredient_uom")
			preview = preview_workspace_import("recipes", file_doc.file_url, inspection["suggested_mapping"])
			self.assertEqual(preview["counts"]["total"], 2)
			self.assertEqual(preview["counts"]["error"], 0)
			self.assertEqual(preview["recipes"][0]["nominal_output_qty"], 100)
			oil = next(row for row in preview["recipes"][0]["ingredients"] if row["item_name"] == "Sunflower Oil")
			self.assertEqual(oil["uom"], "Litre")
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
		return self._saved_workbook(workbook)

	def _saved_workbook(self, workbook):
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
