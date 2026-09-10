import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate

from bulkbite.planning import calculate_customer_demand


class BulkBiteProductionPlan(Document):
	def validate(self):
		self._validate_period()
		self._derive_customer_demand()

	def _validate_period(self):
		if self.period_start and self.period_end and getdate(self.period_end) < getdate(self.period_start):
			frappe.throw(_("Period end cannot be before period start."))

	def _derive_customer_demand(self):
		demand = calculate_customer_demand(self.customer_mix)
		for row, calculated in zip(self.customer_mix, demand["mix"], strict=False):
			row.serving_size_g = calculated["serving_size_g"]
			row.meals_per_day = calculated["meals_per_day"]
			row.days_per_week = calculated["days_per_week"]
			row.cycle_weeks = calculated["cycle_weeks"]
			row.customer_price = calculated["customer_price"]
			row.price_basis = calculated["price_basis"]
			row.weekly_servings = calculated["weekly_servings"]
			row.weekly_output_qty = calculated["weekly_output_qty"]
		for row in self.plan_rows:
			row.weekly_servings = demand["weekly_servings"]
			customer_output = flt(row.customer_required_output_qty) or flt(demand["weekly_output_qty"])
			extra_output = max(flt(row.extra_output_qty), 0)
			row.customer_required_output_qty = customer_output
			row.extra_output_qty = extra_output
			row.planned_output_qty = customer_output + extra_output
			row.uom = "Kg"
			if self.period_start and row.week_number:
				row.planned_date = add_days(getdate(self.period_start), (int(row.week_number) - 1) * 7)
			if row.recipe:
				row.finished_item = frappe.get_cached_value("BulkBite Recipe", row.recipe, "finished_item")
