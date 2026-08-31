from __future__ import annotations

import frappe


# =============================================================================
# region PRODUCTION BASELINE CONTRACT
# =============================================================================


SOURCE_NOTE = "BulkBite master workbook and reviewed supplier catalogue, August 2026."


ITEM_ALIASES = {
	"BB-ING-PARBOILED-RICE": "BB-ING-PARBOILED-LONG-GRAIN-RICE",
	"BB-ING-BASIC-PASTA": "BB-ING-DRY-PASTA",
	"BB-ING-LENTILS": "BB-ING-BROWN-LENTILS",
	"BB-ING-DRY-BEANS": "BB-ING-DRIED-SUGAR-BEANS",
	"BB-ING-POTATOES": "BB-ING-FRESH-POTATOES",
	"BB-ING-ONIONS": "BB-ING-FRESH-BROWN-ONIONS",
	"BB-ING-TOMATO-ONION-MIX": "BB-ING-CANNED-TOMATO-AND-ONION-MIX",
	"BB-ING-CHICKEN-BREAST": "BB-ING-FRESH-CHICKEN-BREAST-FILLETS",
	"BB-ING-VALUE-BEEF-MINCE": "BB-ING-FRESH-BEEF-MINCE",
	"BB-ING-CURRY-POWDER": "BB-ING-MEDIUM-CURRY-POWDER",
	"BB-ING-STOCK-CUBES": "BB-ING-BEEF-STOCK-CUBES",
	"BB-ING-SALT": "BB-ING-TABLE-SALT",
	"BB-ING-MIXED-HERBS": "BB-ING-DRIED-MIXED-HERBS",
	"BB-ING-CARROTS": "BB-ING-FRESH-CARROTS",
	"BB-ING-BLACK-PEPPER": "BB-ING-GROUND-BLACK-PEPPER",
}


def canonical_item_code(item_code):
	"""Return the live catalogue identity for one historical workbook code."""
	return ITEM_ALIASES.get(item_code, item_code)


# endregion PRODUCTION BASELINE CONTRACT


# =============================================================================
# region BASELINE SETUP DATA
# =============================================================================


CATEGORIES = (
	("Dry", "Makro", "Shelf-stable ingredients and seasonings."),
	("Vegetables", "Checkers", "Fresh produce."),
	("Protein", "Checkers", "Fresh meat and protein."),
)


LOCATIONS = (
	("Ingredients", "Ingredients", "Main ingredient store."),
	("Finished Meals", "Finished Meals", "Finished food awaiting allocation."),
	("Quarantine", "Quarantine", "Stock awaiting review."),
	("Waste", "Waste", "Measured production waste."),
)


EQUIPMENT = (
	("Rice Pot", 25, "Kg", 1, "Rice, pasta, and other boiled components."),
	("Curry Pot", 35, "Kg", 1, "Main sauce, stew, and curry vessel."),
	("Prep Station", 20, "Kg", 2, "Separate ingredient preparation surfaces."),
)


