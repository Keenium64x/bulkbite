import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from bulkbite.stock_production import apply_run_variances, get_available_stock, load_expected_usage, post_production_run, record_production_event
from bulkbite.workforce import post_production_employee_costs


# =============================================================================
# region PRODUCTION RUN LIFECYCLE
# =============================================================================


class BulkBiteProductionRun(Document):
	def validate(self):
		self._validate_submission_boundary()
		self._load_theory_when_needed()
		self._validate_actuals()
		apply_run_variances(self)

	def on_submit(self):
		frappe.db.sql("select name from `tabBulkBite Production Run` where name = %s for update", (self.name,))
		if frappe.db.get_value(self.doctype, self.name, "stock_events_posted"):
			return
		output_event = post_production_run(self)
		event = record_production_event(self, output_event.name)
		post_production_employee_costs(self)
		self.db_set(
			{"stock_events_posted": 1, "employee_costs_posted": 1, "output_stock_event": output_event.name, "truth_event": event.name},
			update_modified=False,
		)

	def on_cancel(self):
		frappe.throw(_("Posted production runs remain immutable. Create a correcting production or audit record."))

	def _load_theory_when_needed(self):
		if not self.recipe or (
			self.ingredients and not self.has_value_changed("recipe") and not self.has_value_changed("planned_output_qty")
		):
			return
		expectation = load_expected_usage(self.recipe, self.planned_output_qty, self.source_location)
		self.finished_item = expectation["finished_item"]
		self.set("ingredients", expectation["ingredients"])

	def _validate_actuals(self):
		if flt(self.planned_output_qty) <= 0:
			frappe.throw(_("Planned output must be greater than zero."))
		if flt(self.actual_output_qty) <= 0:
			frappe.throw(_("Actual output must be greater than zero before posting."))
		if not self.ingredients:
			frappe.throw(_("The selected recipe has no ingredient rows."))
		for row in self.ingredients:
			if flt(row.actual_qty) < 0:
				frappe.throw(_("Actual usage cannot be negative for {0}.").format(row.item_code))
			if row.measurement_method not in {"Used", "Remaining"}:
				frappe.throw(_("Choose used or remaining for {0}.").format(row.item_code))
			available = get_available_stock(row.item_code, row.source_location or self.source_location)
			if self._action == "submit" and flt(row.actual_qty) > available:
				frappe.throw(
					_("Usage for {0} ({1}) cannot exceed available stock ({2}).").format(
						row.item_code, flt(row.actual_qty), available
					)
				)
			if self._action == "submit" and row.measurement_method == "Remaining":
				if abs(available - flt(row.available_before_measurement)) > 0.000001:
					frappe.throw(
						_("Stock for {0} changed after the remaining quantity was saved. Save the measurement again before posting.").format(
							row.item_code
						)
					)
		self._validate_employee_assignments()

	def _validate_employee_assignments(self):
		employees = [row.employee for row in self.employees or []]
		if len(employees) != len(set(employees)):
			frappe.throw(_("Add each employee only once to a production run."))
		for row in self.employees or []:
			if row.payment_basis == "Hourly" and row.completion_status == "Completed" and flt(row.hours_worked) <= 0:
				frappe.throw(_("Enter hours worked for hourly employee {0}.").format(row.employee_name or row.employee))

	def _validate_submission_boundary(self):
		if self.stock_events_posted and self.docstatus == 0:
			frappe.throw(_("A posted production run cannot return to draft."))


# endregion PRODUCTION RUN LIFECYCLE
