import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt

from bulkbite.truth_ledger import append_truth_event


MOVEMENT_STATES = {
	"Opening": (None, "Clean"),
	"Filled for Production": ("Clean", "Filled"),
	"Issued to Customer": ("Filled", "With Customer"),
	"Returned by Customer": ("With Customer", "Clean"),
	"Sent to Maintenance": ("Clean", "Maintenance"),
	"Returned from Maintenance": ("Maintenance", "Clean"),
	"Marked Lost": ("With Customer", "Lost"),
	"Retired": (None, "Retired"),
	"Reconciliation Adjustment": (None, None),
}


class BulkBiteContainerMovement(Document):
	def validate(self):
		if self.movement_type not in MOVEMENT_STATES:
			frappe.throw(_("Choose a valid container movement."))
		asset = frappe.get_doc("BulkBite Container Asset", self.container_asset)
		expected_source, default_target = MOVEMENT_STATES[self.movement_type]
		self.container_type = asset.container_type
		self.source_state = asset.lifecycle_state
		if self.movement_type != "Reconciliation Adjustment":
			self.target_state = default_target
		if expected_source and asset.lifecycle_state != expected_source:
			frappe.throw(_("{0} is currently {1}, so it cannot be moved using {2}.").format(asset.name, asset.lifecycle_state, self.movement_type))
		if self.movement_type == "Issued to Customer":
			if not self.customer_reference:
				frappe.throw(_("Enter the customer reference receiving the container."))
			return_days = frappe.get_cached_value("BulkBite Container Type", self.container_type, "expected_return_days") or 0
			self.expected_return_date = self.expected_return_date or add_days(self.posting_date, return_days)
		if self.movement_type == "Marked Lost":
			price, multiplier = frappe.db.get_value("BulkBite Container Type", self.container_type, ["replacement_price", "non_return_charge_multiplier"])
			self.replacement_charge = flt(price) * flt(multiplier or 2)

	def on_submit(self):
		asset = frappe.get_doc("BulkBite Container Asset", self.container_asset)
		updates = {"last_movement": self.name}
		if self.target_state:
			updates["lifecycle_state"] = self.target_state
		updates["current_customer_reference"] = self.customer_reference if self.target_state == "With Customer" else None
		updates["expected_return_date"] = self.expected_return_date if self.target_state == "With Customer" else None
		asset.db_set(updates, update_modified=False)
		truth = append_truth_event("CONTAINER_MOVED", self.doctype, self.name, {
			"asset": self.container_asset,
			"movement_type": self.movement_type,
			"source_state": self.source_state,
			"target_state": self.target_state,
			"customer_reference": self.customer_reference,
			"replacement_charge": flt(self.replacement_charge),
		})
		self.db_set("truth_event", truth.name, update_modified=False)

	def on_cancel(self):
		frappe.throw(_("Submitted container movements remain immutable. Add a correcting reconciliation movement."))
