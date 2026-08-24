import frappe


PLAN_TYPES = [
	{"plan_name": "Lite", "serving_size_g": 300, "normal_price": 1699.95},
	{"plan_name": "Standard", "serving_size_g": 450, "normal_price": 2199.95},
	{"plan_name": "Full", "serving_size_g": 600, "normal_price": 2799.95, "discounted_price": 2199.95},
]

FRESH_ITEMS = {
	"BB-ING-CHICKEN-BREAST",
	"BB-ING-CRUSHED-GARLIC",
	"BB-ING-ONIONS",
	"BB-ING-POTATOES",
	"BB-ING-VALUE-BEEF-MINCE",
}


def execute():
	frappe.db.sql(
		"""
		update `tabBulkBite Supplier Offer`
		set effective_from = coalesce(effective_from, date(creation))
		where effective_from is null
		"""
	)
	"""Seed editable public-plan assumptions and the initial dry/fresh purchase routing."""
	for values in PLAN_TYPES:
		if not frappe.db.exists("BulkBite Customer Plan Type", values["plan_name"]):
			frappe.get_doc(
				{
					"doctype": "BulkBite Customer Plan Type",
					**values,
					"meals_per_day": 2,
					"days_per_week": 7,
					"cycle_weeks": 4,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	for category, supplier in (("Dry", "Makro"), ("Fresh", "Checkers")):
		if not frappe.db.exists("BulkBite Item Category", category):
			doc = frappe.get_doc({"doctype": "BulkBite Item Category", "category_name": category, "enabled": 1})
			if frappe.db.exists("BulkBite Supplier", supplier):
				doc.default_supplier = supplier
			doc.insert(ignore_permissions=True)

	items = frappe.get_all("BulkBite Item", filters={"item_type": "Ingredient"}, fields=["name", "item_code", "item_name"])
	for item in items:
		category = "Fresh" if item.item_code in FRESH_ITEMS else "Dry"
		values = {"item_category": category}
		if str(item.item_name).strip().lower() == "water":
			values["purchasable"] = 0
		frappe.db.set_value("BulkBite Item", item.name, values, update_modified=False)
