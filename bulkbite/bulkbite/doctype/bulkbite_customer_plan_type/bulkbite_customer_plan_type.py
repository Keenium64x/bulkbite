import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BulkBiteCustomerPlanType(Document):
	def validate(self):
		if flt(self.serving_size_g) <= 0:
			frappe.throw(_("Serving size must be greater than zero."))
		if self.meals_per_day <= 0 or self.days_per_week <= 0 or self.cycle_weeks <= 0:
			frappe.throw(_("Meals per day, days per week, and cycle weeks must be greater than zero."))