ITEM_SETTINGS = {
	"BB-ING-PARBOILED-LONG-GRAIN-RICE": ("Dry", 2.8, 0, "", "Planning assumption: 1 kg dry rice yields about 2.8 kg cooked. Buying and production usage remain raw weight."),
	"BB-ING-DRY-PASTA": ("Dry", 2.25, 0, "", "Planning assumption: 1 kg dry pasta yields about 2.25 kg cooked. Buying and production usage remain raw weight."),
	"BB-ING-BROWN-LENTILS": ("Dry", 2.5, 0, "", "Planning assumption: 1 kg dry lentils yields about 2.5 kg cooked. Buying and production usage remain raw weight."),
	"BB-ING-DRIED-SUGAR-BEANS": ("Dry", 2.4, 0, "", "Planning assumption: 1 kg dry beans yields about 2.4 kg cooked. Buying and production usage remain raw weight."),
	"BB-ING-FRESH-POTATOES": ("Vegetables", 1, 175, "medium potatoes", "Count is an estimate only. Weigh the raw potatoes before preparation."),
	"BB-ING-FRESH-BROWN-ONIONS": ("Vegetables", 1, 150, "medium onions", "Count is an estimate only. Weigh the raw onions before preparation."),
	"BB-ING-FRESH-CARROTS": ("Vegetables", 1, 100, "medium carrots", "Count is an estimate only. Weigh the raw carrots before preparation."),
	"BB-ING-FRESH-CHICKEN-BREAST-FILLETS": ("Protein", 1, 0, "", "Weigh raw chicken and keep it separate from ready-to-eat food and cleaned equipment."),
	"BB-ING-FRESH-BEEF-MINCE": ("Protein", 1, 0, "", "Weigh raw mince before cooking."),
	"BB-ING-CANNED-TOMATO-AND-ONION-MIX": ("Dry", 1, 0, "", "Use the saved drained or full-can basis consistently when recording actual use."),
	"BB-ING-TOMATO-PUREE": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-SUNFLOWER-OIL": ("Dry", 1, 0, "", "Use the saved raw volume."),
	"BB-ING-CRUSHED-GARLIC": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-MEDIUM-CURRY-POWDER": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-BEEF-STOCK-CUBES": ("Dry", 1, 0, "", "Use the saved raw weight rather than counting cubes, because pack formats may differ."),
	"BB-ING-TABLE-SALT": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-DRIED-MIXED-HERBS": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-CHILLI-POWDER": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-PAPRIKA": ("Dry", 1, 0, "", "Use the saved raw weight."),
	"BB-ING-GROUND-BLACK-PEPPER": ("Dry", 1, 0, "", "Use the saved raw weight."),
}


FINISHED_ITEMS = (
	("BB-MEAL-CHICKEN-POTATO-CURRY-RICE", "Chicken & Potato Curry + Rice"),
	("BB-MEAL-BEEF-BOLOGNESE-PASTA", "Beef Bolognese Pasta"),
	("BB-MEAL-SMOKY-BEEF-CHILLI-RICE", "Smoky Beef Chilli + Rice"),
	("BB-MEAL-CHICKEN-TOMATO-STEW-RICE", "Chicken Tomato Stew + Rice"),
)


# endregion BASELINE SETUP DATA


# =============================================================================
# region RECIPE THEORY AND METHOD DATA
# =============================================================================


