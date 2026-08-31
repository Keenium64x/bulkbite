from __future__ import annotations

import hashlib
import hmac
import secrets
import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from bulkbite.production_instructions import build_run_instruction_plan


# =============================================================================
# region ASSIGNMENT LINK SECURITY
# =============================================================================

ASSIGNMENT_LINK_LIFETIME_DAYS = 7
ASSIGNMENT_LINK_DOCTYPE = "BulkBite Kitchen Assignment Link"
MANAGER_ROLES = {"System Manager", "BulkBite Manager"}
APP_ROLES = {"System Manager", "BulkBite Manager", "BulkBite Worker"}


def _token_hash(token):
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _require_app_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to manage kitchen links."), frappe.PermissionError)
	if frappe.session.user != "Administrator" and not APP_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Your account does not have access to kitchen links."), frappe.PermissionError)


def _require_manager():
	_require_app_user()
	if frappe.session.user != "Administrator" and not MANAGER_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Only a BulkBite manager can generate or revoke employee links."), frappe.PermissionError)


def _can_manage_links():
	return frappe.session.user == "Administrator" or bool(MANAGER_ROLES.intersection(frappe.get_roles()))


def _active_assignments(run):
	return [
		row
		for row in run.employees or []
		if row.employee and row.completion_status not in {"Absent", "Cancelled"}
	]


def _assigned_employee(run_name, employee):
	run = frappe.get_doc("BulkBite Production Run", run_name)
	assignment = next((row for row in _active_assignments(run) if row.employee == employee), None)
	if not assignment:
		frappe.throw(_("Save this employee on the cooking plan before generating a link."), frappe.ValidationError)
	return run, assignment


def _revoke_active_links(run_name, employee, revoked_at=None):
	revoked_at = revoked_at or now_datetime()
	for row in frappe.get_all(
		ASSIGNMENT_LINK_DOCTYPE,
		filters={"production_run": run_name, "employee": employee, "revoked_at": ("is", "not set")},
		fields=["name"],
	):
		frappe.db.set_value(
			ASSIGNMENT_LINK_DOCTYPE,
			row.name,
			"revoked_at",
			revoked_at,
			update_modified=False,
		)


def _link_status(link, now=None):
	now = get_datetime(now or now_datetime())
	if link.revoked_at:
		return "Revoked"
	if get_datetime(link.expires_at) <= now:
		return "Expired"
	return "Active"


# endregion ASSIGNMENT LINK SECURITY


# =============================================================================
# region MANAGER LINK STATION
# =============================================================================

@frappe.whitelist(methods=["GET"])
def get_kitchen_assignment_links(run_name):
	"""List link state without ever returning a previously generated bearer token."""
	_require_app_user()
	if not _can_manage_links():
		return {"can_manage": False, "links": []}
	run = frappe.get_doc("BulkBite Production Run", run_name)
	run.check_permission("read")
	assigned = {row.employee for row in _active_assignments(run)}
	links = []
	seen = set()
	for row in frappe.get_all(
		ASSIGNMENT_LINK_DOCTYPE,
		filters={"production_run": run.name},
		fields=["name", "employee", "creation", "expires_at", "revoked_at"],
		order_by="creation desc",
	):
		if row.employee not in assigned or row.employee in seen:
			continue
		seen.add(row.employee)
		links.append(_serialize_link_state(row))
	return {"can_manage": True, "links": links}


@frappe.whitelist(methods=["POST"])
def generate_kitchen_assignment_link(run_name, employee):
	"""Rotate one employee's private link and return the new bearer token once."""
	_require_manager()
	run, assignment = _assigned_employee(run_name, employee)
	if run.docstatus == 2:
		frappe.throw(_("A cancelled production run cannot issue kitchen links."), frappe.ValidationError)
	now = now_datetime()
	_revoke_active_links(run.name, employee, revoked_at=now)
	raw_token = secrets.token_urlsafe(48)
	link = frappe.get_doc(
		{
			"doctype": ASSIGNMENT_LINK_DOCTYPE,
			"production_run": run.name,
			"employee": employee,
			"employee_name": assignment.employee_name,
			"token_hash": _token_hash(raw_token),
			"expires_at": add_days(now, ASSIGNMENT_LINK_LIFETIME_DAYS),
		}
	)
	link.insert(ignore_permissions=True)
	return {
		**_serialize_link_state(link),
		"path": f"/bulkbite/kitchen-assignment#{raw_token}",
	}


@frappe.whitelist(methods=["POST"])
def revoke_kitchen_assignment_link(run_name, employee):
	_require_manager()
	_assigned_employee(run_name, employee)
	_revoke_active_links(run_name, employee)
	return {"employee": employee, "status": "Revoked"}


def _serialize_link_state(link):
	return {
		"employee": link.employee,
		"status": _link_status(link),
		"created_on": link.creation,
		"expires_at": link.expires_at,
	}


# endregion MANAGER LINK STATION


# =============================================================================
# region RESTRICTED WORKER PROJECTION
# =============================================================================

