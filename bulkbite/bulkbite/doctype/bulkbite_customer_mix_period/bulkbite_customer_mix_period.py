import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class BulkBiteCustomerMixPeriod(Document):
	def validate(self):
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To cannot be before Effective From."))
		self.customer_count = max(int(self.customer_count or 0), 0)
		self._freeze_customer_terms()
		self._validate_no_overlap()

	def _freeze_customer_terms(self):
		plan = frappe.get_cached_doc("BulkBite Customer Plan Type", self.plan_type)
		self.serving_size_g = flt(self.serving_size_g) or flt(plan.serving_size_g)
		self.meals_per_day = int(self.meals_per_day or plan.meals_per_day or 0)
		self.days_per_week = int(self.days_per_week or plan.days_per_week or 0)
		self.cycle_weeks = int(self.cycle_weeks or plan.cycle_weeks or 4)
		self.price_basis = self.price_basis if self.price_basis in {"Normal", "Discounted"} else "Normal"
		if not flt(self.cycle_price):
			self.cycle_price = (
				flt(plan.discounted_price)
				if self.price_basis == "Discounted" and flt(plan.discounted_price) > 0
				else flt(plan.normal_price)
			)

	def _validate_no_overlap(self):
		for period in frappe.get_all(
			self.doctype,
			filters={"plan_type": self.plan_type},
			fields=["name", "effective_from", "effective_to"],
		):
			if period.name == self.name:
				continue
			period_end = getdate(period.effective_to) if period.effective_to else getdate("9999-12-31")
			self_end = getdate(self.effective_to) if self.effective_to else getdate("9999-12-31")
			if getdate(period.effective_from) <= self_end and period_end >= getdate(self.effective_from):
				frappe.throw(_("These dates overlap another {0} customer period.").format(self.plan_type))