RECIPE_INGREDIENTS = {
	"Chicken & Potato Curry + Rice": (
		("BB-ING-PARBOILED-RICE", 15), ("BB-ING-CHICKEN-BREAST", 18), ("BB-ING-POTATOES", 21),
		("BB-ING-ONIONS", 6), ("BB-ING-TOMATO-ONION-MIX", 6.15), ("BB-ING-TOMATO-PUREE", 1),
		("BB-ING-SUNFLOWER-OIL", 1.5), ("BB-ING-CRUSHED-GARLIC", 0.5), ("BB-ING-CURRY-POWDER", 0.6),
		("BB-ING-STOCK-CUBES", 0.15), ("BB-ING-SALT", 0.07), ("BB-ING-BLACK-PEPPER", 0.08), ("BB-ING-WATER", 7),
	),
	"Beef Bolognese Pasta": (
		("BB-ING-BASIC-PASTA", 22), ("BB-ING-VALUE-BEEF-MINCE", 14), ("BB-ING-LENTILS", 5),
		("BB-ING-ONIONS", 5), ("BB-ING-CARROTS", 5), ("BB-ING-TOMATO-ONION-MIX", 10.25),
		("BB-ING-TOMATO-PUREE", 2), ("BB-ING-SUNFLOWER-OIL", 1.2), ("BB-ING-CRUSHED-GARLIC", 0.5),
		("BB-ING-MIXED-HERBS", 0.12), ("BB-ING-STOCK-CUBES", 0.15), ("BB-ING-SALT", 0.07),
		("BB-ING-BLACK-PEPPER", 0.08), ("BB-ING-WATER", 8),
	),
	"Smoky Beef Chilli + Rice": (
		("BB-ING-PARBOILED-RICE", 15), ("BB-ING-VALUE-BEEF-MINCE", 14), ("BB-ING-DRY-BEANS", 8),
		("BB-ING-ONIONS", 5), ("BB-ING-TOMATO-ONION-MIX", 10.25), ("BB-ING-TOMATO-PUREE", 2),
		("BB-ING-SUNFLOWER-OIL", 1.2), ("BB-ING-CRUSHED-GARLIC", 0.5), ("BB-ING-CHILLI-POWDER", 0.25),
		("BB-ING-PAPRIKA", 0.3), ("BB-ING-STOCK-CUBES", 0.15), ("BB-ING-SALT", 0.07),
		("BB-ING-BLACK-PEPPER", 0.08), ("BB-ING-WATER", 8),
	),
	"Chicken Tomato Stew + Rice": (
		("BB-ING-PARBOILED-RICE", 15), ("BB-ING-CHICKEN-BREAST", 18), ("BB-ING-POTATOES", 15),
		("BB-ING-CARROTS", 8), ("BB-ING-ONIONS", 6), ("BB-ING-TOMATO-ONION-MIX", 8.2),
		("BB-ING-TOMATO-PUREE", 1.5), ("BB-ING-SUNFLOWER-OIL", 1.5), ("BB-ING-CRUSHED-GARLIC", 0.5),
		("BB-ING-PAPRIKA", 0.3), ("BB-ING-STOCK-CUBES", 0.15), ("BB-ING-SALT", 0.07),
		("BB-ING-BLACK-PEPPER", 0.08), ("BB-ING-WATER", 7),
	),
}


RECIPE_FINISHED_ITEMS = dict((name, code) for code, name in FINISHED_ITEMS)


