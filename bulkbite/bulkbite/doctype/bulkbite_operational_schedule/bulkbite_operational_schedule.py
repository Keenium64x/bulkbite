import frappe
from frappe import _
from frappe.model.document import Document


class BulkBiteOperationalSchedule(Document):
	def validate(self):
		if self.recurrence == "Weekly" and not self.day_of_week:
			frappe.throw(_("Choose the weekday for a weekly schedule."))
		if self.recurrence in {"Monthly", "Quarterly", "Annual"} and not self.day_of_month:
			frappe.throw(_("Choose the day of month for this schedule."))
		if self.recurrence == "Annual" and not self.month_of_year:
			frappe.throw(_("Choose the month for an annual schedule."))

	def on_update(self):
		from bulkbite.operational_actions import materialize_operational_actions

		if self.enabled:
			materialize_operational_actions(schedule_name=self.name)
