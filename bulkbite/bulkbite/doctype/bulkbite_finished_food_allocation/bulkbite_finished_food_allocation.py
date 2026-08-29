import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from bulkbite.stock_ledger import append_stock_event, get_stock_balance, get_valuation_rate
from bulkbite.truth_ledger import append_truth_event


# =============================================================================
# region FINISHED FOOD ALLOCATION LIFECYCLE
# =============================================================================


class BulkBiteFinishedFoodAllocation(Document):
	def validate(self):
		if flt(self.quantity) <= 0:
			frappe.throw(_("Allocation quantity must be greater than zero."))
		item_type = frappe.get_cached_value("BulkBite Item", self.finished_item, "item_type")
		if item_type != "Finished Meal":
			frappe.throw(_("Choose a finished meal item."))
		if self.source_production_run:
			run_item = frappe.get_cached_value("BulkBite Production Run", self.source_production_run, "finished_item")
			if run_item != self.finished_item:
				frappe.throw(_("The source production run made a different finished meal."))
		if self.allocation_type == "Future Customers" and not self.demand_period:
			frappe.throw(_("Enter the future customer period or reference."))
		if self.allocation_type == "Future Customer Fulfilment":
			self._validate_reservation_fulfilment()
		elif self.source_reservation:
			frappe.throw(_("A future reservation can only be linked to a future customer fulfilment."))

	def on_submit(self):
		_lock_finished_food_position(self.finished_item, self.source_location)
		if self.allocation_type == "Future Customer Fulfilment":
			frappe.db.sql("select name from `tabBulkBite Finished Food Allocation` where name = %s for update", (self.source_reservation,))
			available = get_reservation_remaining(self.source_reservation, exclude_name=self.name)
			if flt(self.quantity) > available:
				frappe.throw(_("Only {0} {1} remains on reservation {2}.").format(available, self.uom, self.source_reservation))
		else:
			available = get_unallocated_finished_food(self.finished_item, self.source_location, exclude_name=self.name)
			if flt(self.quantity) > available:
				frappe.throw(_("Only {0} {1} is unallocated at {2}.").format(available, self.uom, self.source_location))
		stock_event = None
		if self.allocation_type != "Future Customers":
			stock_event = append_stock_event(
				"Consumption", self.finished_item, self.source_location, -flt(self.quantity),
				get_valuation_rate(self.finished_item, self.source_location), self.doctype, self.name,
			)
		status = "Reserved" if self.allocation_type == "Future Customers" else "Issued"
		truth = append_truth_event(
			"FINISHED_FOOD_ALLOCATED", self.doctype, self.name,
			{
				"allocation_type": self.allocation_type,
				"demand_period": self.demand_period,
				"finished_item": self.finished_item,
				"quantity": flt(self.quantity),
				"source_location": self.source_location,
				"source_production_run": self.source_production_run,
				"stock_event": stock_event.name if stock_event else None,
			},
		)
		self.db_set({"status": status, "stock_event": stock_event.name if stock_event else None, "truth_event": truth.name}, update_modified=False)

	def on_cancel(self):
		frappe.throw(_("Submitted finished-food allocations remain immutable. Add a correcting allocation or stock audit."))

	def _validate_reservation_fulfilment(self):
		if not self.source_reservation:
			frappe.throw(_("Choose the future reservation being fulfilled."))
		reservation = frappe.get_doc("BulkBite Finished Food Allocation", self.source_reservation)
		if reservation.docstatus != 1 or reservation.allocation_type != "Future Customers":
			frappe.throw(_("Choose a submitted future customer reservation."))
		if reservation.finished_item != self.finished_item or reservation.source_location != self.source_location:
			frappe.throw(_("The reservation is for a different finished meal or stock location."))
		self.demand_period = self.demand_period or reservation.demand_period


def _lock_finished_food_position(item_code, location):
	"""Serialize physical issues and reservations against one item-location balance."""
	frappe.db.sql("select name from `tabDocType` where name = %s for update", ("BulkBite Stock Balance",))
	frappe.db.sql(
		"select name from `tabBulkBite Stock Balance` where item_code = %s and location = %s for update",
		(item_code, location),
	)


def get_unallocated_finished_food(item_code, location, exclude_name=None):
	"""Return physical finished stock after outstanding future-customer reservations."""
	filters = {"finished_item": item_code, "source_location": location, "allocation_type": "Future Customers", "docstatus": 1}
	if exclude_name:
		filters["name"] = ("!=", exclude_name)
	reserved = sum(get_reservation_remaining(name) for name in frappe.get_all("BulkBite Finished Food Allocation", filters=filters, pluck="name"))
	return max(round(flt(get_stock_balance(item_code, location)) - reserved, 3), 0)


def get_reservation_remaining(reservation_name, exclude_name=None):
	"""Return the unissued quantity on one immutable future reservation."""
	reserved = flt(frappe.db.get_value("BulkBite Finished Food Allocation", reservation_name, "quantity"))
	filters = {"source_reservation": reservation_name, "allocation_type": "Future Customer Fulfilment", "docstatus": 1}
	if exclude_name:
		filters["name"] = ("!=", exclude_name)
	fulfilled = sum(flt(value) for value in frappe.get_all("BulkBite Finished Food Allocation", filters=filters, pluck="quantity"))
	return max(round(reserved - fulfilled, 3), 0)


# endregion FINISHED FOOD ALLOCATION LIFECYCLE