RECIPE_STEPS = {
	"Chicken & Potato Curry + Rice": (
		(1, "Start rice", "Rinse the rice until the runoff is mostly clear. Measure the recipe water, bring the pot to a controlled boil, add the rice, reduce to a steady simmer, cover, and cook until tender. Rest covered before fluffing.", "BB-ING-PARBOILED-RICE, BB-ING-WATER", "Rice Pot", "", 1, 10, 0.18, 1, "Rice cook", "Rice is tender, separate, and free of standing water."),
		(2, "Prepare vegetables", "Wash the potatoes, remove damaged areas, and cut them into even pieces. Peel and dice the onions. Measure the garlic and keep each prepared ingredient separate.", "BB-ING-POTATOES, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC", "Prep Station", "", 1, 15, 0.28, 1, "Preparation", "Pieces are even enough to cook consistently."),
		(3, "Prepare chicken safely", "Trim and cut the chicken into even pieces using the raw-protein area and tools. Clean and sanitise the surface and tools before they are reused.", "BB-ING-CHICKEN-BREAST", "Prep Station", "", 1, 12, 0.25, 1, "Protein preparation", "Raw chicken has not contacted ready-to-eat food or clean equipment."),
		(4, "Build curry base", "Heat the oil, soften the onions without scorching, stir in the garlic and curry powder, then add tomato puree and tomato-and-onion mix. Cook until the base is evenly combined and aromatic.", "BB-ING-SUNFLOWER-OIL, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-CURRY-POWDER, BB-ING-TOMATO-PUREE, BB-ING-TOMATO-ONION-MIX", "Curry Pot", "2", 0, 12, 0.14, 1, "Curry cook", "The spice base is evenly mixed and has not caught on the bottom."),
		(5, "Cook chicken and potatoes", "Add the prepared chicken and cook it through the curry base. Add potatoes, crumbled stock, salt, pepper, and the remaining recipe water. Bring to a controlled boil, reduce to a simmer, and stir from the bottom until the chicken is fully cooked and the potatoes are tender.", "BB-ING-CHICKEN-BREAST, BB-ING-POTATOES, BB-ING-STOCK-CUBES, BB-ING-SALT, BB-ING-BLACK-PEPPER, BB-ING-WATER", "Curry Pot", "3, 4", 0, 25, 0.35, 1, "Curry cook", "Chicken is fully cooked according to the kitchen's verified food-safety procedure and potatoes are tender."),
		(6, "Finish, weigh, and portion", "Taste against the approved recipe, correct only with the weighed recipe seasonings, confirm the finished weight, and portion the curry and rice into clean containers.", "BB-ING-PARBOILED-RICE", "Prep Station", "1, 5", 1, 12, 0.16, 2, "Portioning", "Finished weight, container count, and any variance are recorded."),
	),
	"Beef Bolognese Pasta": (
		(1, "Rinse and start lentils", "Rinse the lentils under cold water until the runoff is mostly clear. Add them to the pot with their measured share of recipe water, bring to a controlled boil, then reduce to a simmer until nearly tender.", "BB-ING-LENTILS, BB-ING-WATER", "Curry Pot", "", 1, 10, 0.22, 1, "Sauce cook", "Lentils are clean and nearly tender without scorching."),
		(2, "Prepare vegetables", "Peel and dice the onions. Wash, trim, and grate or finely dice the carrots. Measure the garlic and keep the prepared vegetables ready for the sauce.", "BB-ING-ONIONS, BB-ING-CARROTS, BB-ING-CRUSHED-GARLIC", "Prep Station", "", 1, 14, 0.25, 1, "Preparation", "Vegetables are evenly prepared and clean."),
		(3, "Brown the mince", "Heat part of the oil, add the mince in workable batches, break up clumps, and cook until no raw mince remains. Drain only excess liquid that is not part of the recorded recipe method.", "BB-ING-VALUE-BEEF-MINCE, BB-ING-SUNFLOWER-OIL", "Curry Pot", "1", 0, 18, 0.25, 1, "Sauce cook", "Mince is evenly broken up and no raw meat remains."),
		(4, "Build bolognese sauce", "Add onions, carrots, and garlic to the mince. Cook until softened, then add tomato-and-onion mix, puree, herbs, crumbled stock, salt, pepper, the lentils, and the remaining recipe water. Simmer and stir from the bottom until the sauce is cohesive.", "BB-ING-ONIONS, BB-ING-CARROTS, BB-ING-CRUSHED-GARLIC, BB-ING-TOMATO-ONION-MIX, BB-ING-TOMATO-PUREE, BB-ING-MIXED-HERBS, BB-ING-STOCK-CUBES, BB-ING-SALT, BB-ING-BLACK-PEPPER, BB-ING-LENTILS, BB-ING-WATER", "Curry Pot", "2, 3", 0, 25, 0.32, 1, "Sauce cook", "Lentils are tender, the sauce coats the spoon, and the bottom has not scorched."),
		(5, "Cook pasta", "Bring the measured cooking water to a strong boil. Add pasta in equipment-sized batches, stir to prevent sticking, cook until just tender, then drain thoroughly.", "BB-ING-BASIC-PASTA, BB-ING-WATER", "Rice Pot", "", 1, 12, 0.18, 1, "Pasta cook", "Pasta is tender but still holds its shape and is fully drained."),
		(6, "Combine, weigh, and portion", "Combine the cooked pasta and sauce evenly, or portion them according to the approved service method. Confirm the finished weight and portion into clean containers.", "BB-ING-BASIC-PASTA", "Prep Station", "4, 5", 1, 12, 0.16, 2, "Portioning", "Finished weight, container count, and any variance are recorded."),
	),
	"Smoky Beef Chilli + Rice": (
		(1, "Soak and start beans", "Sort and rinse the beans, removing damaged beans or debris. Soak them if the production timing allows, drain, add fresh measured recipe water, bring to a controlled boil, and simmer until nearly tender.", "BB-ING-DRY-BEANS, BB-ING-WATER", "Curry Pot", "", 1, 15, 0.35, 1, "Chilli cook", "Beans are clean and nearly tender before they enter the chilli."),
		(2, "Start rice", "Rinse the rice until the runoff is mostly clear. Measure its recipe water, bring to a controlled boil, add the rice, reduce to a steady simmer, cover, cook until tender, then rest covered.", "BB-ING-PARBOILED-RICE, BB-ING-WATER", "Rice Pot", "", 1, 10, 0.18, 1, "Rice cook", "Rice is tender and free of standing water."),
		(3, "Prepare aromatics", "Peel and dice the onions. Measure the garlic, chilli powder, paprika, salt, pepper, and stock separately so the spice level remains controlled.", "BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-CHILLI-POWDER, BB-ING-PAPRIKA, BB-ING-SALT, BB-ING-BLACK-PEPPER, BB-ING-STOCK-CUBES", "Prep Station", "", 1, 12, 0.18, 1, "Preparation", "All seasonings are weighed and clearly separated."),
		(4, "Brown mince and build base", "Heat the oil, brown the mince in workable batches, break up clumps, then add onions and garlic. Stir in chilli powder and paprika without scorching them, followed by tomato puree and tomato-and-onion mix.", "BB-ING-VALUE-BEEF-MINCE, BB-ING-SUNFLOWER-OIL, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-CHILLI-POWDER, BB-ING-PAPRIKA, BB-ING-TOMATO-PUREE, BB-ING-TOMATO-ONION-MIX", "Curry Pot", "3", 0, 20, 0.26, 1, "Chilli cook", "No raw mince remains and the spice base has not scorched."),
		(5, "Finish chilli", "Add the cooked beans, crumbled stock, salt, pepper, and remaining recipe water to the mince base. Simmer and stir from the bottom until the beans are tender and the chilli has an even consistency.", "BB-ING-DRY-BEANS, BB-ING-STOCK-CUBES, BB-ING-SALT, BB-ING-BLACK-PEPPER, BB-ING-WATER", "Curry Pot", "1, 4", 0, 25, 0.3, 1, "Chilli cook", "Beans are tender and the seasoning is evenly distributed."),
		(6, "Weigh and portion", "Confirm the finished weights, record any variance, and portion the chilli and rice into clean containers.", "BB-ING-PARBOILED-RICE", "Prep Station", "2, 5", 1, 12, 0.16, 2, "Portioning", "Finished weight and container count match the production record."),
	),
	"Chicken Tomato Stew + Rice": (
		(1, "Start rice", "Rinse the rice until the runoff is mostly clear. Measure its recipe water, bring to a controlled boil, add the rice, reduce to a steady simmer, cover, cook until tender, then rest covered.", "BB-ING-PARBOILED-RICE, BB-ING-WATER", "Rice Pot", "", 1, 10, 0.18, 1, "Rice cook", "Rice is tender and free of standing water."),
		(2, "Prepare vegetables", "Wash the potatoes and carrots, remove damaged areas, and cut them into even pieces. Peel and dice the onions. Measure the garlic separately.", "BB-ING-POTATOES, BB-ING-CARROTS, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC", "Prep Station", "", 1, 16, 0.3, 1, "Preparation", "Vegetables are clean and even enough to cook consistently."),
		(3, "Prepare chicken safely", "Trim and cut the chicken into even pieces using the raw-protein area and tools. Clean and sanitise the surface and tools before they are reused.", "BB-ING-CHICKEN-BREAST", "Prep Station", "", 1, 12, 0.25, 1, "Protein preparation", "Raw chicken has not contacted ready-to-eat food or clean equipment."),
		(4, "Build tomato base", "Heat the oil, soften the onions, add the garlic and paprika, then stir in the tomato puree and tomato-and-onion mix until evenly combined.", "BB-ING-SUNFLOWER-OIL, BB-ING-ONIONS, BB-ING-CRUSHED-GARLIC, BB-ING-PAPRIKA, BB-ING-TOMATO-PUREE, BB-ING-TOMATO-ONION-MIX", "Curry Pot", "2", 0, 12, 0.14, 1, "Stew cook", "The tomato base is evenly mixed and has not scorched."),
		(5, "Cook chicken and vegetables", "Add the prepared chicken and cook it through the tomato base. Add potatoes, carrots, crumbled stock, salt, pepper, and remaining recipe water. Bring to a controlled boil, reduce to a simmer, and stir from the bottom until the chicken is fully cooked and the vegetables are tender.", "BB-ING-CHICKEN-BREAST, BB-ING-POTATOES, BB-ING-CARROTS, BB-ING-STOCK-CUBES, BB-ING-SALT, BB-ING-BLACK-PEPPER, BB-ING-WATER", "Curry Pot", "3, 4", 0, 25, 0.34, 1, "Stew cook", "Chicken is fully cooked according to the kitchen's verified procedure and vegetables are tender."),
		(6, "Finish, weigh, and portion", "Taste against the approved recipe, confirm the finished weights, record any variance, and portion the stew and rice into clean containers.", "BB-ING-PARBOILED-RICE", "Prep Station", "1, 5", 1, 12, 0.16, 2, "Portioning", "Finished weight and container count match the production record."),
	),
}


