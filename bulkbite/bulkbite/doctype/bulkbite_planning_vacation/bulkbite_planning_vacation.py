import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class BulkBitePlanningVacation(Document):
	def validate(self):
		self.vacation_name = str(self.vacation_name or "").strip()
		if not self.vacation_name:
			frappe.throw(_("Enter a vacation name."))
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("Vacation start date must be on or before the end date."))
		if self.is_new() and getdate(self.from_date) < getdate(nowdate()):
			frappe.throw(_("A new vacation cannot start in the past."))
		if not self.is_new():
			original = self.get_doc_before_save()
			if original and getdate(original.from_date) < getdate(nowdate()):
				frappe.throw(_("A vacation that has started cannot be changed."))
		self._validate_no_overlap()

	def on_update(self):
		if not self.legacy_service_period:
			return
		original = self.get_doc_before_save()
		planning_changed = original and (
			original.vacation_name != self.vacation_name
			or getdate(original.from_date) != getdate(self.from_date)
			or getdate(original.to_date) != getdate(self.to_date)
		)
		if planning_changed:
			from bulkbite.production_periods import supersede_future_legacy_skip

			supersede_future_legacy_skip(self.legacy_service_period, self.name)

	def _validate_no_overlap(self):
		for vacation in frappe.get_all(
			"BulkBite Planning Vacation",
			filters={"production_plan": self.production_plan, "status": "Active"},
			fields=["name", "from_date", "to_date"],
		):
			if vacation.name == self.name:
				continue
			if getdate(vacation.from_date) <= getdate(self.to_date) and getdate(vacation.to_date) >= getdate(self.from_date):
				frappe.throw(_("These dates overlap another vacation."))