@frappe.whitelist(allow_guest=True, methods=["POST"])
def resolve_kitchen_assignment(token=None):
	"""Resolve a bearer token into one lane and the shared cooking method only."""
	if not token or len(token) > 512:
		frappe.throw(_("This kitchen link is invalid or no longer available."), frappe.PermissionError)
	wanted_hash = _token_hash(token)
	link_name = frappe.db.get_value(ASSIGNMENT_LINK_DOCTYPE, {"token_hash": wanted_hash}, "name")
	if not link_name:
		frappe.throw(_("This kitchen link is invalid or no longer available."), frappe.PermissionError)
	link = frappe.get_doc(ASSIGNMENT_LINK_DOCTYPE, link_name)
	if not hmac.compare_digest(str(link.token_hash), wanted_hash):
		frappe.throw(_("This kitchen link is invalid or no longer available."), frappe.PermissionError)
	status = _link_status(link)
	if status == "Revoked":
		frappe.throw(_("This kitchen link has been revoked. Ask the manager for a new link."), frappe.PermissionError)
	if status == "Expired":
		frappe.throw(_("This kitchen link has expired. Ask the manager for a new link."), frappe.PermissionError)

	run, assignment = _assigned_employee(link.production_run, link.employee)
	if run.docstatus == 2:
		frappe.throw(_("This production run was cancelled."), frappe.PermissionError)
	assignments = _active_assignments(run)
	lane_number = next(index for index, row in enumerate(assignments, start=1) if row.employee == link.employee)
	instructions = build_run_instruction_plan(run.recipe, run.planned_output_qty, max(len(assignments), 1))
	lane = next((row for row in instructions.get("worker_lanes", []) if int(row.get("lane") or 0) == lane_number), None)
	if not lane:
		frappe.throw(_("This employee does not have a worker lane in the current cooking plan."), frappe.ValidationError)

	frappe.db.set_value(
		ASSIGNMENT_LINK_DOCTYPE,
		link.name,
		"last_accessed_at",
		now_datetime(),
		update_modified=False,
	)
	return {
		"run": {
			"name": run.name,
			"production_date": run.production_date,
			"recipe_name": instructions.get("recipe_name"),
			"output_qty": instructions.get("output_qty"),
			"output_uom": instructions.get("output_uom"),
		},
		"employee": {
			"name": assignment.employee,
			"full_name": assignment.employee_name,
			"lane": lane_number,
		},
		"lane": _restricted_lane_projection(lane, assignments),
		"instructions": _restricted_instruction_projection(instructions),
	}


def _restricted_lane_projection(lane, assignments):
	names_by_lane = {
		index: row.employee_name or row.employee
		for index, row in enumerate(assignments, start=1)
	}
	steps = []
	for row in lane.get("steps", []):
		step = _pick(
			row,
			"kind",
			"task_id",
			"step_number",
			"step_name",
			"start_minute",
			"end_minute",
			"duration_minutes",
			"equipment_type",
			"is_critical",
			"after_step_number",
		)
		if row.get("kind") == "assist":
			step["assist_with"] = [names_by_lane.get(int(number), _("another worker")) for number in row.get("assisting_workers", [])]
		steps.append(step)
	return {
		"lane": lane.get("lane"),
		"available_at": lane.get("available_at"),
		"steps": steps,
	}


def _restricted_instruction_projection(instructions):
	return {
		"estimated_elapsed_minutes": instructions.get("estimated_elapsed_minutes"),
		"critical_path_minutes": instructions.get("critical_path_minutes"),
		"warnings": list(instructions.get("warnings") or []),
		"ingredients": [
			_pick(
				row,
				"item_code",
				"item_name",
				"quantity",
				"uom",
				"prepared_quantity",
				"prepared_uom",
				"piece_count_estimate",
				"piece_count_label",
				"preparation_yield_note",
			)
			for row in instructions.get("ingredients", [])
		],
		"equipment": [
			_pick(
				row,
				"name",
				"equipment_type_name",
				"quantity_available",
				"concurrent_batch_limit",
				"capacity_qty",
				"capacity_uom",
				"total_concurrent_capacity",
			)
			for row in instructions.get("equipment", [])
		],
		"steps": [
			_pick(
				row,
				"task_id",
				"step_number",
				"step_name",
				"objective",
				"instruction",
				"substeps",
				"quality_checkpoint",
				"estimated_minutes",
				"duration_minutes",
				"equipment_type",
				"equipment_name",
				"batch_count",
				"batch_index",
				"batch_load_qty",
				"batch_capacity_uom",
				"scheduled_start",
				"scheduled_end",
				"early_start",
				"late_start",
				"slack_minutes",
				"is_critical",
				"minimum_workers",
				"requires_active_worker",
			)
			for row in instructions.get("steps", [])
		],
	}


def _pick(row, *fields):
	return {field: row.get(field) for field in fields if field in row}


# endregion RESTRICTED WORKER PROJECTION