# endregion RECIPE THEORY AND METHOD DATA


# =============================================================================
# region IDEMPOTENT BOOTSTRAP ORCHESTRATION
# =============================================================================


@frappe.whitelist()
def load_production_baseline():
	"""Load reviewed setup and recipe theory without creating operational evidence."""
	frappe.only_for("System Manager")
	try:
		_setup_suppliers()
		_setup_categories_locations_and_equipment()
		_setup_catalogue_items()
		recipes = _setup_recipes()
		frappe.db.commit()
		return {
			"loaded": True,
			"items": frappe.db.count("BulkBite Item", {"enabled": 1}),
			"supplier_offers": frappe.db.count("BulkBite Supplier Offer", {"enabled": 1}),
			"recipes": recipes,
			"receipts_created": 0,
			"production_runs_created": 0,
		}
	except Exception:
		frappe.db.rollback()
		raise


def _setup_suppliers():
	for name, lead_days in (("Makro", 4), ("Checkers", 1)):
		doc = _named_doc("BulkBite Supplier", name)
		doc.update({
			"supplier_name": name,
			"enabled": 1,
			"delivery_lead_time_days": lead_days,
			"order_safety_days": 1,
			"notes": "Reviewed supplier catalogue route. Existing contact and tax fields are preserved.",
		})
		doc.save(ignore_permissions=True)


