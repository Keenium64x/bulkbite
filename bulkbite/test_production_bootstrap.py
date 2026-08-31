import unittest

from bulkbite.production_bootstrap import ITEM_ALIASES, RECIPE_INGREDIENTS, RECIPE_STEPS, canonical_item_code


# =============================================================================
# region PRODUCTION BASELINE PROOF
# =============================================================================


class ProductionBaselineProof(unittest.TestCase):
	def test_all_historical_recipe_item_codes_resolve_to_canonical_catalogue_codes(self):
		for ingredients in RECIPE_INGREDIENTS.values():
			for item_code, quantity in ingredients:
				self.assertTrue(canonical_item_code(item_code))
				self.assertGreater(quantity, 0)
		self.assertEqual(len(ITEM_ALIASES), len(set(ITEM_ALIASES.values())))

	def test_each_recipe_has_a_connected_numbered_instruction_method(self):
		self.assertEqual(set(RECIPE_STEPS), set(RECIPE_INGREDIENTS))
		for recipe_name, steps in RECIPE_STEPS.items():
			numbers = [step[0] for step in steps]
			self.assertEqual(numbers, list(range(1, len(steps) + 1)), recipe_name)
			known = set(numbers)
			for step in steps:
				dependencies = {int(value.strip()) for value in step[5].split(",") if value.strip()}
				self.assertTrue(dependencies.issubset(known))
				self.assertNotIn(step[0], dependencies)
			self.assertTrue(any(step[5] for step in steps), recipe_name)

	def test_litre_ingredients_do_not_enter_kg_equipment_batch_loads(self):
		for recipe_name, steps in RECIPE_STEPS.items():
			for step in steps:
				self.assertNotIn("BB-ING-SUNFLOWER-OIL", step[3], f"{recipe_name}: {step[1]}")


# endregion PRODUCTION BASELINE PROOF