def _setup_categories_locations_and_equipment():
	for name, supplier, notes in CATEGORIES:
		doc = _named_doc("BulkBite Item Category", name)
		doc.update({"category_name": name, "default_supplier": supplier, "enabled": 1, "notes": notes})
		doc.save(ignore_permissions=True)
	for name, location_type, notes in LOCATIONS:
		doc = _named_doc("BulkBite Location", name)
		doc.update({"location_name": name, "location_type": location_type, "enabled": 1, "notes": notes})
		doc.save(ignore_permissions=True)
	for name, capacity, uom, quantity, notes in EQUIPMENT:
		doc = _named_doc("BulkBite Equipment Type", name)
		doc.update({
			"equipment_type_name": name, "capacity_qty": capacity, "capacity_uom": uom,
			"quantity_available": quantity, "concurrent_batch_limit": 1, "enabled": 1, "notes": notes,
		})
		doc.save(ignore_permissions=True)


def _setup_catalogue_items():
	for item_code, values in ITEM_SETTINGS.items():
		if not frappe.db.exists("BulkBite Item", item_code):
			raise frappe.ValidationError(f"Reviewed catalogue item {item_code} is missing.")
		category, yield_factor, piece_weight, piece_label, yield_note = values
		doc = frappe.get_doc("BulkBite Item", item_code)
		doc.update({
			"item_category": category,
			"prepared_yield_factor": yield_factor,
			"average_piece_weight_g": piece_weight,
			"piece_count_label": piece_label,
			"preparation_yield_note": yield_note,
		})
		doc.save(ignore_permissions=True)
	for offer in frappe.get_all("BulkBite Supplier Offer", filters={"enabled": 1}, fields=["item_code", "supplier_item_code"]):
		if offer.supplier_item_code and frappe.db.exists("BulkBite Item", offer.item_code):
			doc = frappe.get_doc("BulkBite Item", offer.item_code)
			codes = {line.strip() for line in str(doc.scan_codes or "").splitlines() if line.strip()}
			codes.add(offer.supplier_item_code)
			doc.scan_codes = "\n".join(sorted(codes))
			doc.save(ignore_permissions=True)
	if not frappe.db.exists("BulkBite Item", "BB-ING-WATER"):
		frappe.get_doc({
			"doctype": "BulkBite Item", "item_code": "BB-ING-WATER", "item_name": "Water",
			"item_type": "Ingredient", "stock_uom": "Kg", "track_stock": 0, "purchasable": 0,
			"enabled": 1, "prepared_yield_factor": 1, "description": "Internal recipe input. It is not purchased or stock-counted.",
		}).insert(ignore_permissions=True)
	for item_code, item_name in FINISHED_ITEMS:
		if not frappe.db.exists("BulkBite Item", item_code):
			frappe.get_doc({
				"doctype": "BulkBite Item", "item_code": item_code, "item_name": item_name,
				"item_type": "Finished Meal", "stock_uom": "Kg", "track_stock": 1,
				"purchasable": 0, "enabled": 1, "description": SOURCE_NOTE,
			}).insert(ignore_permissions=True)


def _setup_recipes():
	names = []
	for recipe_name, raw_ingredients in RECIPE_INGREDIENTS.items():
		record_name = frappe.db.get_value("BulkBite Recipe", {"recipe_name": recipe_name, "version": 1}, "name")
		doc = frappe.get_doc("BulkBite Recipe", record_name) if record_name else frappe.new_doc("BulkBite Recipe")
		doc.update({
			"recipe_name": recipe_name,
			"version": 1,
			"status": "Approved",
			"finished_item": RECIPE_FINISHED_ITEMS[recipe_name],
			"nominal_output_qty": 100,
			"output_uom": "Kg",
			"source_workbook": "BulkBite.xlsx",
			"source_sheet": "Recipe_Costing",
			"instruction_guidance": "Run independent preparation and cooking steps concurrently when clean equipment and workers are available. Weigh every ingredient before cooking, keep raw protein separate, and record finished weight before portioning.",
			"notes": SOURCE_NOTE,
		})
		doc.set("ingredients", [])
		for old_code, quantity in raw_ingredients:
			doc.append("ingredients", {"item_code": canonical_item_code(old_code), "qty": quantity})
		doc.set("instruction_steps", [])
		for step in RECIPE_STEPS[recipe_name]:
			step_number, step_name, instruction, items, equipment, dependencies, concurrent, base_minutes, per_kg, workers, role, check = step
			doc.append("instruction_steps", {
				"step_number": step_number,
				"step_name": step_name,
				"instruction": instruction,
				"ingredient_items": ", ".join(canonical_item_code(code.strip()) for code in items.split(",")),
				"equipment_type": equipment,
				"depends_on_steps": dependencies,
				"can_run_concurrently": concurrent,
				"requires_active_worker": 1,
				"duration_minutes": base_minutes,
				"duration_per_kg_minutes": per_kg,
				"minimum_workers": workers,
				"worker_role": role,
				"quality_checkpoint": check,
			})
		doc.save(ignore_permissions=True)
		names.append(doc.name)
	return names


def _named_doc(doctype, name):
	return frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else frappe.new_doc(doctype)


# endregion IDEMPOTENT BOOTSTRAP ORCHESTRATION
