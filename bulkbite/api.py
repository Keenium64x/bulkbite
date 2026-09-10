from __future__ import annotations

import json
import csv
import hashlib
import io
from pathlib import Path

import frappe
from frappe import _
from frappe.model.dynamic_links import get_dynamic_link_map
from frappe.model.rename_doc import get_link_fields
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, nowdate
from frappe.utils.background_jobs import get_job
from openpyxl import load_workbook

from bulkbite.stock_ledger import append_stock_event, get_stock_balance, get_valuation_rate
from bulkbite.stock_production import derive_usage_from_remaining, get_available_stock, load_expected_usage, round_operational_quantity
from bulkbite.document_ai import ai_is_configured, extract_measurements_with_ai
from bulkbite.document_extraction import extract_measurement_rows, resolve_private_source
from bulkbite.document_text import extract_private_text
from bulkbite.receipt_extraction import extract_receipt_review
from bulkbite.invoice_extraction import extract_cost_invoice_review
from bulkbite.finance_ledger import build_finance_ledger_workbook, create_actual_expense, get_finance_ledger
from bulkbite.truth_ledger import append_truth_event
from bulkbite.scan_identity import find_scan_owner, item_scan_codes, normalize_scan_code
from bulkbite.variance import calculate_output_variance, calculate_usage_variance
from bulkbite.planning import (
	build_buying_plan,
	build_dashboard_financial_summary,
	build_plan_snapshot,
	build_spend_report,
	calculate_customer_demand,
	freeze_buying_theory,
	load_buying_theory,
)
from bulkbite.costing import calculate_operating_costs, enrich_spend_report
from bulkbite.workforce import (
	calculate_assignment_pay,
	calculate_capacity_forecast,
	calculate_weekly_capacity,
	calculate_run_performance,
	get_employee_capacity_snapshot,
	get_employee_production_history,
)
from bulkbite.price_workbook import (
	apply_price_import,
	build_price_workbook,
	get_price_field_contract,
	improve_price_import,
	inspect_price_import,
	preview_price_import,
	review_price_import,
)
from bulkbite.setup_workbook import (
	apply_workspace_import,
	build_workspace_workbook,
	get_workspace_contract,
	inspect_workspace_file,
	preview_workspace_import,
	review_workspace_import,
)
from bulkbite.production_instructions import build_run_instruction_plan
from bulkbite.production_periods import (
	load_service_period_records,
	mark_service_period_range_skipped,
	mark_service_period_skipped,
	missed_service_periods,
	production_calendar_slot,
	resolve_current_service_period,
)
from bulkbite.operational_actions import (
	build_operational_action_snapshot,
	get_container_position_snapshot,
	get_default_container_suggestion,
	get_operational_calendar_snapshot,
	materialize_operational_actions,
)


# =============================================================================
# region FRONTEND SNAPSHOT
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_workspace_snapshot():
	_require_app_user()
	result = {
		"user": frappe.session.user,
		"company": "BulkBite",
		"setup_required": not bool(frappe.db.exists("BulkBite Location", "Ingredients")),
		"counts": {
			"ingredients": frappe.db.count("BulkBite Item", {"item_type": "Ingredient", "track_stock": 1, "enabled": 1}),
			"receipt_intakes": frappe.db.count("BulkBite Receipt Intake", {"status": ("!=", "Rejected")}),
			"received_receipts": frappe.db.count("BulkBite Receipt Intake", {"stock_events_posted": 1}),
			"draft_production_runs": frappe.db.count("BulkBite Production Run", {"docstatus": 0}),
			"posted_production_runs": frappe.db.count("BulkBite Production Run", {"docstatus": 1}),
		},
		"recent_runs": frappe.get_all(
			"BulkBite Production Run",
			fields=["name", "production_date", "finished_item", "planned_output_qty", "actual_output_qty", "material_cost_variance", "docstatus", "output_stock_event", "actual_elapsed_hours", "actual_team_size", "actual_labour_hours", "actual_labour_minutes_per_kg", "planned_takt_minutes_per_kg", "takt_variance_minutes_per_kg", "takt_status"],
			order_by="production_date desc, modified desc",
			limit=200,
		),
		"recent_receipts": frappe.get_all(
			"BulkBite Receipt Intake",
			fields=["name", "supplier", "supplier_invoice_number", "invoice_date", "subtotal_amount", "tax_amount", "total_amount", "status", "stock_events_posted", "accountant_exported"],
			order_by="invoice_date desc, modified desc",
			limit=200,
		),
		"recent_cost_invoices": frappe.get_all(
			"BulkBite Cost Invoice",
			fields=["name", "payee", "invoice_number", "invoice_date", "subtotal_amount", "tax_amount", "total_amount", "status", "costs_posted"],
			order_by="invoice_date desc, modified desc",
			limit=200,
		),
		"options": {
			"locations": frappe.get_all("BulkBite Location", filters={"enabled": 1}, pluck="name", order_by="name"),
			"recipes": frappe.get_all("BulkBite Recipe", filters=[["status", "=", "Approved"], *_exclude_archived_setup_records("BulkBite Recipe")], fields=["name", "recipe_name", "finished_item as item", "nominal_output_qty as quantity", "output_uom as uom"], order_by="recipe_name"),
			"suppliers": frappe.get_all("BulkBite Supplier", filters={"enabled": 1}, pluck="name", order_by="name"),
			"production_plans": frappe.get_all("BulkBite Production Plan", filters=[["status", "in", ["Relative Draft", "Dated Draft", "Active"]], *_exclude_archived_setup_records("BulkBite Production Plan")], fields=["name as value", "plan_title as label"], order_by="modified desc"),
			"customer_plan_types": frappe.get_all("BulkBite Customer Plan Type", filters={"enabled": 1}, fields=["name", "serving_size_g", "meals_per_day", "days_per_week", "cycle_weeks"], order_by="serving_size_g"),
			"item_categories": frappe.get_all("BulkBite Item Category", filters={"enabled": 1}, fields=["name", "default_supplier"], order_by="name"),
			"operating_cost_rules": frappe.get_all("BulkBite Operating Cost Rule", filters={"enabled": 1}, fields=["name as value", "cost_name as label", "cost_category", "basis", "rate"], order_by="cost_category, cost_name"),
			"employees": frappe.get_all("BulkBite Employee", filters={"status": "Active", "available_for_production": 1}, fields=["name as value", "full_name as label", "employee_type", "available_hours_per_run"], order_by="full_name"),
			"team_templates": _get_team_templates(),
		},
	}
	for run in result["recent_runs"]:
		for field in ("planned_output_qty", "actual_output_qty"):
			run[field] = round_operational_quantity(run.get(field))
	result["operations"] = build_operational_action_snapshot()
	_enrich_run_workforce_evidence(result["recent_runs"])
	_enrich_document_effects(result["recent_receipts"], "BulkBite Receipt Line", "items")
	_enrich_document_effects(result["recent_cost_invoices"], "BulkBite Cost Invoice Line", "costs")
	return result


def _enrich_run_workforce_evidence(runs):
	"""Provide calculated historical team evidence for runs saved before run-level fields existed."""
	if not runs:
		return
	assignments = frappe.get_all(
		"BulkBite Production Employee",
		filters={"parent": ("in", [row.name for row in runs]), "parenttype": "BulkBite Production Run", "completion_status": "Completed"},
		fields=["parent", "employee", "hours_worked"],
	)
	by_run = {}
	for row in assignments:
		by_run.setdefault(row.parent, []).append(row)
	for run in runs:
		if flt(run.actual_labour_hours) > 0:
			continue
		team = by_run.get(run.name, [])
		team_hours = sum(flt(row.hours_worked) for row in team)
		team_size = len({row.employee for row in team if row.employee})
		run.actual_team_size = team_size
		run.actual_labour_hours = round(team_hours, 2)
		run.actual_elapsed_hours = round(team_hours / team_size, 2) if team_size else 0
		run.actual_labour_minutes_per_kg = round(team_hours * 60 / flt(run.actual_output_qty), 2) if flt(run.actual_output_qty) else 0


def _enrich_document_effects(documents, child_doctype, effect_type):
	"""Add compact line effects to receipt and cost-invoice history rows."""
	if not documents:
		return
	children = frappe.get_all(
		child_doctype,
		filters={"parent": ("in", [row.name for row in documents])},
		fields=["parent", "qty", "uom"] if effect_type == "items" else ["parent", "cost_category", "cost_entry"],
	)
	grouped = {}
	for child in children:
		grouped.setdefault(child.parent, []).append(child)
	for document in documents:
		rows = grouped.get(document.name, [])
		document["line_count"] = len(rows)
		if effect_type == "items":
			quantities = {}
			for row in rows:
				quantities[row.uom or "Unit"] = quantities.get(row.uom or "Unit", 0) + flt(row.qty)
			document["item_count"] = len(rows)
			document["total_stock_quantity"] = round_operational_quantity(sum(flt(row.qty) for row in rows))
			document["stock_uoms"] = ", ".join(sorted({row.uom for row in rows if row.uom}))
			document["stock_quantity_summary"] = ", ".join(f"{round_operational_quantity(value)} {uom}" for uom, value in sorted(quantities.items()))
		else:
			document["cost_categories"] = ", ".join(sorted({row.cost_category for row in rows if row.cost_category}))
			document["posted_entry_count"] = sum(1 for row in rows if row.cost_entry)


@frappe.whitelist(methods=["GET"])
def get_inventory_snapshot(location=None):
	"""Return ingredient balances and valuation for the worker Inventory view."""
	_require_app_user()
	location = location or "Ingredients"
	items = frappe.get_all(
		"BulkBite Item",
		filters={"item_type": "Ingredient", "track_stock": 1, "enabled": 1},
		fields=["item_code", "item_name", "stock_uom", "theory_valuation_rate"],
		order_by="item_name",
	)
	for item in items:
		item["location"] = location
		item["actual_qty"] = round_operational_quantity(get_available_stock(item.item_code, location))
		item["valuation_rate"] = get_valuation_rate(item.item_code, location)
		item["stock_value"] = round(flt(item["actual_qty"]) * flt(item["valuation_rate"]), 2)
	return {"location": location, "items": items}


@frappe.whitelist(methods=["GET"])
def get_finance_workspace(from_date=None, to_date=None):
	"""Load the direct Finance workspace without changing cost or stock records."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	start = getdate(from_date) if from_date else getdate(nowdate()).replace(day=1)
	end = getdate(to_date) if to_date else add_days(add_months(start, 1), -1)
	if start > end:
		frappe.throw(_("From date must be on or before to date."))
	operating = calculate_operating_costs(start, end)
	workforce = _current_workforce_snapshot()
	spend = enrich_spend_report(build_spend_report(start, end))
	expected_amounts = {row["name"]: row["amount"] for row in operating["expected_rows"]}
	rules = frappe.get_all(
		"BulkBite Operating Cost Rule",
		filters={"cost_category": ("!=", "Labour")},
		fields=[
			"name", "cost_code", "cost_name", "cost_category", "basis", "rate",
			"employee_count", "hours_per_employee", "default_quantity", "recurrence",
			"effective_from", "effective_to", "vat_treatment", "accounting_category",
			"payee", "enabled", "notes",
		],
		order_by="enabled desc, cost_category asc, cost_name asc",
	)
	for rule in rules:
		rule["period_amount"] = expected_amounts.get(rule.name, 0)
	adjustments = frappe.get_all(
		"BulkBite Price Adjustment",
		fields=[
			"name", "adjustment_code", "adjustment_name", "scope_type", "supplier_offer",
			"supplier", "item_code", "item_category", "adjustment_type", "calculation_basis",
			"value", "threshold_amount", "effective_from", "effective_to", "priority",
			"stackable", "vat_treatment", "enabled", "notes",
		],
		order_by="enabled desc, priority asc, adjustment_name asc",
	)
	actual_costs = frappe.get_all(
		"BulkBite Cost Entry",
		fields=[
			"name", "cost_date", "expense_type", "cost_rule", "cost_category", "payee", "quantity",
			"unit_rate", "amount", "vat_amount", "production_plan", "production_run", "employee", "evidence_file",
			"accounting_category", "finance_event", "notes",
		],
		order_by="cost_date desc, creation desc",
		limit_page_length=200,
	)
	return {
		"period": {"from_date": start, "to_date": end},
		"summary": {
			"expected_total": operating["expected_total"],
			"actual_total": operating["actual_total"],
			"variance": round(flt(operating["actual_total"]) - flt(operating["expected_total"]), 2),
			"active_adjustments": sum(1 for row in adjustments if row.enabled),
			"expected_savings": spend["summary"].get("expected_savings", 0),
			"actual_savings": round(sum(
				flt(row.get("actual_amount")) for row in spend.get("savings") or []
				if row.get("effect") == "saving"
			), 2),
		},
		"forecast": {
			"revenue": spend.get("profit", {}).get("revenue", 0),
			"food_cost": spend["summary"].get("expected_spend", 0),
			"operating_cost": operating["expected_total"],
			"discounts_and_savings": spend["summary"].get("expected_savings", 0),
			"added_buying_costs": spend["summary"].get("expected_added_buying_costs", 0),
			"operating_profit": spend.get("profit", {}).get("expected_operating_result", 0),
			"margin_percent": round(
				flt(spend.get("profit", {}).get("expected_operating_result")) / flt(spend.get("profit", {}).get("revenue")) * 100,
				1,
			) if flt(spend.get("profit", {}).get("revenue")) else 0,
			"actual_revenue_basis": spend.get("profit", {}).get("revenue_basis"),
			"actual_food_cost": spend["summary"].get("actual_spend", 0),
			"actual_operating_cost": operating["actual_total"],
			"actual_operating_result": spend.get("profit", {}).get("actual_operating_result", 0),
		},
		"breakdown": operating["breakdown"],
		"workforce": workforce,
		"expected_costs": rules,
		"adjustments": adjustments,
		"actual_costs": actual_costs,
		"expense_types": frappe.get_all(
			"BulkBite Expense Type",
			fields=["name", "expense_type_name", "cost_category", "document_type", "default_vat_treatment", "accounting_category", "enabled", "notes"],
			order_by="enabled desc, expense_type_name asc",
		),
		"finance_ledger": get_finance_ledger(start, end),
		"can_create_expense_types": frappe.has_permission("BulkBite Expense Type", "create"),
		"options": {
			"suppliers": _finance_link_options("BulkBite Supplier", "supplier_name"),
			"items": _finance_link_options("BulkBite Item", "item_name"),
			"item_categories": _finance_link_options("BulkBite Item Category", "category_name"),
			"supplier_offers": _finance_link_options("BulkBite Supplier Offer", "name"),
		},
	}


@frappe.whitelist(methods=["GET"])
def get_finance_ledger_workspace(from_date=None, to_date=None):
	"""Expose verified finance events to managers and accountants without mutation."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	start = getdate(from_date) if from_date else getdate(nowdate()).replace(day=1)
	end = getdate(to_date) if to_date else add_days(add_months(start, 1), -1)
	if start > end:
		frappe.throw(_("From date must be on or before to date."))
	return get_finance_ledger(start, end)


def _current_workforce_snapshot():
	plan_name = frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")
	if not plan_name:
		return get_employee_capacity_snapshot()
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	return get_employee_capacity_snapshot(calculate_customer_demand(plan.customer_mix))


@frappe.whitelist(methods=["POST"])
def save_expected_cost_rule(payload=None):
	"""Create or update one reviewed non-employee expected-cost rule."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	if not data.get("cost_name") or not data.get("cost_category") or not data.get("basis"):
		frappe.throw(_("Cost type, category, and basis are required."))
	if data.get("cost_category") == "Labour":
		frappe.throw(_("Employee costs are configured through employee types under Production."))
	if data.get("basis") == "Hourly":
		if int(data.get("employee_count") or 0) < 1 or flt(data.get("hours_per_employee")) <= 0:
			frappe.throw(_("Hourly costs need at least one employee and hours per employee."))
	elif data.get("basis") == "Fixed" and flt(data.get("default_quantity")) <= 0:
		frappe.throw(_("Fixed costs need an expected quantity."))
	values = _pick_finance_fields(data, {
		"cost_name", "cost_category", "basis", "rate", "employee_count",
		"hours_per_employee", "default_quantity", "recurrence", "effective_from",
		"effective_to", "vat_treatment", "accounting_category", "payee", "enabled", "notes",
	})
	if not data.get("name"):
		values["cost_code"] = _new_finance_code("COST", "BulkBite Operating Cost Rule", "cost_code")
	doc = _save_finance_record("BulkBite Operating Cost Rule", data.get("name"), values)
	return {"name": doc.name, "cost_name": doc.cost_name, "enabled": doc.enabled}


@frappe.whitelist(methods=["POST"])
def save_miscellaneous_cost(payload=None):
	"""Create one direct actual cost and attach all reviewed private evidence files."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	evidence_urls = [row.get("evidence_file") for row in _as_list(data.get("evidence_files"))]
	if any(evidence_urls):
		_validate_private_evidence(evidence_urls)
	amount = flt(data.get("amount")) or round(flt(data.get("quantity")) * flt(data.get("unit_rate")), 2)
	if not data.get("cost_date") or not data.get("expense_type") or not data.get("cost_category") or amount <= 0:
		frappe.throw(_("Cost date, expense type, category, and an actual cost greater than zero are required."))
	values = _pick_finance_fields(data, {
		"cost_date", "expense_type", "cost_rule", "cost_category", "payee", "quantity", "unit_rate",
		"vat_amount", "currency", "production_plan", "accounting_category", "notes",
	})
	values["amount"] = amount
	values["evidence_file"] = evidence_urls[0] if evidence_urls else None
	doc, event = create_actual_expense(values)
	if any(evidence_urls):
		_attach_private_evidence(evidence_urls, doc.doctype, doc.name)
	return {"name": doc.name, "cost_date": doc.cost_date, "amount": doc.amount, "finance_event": event.name}


@frappe.whitelist(methods=["POST"])
def save_price_adjustment(payload=None):
	"""Create or update one reviewed discount, saving, fee, or buying-cost rule."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	if not data.get("adjustment_name") or not data.get("adjustment_type") or not data.get("scope_type"):
		frappe.throw(_("Adjustment name, type, and scope are required."))
	values = _pick_finance_fields(data, {
		"adjustment_name", "scope_type", "supplier_offer", "supplier", "item_code",
		"item_category", "adjustment_type", "calculation_basis", "value",
		"threshold_amount", "effective_from", "effective_to", "priority", "stackable",
		"vat_treatment", "enabled", "notes",
	})
	if not data.get("name"):
		values["adjustment_code"] = _new_finance_code("ADJ", "BulkBite Price Adjustment", "adjustment_code")
	doc = _save_finance_record("BulkBite Price Adjustment", data.get("name"), values)
	return {"name": doc.name, "adjustment_name": doc.adjustment_name, "enabled": doc.enabled}


def _finance_link_options(doctype, label_field):
	fields = ["name"] + ([label_field] if label_field != "name" else [])
	return [
		{"value": row.name, "label": row.get(label_field) or row.name}
		for row in frappe.get_all(
			doctype,
			fields=fields,
			filters=_exclude_archived_setup_records(doctype) or None,
			order_by=f"{label_field} asc",
			limit_page_length=1000,
		)
	]


def _pick_finance_fields(data, allowed_fields):
	return {field: data.get(field) for field in allowed_fields if field in data}


def _new_finance_code(prefix, doctype, fieldname):
	while True:
		code = f"{prefix}-{frappe.generate_hash(length=8).upper()}"
		if not frappe.db.exists(doctype, {fieldname: code}):
			return code


def _save_finance_record(doctype, name, values):
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.check_permission("write" if name else "create")
	doc.update(values)
	doc.save()
	return doc


# endregion FRONTEND SNAPSHOT


# =============================================================================
# region EMPLOYEE AND CAPACITY MANAGEMENT
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_employee_workspace():
	"""Return workforce status, employee types, profiles, and assignment options."""
	_require_roles("BulkBite Manager", "BulkBite Worker", "BulkBite Accountant")
	types = frappe.get_all(
		"BulkBite Employee Type",
		fields=["name", "employee_type_name", "description", "capacity_basis", "capacity_per_worker", "expected_hours_per_run", "payment_basis", "payment_rate", "working_assumptions", "enabled"],
		order_by="enabled desc, employee_type_name",
	)
	employees = frappe.get_all(
		"BulkBite Employee",
		fields=["name", "full_name", "employee_type", "status", "available_for_production", "available_hours_per_run", "email_address", "phone_number", "start_date", "end_date", "use_payment_override", "payment_basis_override", "payment_rate_override", "notes"],
		order_by="status asc, full_name",
	)
	documents = frappe.get_all(
		"BulkBite Employee Document",
		filters={"parent": ("in", [row.name for row in employees])},
		fields=["name", "parent", "document_type", "document_file", "expiry_date", "notes"],
		order_by="idx",
	) if employees else []
	documents_by_employee = {}
	for document in documents:
		documents_by_employee.setdefault(document.parent, []).append(document)
	history_by_employee = get_employee_production_history([employee.name for employee in employees])
	for employee in employees:
		employee["documents"] = documents_by_employee.get(employee.name, [])
		employee["production_history"] = history_by_employee.get(employee.name, [])
		employee["total_completed_hours"] = round(sum(
			flt(row.get("hours_worked")) for row in employee["production_history"]
			if row.get("completion_status") == "Completed"
		), 2)
	return {"capacity": _current_workforce_snapshot(), "employee_types": types, "employees": employees}


@frappe.whitelist(methods=["POST"])
def save_employee_type(payload=None):
	"""Create or update one role with measurable capacity and a payment rule."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	values = _pick_finance_fields(data, {
		"employee_type_name", "description", "capacity_basis", "capacity_per_worker",
		"expected_hours_per_run", "payment_basis", "payment_rate", "working_assumptions", "enabled",
	})
	if not values.get("employee_type_name") or not values.get("capacity_basis") or not values.get("payment_basis"):
		frappe.throw(_("Employee type, capacity basis, and payment basis are required."))
	doc = _save_finance_record("BulkBite Employee Type", data.get("name"), values)
	return {"name": doc.name, "employee_type_name": doc.employee_type_name}


@frappe.whitelist(methods=["POST"])
def save_employee(payload=None):
	"""Create or update one employee profile and its reviewed private documents."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	documents = _as_list(data.get("documents"))
	file_urls = [row.get("document_file") for row in documents if row.get("document_file")]
	if file_urls:
		_validate_private_evidence(file_urls)
	values = _pick_finance_fields(data, {
		"full_name", "employee_type", "status", "available_for_production", "available_hours_per_run", "email_address",
		"phone_number", "start_date", "end_date", "use_payment_override",
		"payment_basis_override", "payment_rate_override", "notes",
	})
	if not values.get("full_name") or not values.get("employee_type"):
		frappe.throw(_("Employee name and employee type are required."))
	if flt(values.get("available_hours_per_run")) < 0:
		frappe.throw(_("Hours available per production run cannot be negative."))
	if values.get("available_for_production") and not flt(values.get("available_hours_per_run")):
		values["available_hours_per_run"] = flt(frappe.db.get_value("BulkBite Employee Type", values.get("employee_type"), "expected_hours_per_run"))
	doc = frappe.get_doc("BulkBite Employee", data.name) if data.get("name") else frappe.new_doc("BulkBite Employee")
	doc.check_permission("write" if data.get("name") else "create")
	doc.update(values)
	doc.set("documents", [
		{"document_type": row.get("document_type") or _("Employee document"), "document_file": row.get("document_file"), "expiry_date": row.get("expiry_date"), "notes": row.get("notes")}
		for row in documents if row.get("document_file")
	])
	doc.save()
	if file_urls:
		_attach_private_evidence(file_urls, doc.doctype, doc.name)
	return {"name": doc.name, "full_name": doc.full_name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def save_production_employees(name, employees=None, team_template=None, actual_elapsed_hours=None, scheduled_elapsed_hours=None):
	"""Freeze reviewed employee attendance and pay facts for one draft run."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus != 0:
		frappe.throw(_("Employees can only be changed on a draft production run."))
	actual_time_supplied = actual_elapsed_hours is not None
	elapsed_hours = flt(actual_elapsed_hours) if actual_time_supplied else flt(run.actual_elapsed_hours)
	if actual_time_supplied and elapsed_hours < 0:
		frappe.throw(_("Actual elapsed time cannot be negative."))
	planned_window_supplied = scheduled_elapsed_hours is not None
	planned_window_hours = flt(scheduled_elapsed_hours) if planned_window_supplied else flt(run.scheduled_elapsed_hours)
	if planned_window_hours < 0:
		frappe.throw(_("Kitchen time available cannot be negative."))
	existing_by_employee = {row.employee: row for row in run.employees or [] if row.employee}
	rows = []
	for supplied in _as_list(employees):
		if not supplied.get("employee"):
			continue
		employee = frappe.get_doc("BulkBite Employee", supplied.get("employee"))
		if employee.status != "Active":
			frappe.throw(_("{0} is not an active employee.").format(employee.full_name))
		employee_type = frappe.get_doc("BulkBite Employee Type", employee.employee_type)
		available_hours, custom_hours = _resolve_employee_availability(
			supplied,
			planned_window_hours,
			planned_window_supplied,
			flt(employee.available_hours_per_run) or flt(employee_type.expected_hours_per_run),
		)
		if available_hours < 0:
			frappe.throw(_("Available hours for {0} cannot be negative.").format(employee.full_name))
		payment_basis = employee.payment_basis_override if employee.use_payment_override and employee.payment_basis_override else employee_type.payment_basis
		payment_rate = employee.payment_rate_override if employee.use_payment_override else employee_type.payment_rate
		existing_assignment = existing_by_employee.get(employee.name)
		preserve_actual = not actual_time_supplied and flt(run.actual_elapsed_hours) > 0 and existing_assignment
		completion_status = (
			existing_assignment.completion_status
			if preserve_actual
			else supplied.get("completion_status") if actual_time_supplied else "Assigned"
		) or "Completed"
		if actual_time_supplied and completion_status == "Assigned":
			completion_status = "Completed"
		hours_worked = (
			flt(existing_assignment.hours_worked)
			if preserve_actual
			else elapsed_hours if actual_time_supplied
			else 0
		)
		if completion_status in {"Absent", "Cancelled"}:
			hours_worked = 0
		pay = calculate_assignment_pay(frappe._dict({"payment_basis": payment_basis, "payment_rate": payment_rate}), hours_worked, completion_status)
		rows.append({
			"employee": employee.name, "employee_name": employee.full_name, "employee_type": employee.employee_type,
			"available_hours": available_hours, "custom_hours": custom_hours, "hours_worked": hours_worked, "completion_status": completion_status,
			**pay, "notes": supplied.get("notes"),
		})
	run.team_template = team_template
	if planned_window_supplied:
		run.scheduled_elapsed_hours = planned_window_hours
	if actual_time_supplied:
		performance = calculate_run_performance(run.actual_output_qty, elapsed_hours, rows, run.planned_takt_minutes_per_kg)
		for fieldname, value in performance.items():
			run.set(fieldname, value)
	run.set("employees", rows)
	run.save()
	return _serialize_run(run)


def _resolve_employee_availability(supplied, planned_window_hours, planned_window_supplied, default_available_hours):
	"""Return the planned hours and whether this employee overrides the shared kitchen window."""
	custom_hours = _as_bool(supplied.get("custom_hours"))
	if planned_window_supplied and not custom_hours:
		return flt(planned_window_hours), False
	supplied_hours = supplied.get("available_hours")
	if supplied_hours in (None, ""):
		return flt(default_available_hours), custom_hours
	return flt(supplied_hours), custom_hours


@frappe.whitelist(methods=["POST"])
def save_team_template(payload=None):
	"""Create or update one reusable production crew template."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	if not data.get("template_name"):
		frappe.throw(_("Enter a team template name."))
	members = []
	seen = set()
	for row in _as_list(data.get("members")):
		employee = row.get("employee")
		if not employee or employee in seen:
			continue
		seen.add(employee)
		members.append({"employee": employee, "default_hours_override": flt(row.get("default_hours_override")), "enabled": bool(row.get("enabled", True))})
	if not members:
		frappe.throw(_("Add at least one employee to the team template."))
	doc = frappe.get_doc("BulkBite Team Template", data.name) if data.get("name") else frappe.new_doc("BulkBite Team Template")
	doc.update({"template_name": data.template_name, "default_elapsed_hours": flt(data.get("default_elapsed_hours")) or 4, "enabled": bool(data.get("enabled", True)), "notes": data.get("notes")})
	doc.set("members", members)
	doc.save()
	return {"name": doc.name, "template_name": doc.template_name}


def _get_team_templates():
	rows = []
	for template in frappe.get_all("BulkBite Team Template", filters={"enabled": 1}, fields=["name", "template_name", "default_elapsed_hours", "notes"], order_by="template_name"):
		template["members"] = frappe.get_all(
			"BulkBite Team Template Member",
			filters={"parent": template.name, "parenttype": "BulkBite Team Template", "enabled": 1},
			fields=["employee", "employee_name", "employee_type", "default_hours_override"],
			order_by="idx asc",
		)
		template["team_size"] = len(template["members"])
		rows.append(template)
	return rows


# endregion EMPLOYEE AND CAPACITY MANAGEMENT


# =============================================================================
# region AUXILIARY RECORD FORMS
# =============================================================================

_AUXILIARY_FORM_DOCTYPES = {
	"BulkBite Item": {"label": "Items", "singular_label": "item", "description": "Ingredients, finished meals, categories, units, scan codes, and theory rates."},
	"BulkBite Item Category": {"label": "Food categories", "singular_label": "category", "description": "Group ingredients such as dry and fresh food and choose the usual supplier."},
	"BulkBite Supplier": {"label": "Suppliers", "singular_label": "supplier", "description": "Supplier identity and accountant export references."},
	"BulkBite Supplier Offer": {"label": "Supplier offers", "singular_label": "offer", "description": "Normal and discounted supplier pack prices used by theoretical buying plans."},
	"BulkBite Price Adjustment": {"label": "Price adjustments", "singular_label": "price adjustment", "description": "Discounts, rebates, VAT, delivery fees, free delivery, and other buying adjustments."},
	"BulkBite Operating Cost Rule": {"label": "Operating cost rules", "singular_label": "operating cost rule", "description": "Expected labour, packaging, utilities, rent, delivery, and other costs."},
	"BulkBite Cost Entry": {"label": "Actual costs", "singular_label": "actual cost", "description": "Evidence-backed labour and other actual operating costs for financial reporting."},
	"BulkBite Cost Invoice": {"label": "Cost invoices", "singular_label": "cost invoice", "description": "Reviewed invoices that create evidence-backed actual operating costs."},
	"BulkBite Expense Type": {"label": "Expense types", "singular_label": "expense type", "description": "Reusable invoice and miscellaneous expense classifications for finance review and accountant export."},
	"BulkBite Customer Plan Type": {"label": "Customer plans", "singular_label": "customer plan", "description": "Serving sizes and schedule assumptions such as Lite 300 g, Standard 450 g, and Full 600 g."},
	"BulkBite Location": {"label": "Locations", "singular_label": "location", "description": "The physical places where ingredients, meals, quarantine, and waste are measured."},
	"BulkBite Recipe": {"label": "Recipes", "singular_label": "recipe", "description": "Versioned meal theory and controlled ingredient quantities."},
	"BulkBite Equipment Type": {"label": "Equipment types", "singular_label": "equipment type", "description": "Available kitchen equipment, batch capacity, and concurrent use limits for production instructions."},
	"BulkBite Production Plan": {"label": "Production plans", "singular_label": "plan", "description": "Planned recipes and meal quantities used by the production workflow."},
	"BulkBite Team Template": {"label": "Team templates", "singular_label": "team template", "description": "Reusable groups that prefill the people expected in a normal production run."},
	"BulkBite Container Type": {"label": "Container types", "singular_label": "container type", "description": "Reusable container capacity, replacement price, and expected return rules."},
	"BulkBite Container Asset": {"label": "Containers", "singular_label": "container", "description": "Individually tracked reusable containers and their current lifecycle state."},
	"BulkBite Operational Schedule": {"label": "Operational schedules", "singular_label": "schedule", "description": "Repeating stock counts, accountant exports, container checks, and other duties."},
	"BulkBite Operational Action": {"label": "Calendar actions", "singular_label": "calendar action", "description": "One-off operational duties and dated occurrences created by recurring schedules."},
	"BulkBite Settings": {"label": "Operational defaults", "singular_label": "setting", "description": "Global kitchen planning defaults and AI method-generation controls."},
}
_AUXILIARY_FIELD_TYPES = {"Data", "Int", "Float", "Currency", "Date", "Select", "Check", "Small Text", "Text", "Long Text", "Link", "Table"}
_AUXILIARY_LIST_FILTER_TYPES = {"Check", "Date", "Link", "Select"}
_AUXILIARY_LIST_COLUMN_TYPES = {"Data", "Int", "Float", "Currency", "Date", "Select", "Check", "Link"}
_AUXILIARY_DELETE_MAX_ROOTS = 100
_AUXILIARY_DELETE_MAX_RECORDS = 1000


@frappe.whitelist(methods=["GET"])
def get_auxiliary_form_catalogue():
	"""Return the permission-aware supporting-record destinations used by linked fields."""
	_require_app_user()
	rows = []
	for doctype, copy in _AUXILIARY_FORM_DOCTYPES.items():
		if not frappe.has_permission(doctype, "read"):
			continue
		is_single = bool(frappe.get_meta(doctype).issingle)
		rows.append({
			"doctype": doctype,
			**copy,
			"is_single": is_single,
			"can_create": not is_single and frappe.has_permission(doctype, "create"),
			"can_read": True,
			"can_delete": not is_single and frappe.has_permission(doctype, "delete"),
		})
	return rows


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record_list(doctype):
	"""List one approved supporting DocType through ordinary Frappe permissions."""
	_require_auxiliary_doctype(doctype, "read")
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field or (meta.autoname.removeprefix("field:") if str(meta.autoname or "").startswith("field:") else None)
	fields = ["name"] + ([title_field] if title_field and title_field != "name" else [])
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=_exclude_archived_setup_records(doctype),
		order_by=f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}",
		limit_page_length=200,
	)
	return [{"name": row.name, "label": row.get(title_field) or row.name} for row in rows]


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record_workspace(doctype, search=None, page=1, page_size=25, filters=None, sort=None):
	"""Return a safe list contract for the existing All setup record page."""
	_require_auxiliary_doctype(doctype, "read")
	meta = frappe.get_meta(doctype)
	columns = _auxiliary_list_columns(meta)
	title_field = _auxiliary_title_field(meta)
	fieldnames = list(dict.fromkeys(["name", title_field, *[column["field"] for column in columns]]))
	fieldnames = [fieldname for fieldname in fieldnames if fieldname and fieldname != "title"]
	page = max(1, int(page or 1))
	page_size = min(100, max(1, int(page_size or 25)))
	start = (page - 1) * page_size
	safe_filters = [*_auxiliary_list_filters(meta, filters), *_exclude_archived_setup_records(doctype)]
	search_filters = _auxiliary_search_filters(search, title_field)
	order_by = _auxiliary_list_order(meta, sort, columns)
	rows = frappe.get_list(
		doctype,
		fields=fieldnames,
		filters=safe_filters or None,
		or_filters=search_filters or None,
		order_by=order_by,
		limit_start=start,
		limit_page_length=page_size,
	)
	if search_filters:
		count_rows = frappe.get_list(
			doctype,
			fields=[{"COUNT": "name", "as": "count"}],
			filters=safe_filters or None,
			or_filters=search_filters,
			limit_page_length=1,
		)
		total = int(count_rows[0].get("count") or 0) if count_rows else 0
	else:
		total = frappe.db.count(doctype, filters=safe_filters or None)
	return {
		"doctype": doctype,
		"label": _AUXILIARY_FORM_DOCTYPES[doctype]["label"],
		"columns": columns,
		"rows": [
			{
				"name": row.name,
				"title": row.get(title_field) or row.name,
				"values": {fieldname: row.get(fieldname) for fieldname in fieldnames if fieldname != "name"},
			}
			for row in rows
		],
		"permissions": {
			"read": True,
			"create": bool(frappe.has_permission(doctype, "create")),
			"bulkDelete": bool(frappe.has_permission(doctype, "delete")),
		},
		"filters": _auxiliary_filter_contract(meta),
		"sort": _as_dict(sort) or None,
		"page": page,
		"page_size": page_size,
		"total": total,
		"has_next": start + len(rows) < total,
	}


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record(doctype, name=None):
	"""Return one safe metadata contract plus values for create or edit."""
	is_single = bool(frappe.get_meta(doctype).issingle)
	_require_auxiliary_doctype(doctype, "read" if name or is_single else "create")
	contract = _auxiliary_form_contract(doctype)
	contract["permissions"] = {
		"read": bool(frappe.has_permission(doctype, "read")),
		"write": bool(frappe.has_permission(doctype, "write")) and not (name and _is_archived_setup_record(doctype, name)),
		"delete": not is_single and bool(frappe.has_permission(doctype, "delete")) and not (name and _is_archived_setup_record(doctype, name)),
	}
	doc = frappe.get_single(doctype) if is_single else frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	if name or is_single:
		doc.check_permission("read")
	return {
		"contract": contract,
		"values": {field["name"]: doc.get(field["name"]) for section in contract["sections"] for field in section["fields"]},
		"tables": {table["name"]: [row.as_dict() for row in doc.get(table["name"])] for table in contract["tables"]},
	}


@frappe.whitelist(methods=["POST"])
def save_auxiliary_record(doctype, values, tables=None, name=None):
	"""Create or update only fields exposed by the approved auxiliary contract."""
	is_single = bool(frappe.get_meta(doctype).issingle)
	_require_auxiliary_doctype(doctype, "write" if name or is_single else "create")
	if name and _is_archived_setup_record(doctype, name):
		frappe.throw(_("This record is retained as historical identity and cannot be changed."), frappe.PermissionError)
	contract = _auxiliary_form_contract(doctype)
	allowed_values = {field["name"] for section in contract["sections"] for field in section["fields"] if not field["read_only"]}
	allowed_tables = {table["name"]: table for table in contract["tables"]}
	doc = frappe.get_single(doctype) if is_single else frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.check_permission("write" if name or is_single else "create")
	for fieldname, value in _as_dict(values).items():
		if fieldname in allowed_values:
			doc.set(fieldname, value)
	for fieldname, rows in _as_dict(tables).items():
		if fieldname not in allowed_tables:
			continue
		allowed_row_fields = {field["name"] for field in allowed_tables[fieldname]["fields"] if not field["read_only"]}
		doc.set(fieldname, [{key: value for key, value in row.items() if key in allowed_row_fields} for row in _as_list(rows)])
	doc.save()
	return {"doctype": doctype, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def plan_auxiliary_record_deletion(doctype, names, default_outcome=None, outcomes_by_doctype=None):
	"""Preview the graph and optionally resolve one mixed delete or unlink plan."""
	_require_auxiliary_doctype(doctype, "delete")
	plan = _auxiliary_deletion_plan(doctype, names)
	if default_outcome:
		plan.public["resolution"] = _public_auxiliary_delete_resolution(
			_resolve_auxiliary_delete_execution(plan, default_outcome, outcomes_by_doctype)
		)
		plan.public["plan_token"] = _auxiliary_delete_plan_token(plan.public, exclude_token=True)
	return plan.public


@frappe.whitelist(methods=["POST"])
def delete_auxiliary_records(doctype, names, plan_token, outcome=None, outcomes_by_doctype=None, approved=False):
	"""Execute one freshly approved mixed unlink and deletion plan atomically."""
	_require_auxiliary_doctype(doctype, "delete")
	if not _as_bool(approved):
		frappe.throw(_("Final deletion approval is required."), frappe.PermissionError)
	if outcome not in {"unlink", "delete", "recursive"}:
		frappe.throw(_("Choose the default action for related records."))
	plan = _auxiliary_deletion_plan(doctype, names)
	resolution = _resolve_auxiliary_delete_execution(plan, outcome, outcomes_by_doctype)
	plan.public["resolution"] = _public_auxiliary_delete_resolution(resolution)
	expected_token = _auxiliary_delete_plan_token(plan.public, exclude_token=True)
	if not plan_token or plan_token != expected_token:
		frappe.throw(_("The connected records or deletion choices changed. Review the deletion plan again."))
	if resolution.blockers:
		frappe.throw(_("The mixed deletion plan is blocked. Review the related record choices."))

	savepoint = "bulkbite_auxiliary_record_deletion"
	frappe.db.savepoint(savepoint)
	deleted = []
	archived = []
	try:
		_unlink_auxiliary_delete_plan(resolution.unlink_edges)
		_clear_auxiliary_delete_plan_links(resolution.delete_edges)
		for node in resolution.archived:
			_archive_auxiliary_setup_record(node, _("Preserved because immutable or protected history still references this record."))
			archived.append({key: node[key] for key in ("doctype", "name", "title")})
		delete_order = resolution.delete_order
		for node in delete_order:
			doc = frappe.get_doc(node["doctype"], node["name"])
			reason = _auxiliary_delete_block_reason(doc)
			if reason:
				frappe.throw(reason, frappe.PermissionError)
			doc.check_permission("delete")
			frappe.delete_doc(node["doctype"], node["name"])
			deleted.append({key: node[key] for key in ("doctype", "name", "title")})
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
	return {
		"deleted": deleted,
		"deleted_count": len(deleted),
		"root_count": len(plan.public["roots"]),
		"dependency_count": max(0, len(deleted) - len(plan.public["roots"])),
		"unlinked_count": len(resolution.unlink_edges),
		"archived": archived,
		"archived_count": len(archived),
		"preserved_count": len(resolution.preserved),
		"outcome": _normalize_auxiliary_delete_outcome(outcome),
		"outcomes_by_doctype": resolution.outcomes_by_doctype,
	}


def _require_auxiliary_doctype(doctype, permission):
	if permission == "read":
		_require_app_user()
	else:
		_require_roles("BulkBite Manager")
	if doctype not in _AUXILIARY_FORM_DOCTYPES:
		frappe.throw(_("{0} is not an approved BulkBite setup record.").format(doctype), frappe.PermissionError)
	if not frappe.has_permission(doctype, permission):
		frappe.throw(_("You do not have permission to {0} {1}.").format(permission, doctype), frappe.PermissionError)


def _exclude_archived_setup_records(doctype):
	if not frappe.db.table_exists("BulkBite Archived Setup Record"):
		return []
	archived_names = frappe.get_all(
		"BulkBite Archived Setup Record",
		filters={"record_doctype": doctype},
		pluck="record_name",
		limit_page_length=10000,
	)
	return [["name", "not in", archived_names]] if archived_names else []


def _is_archived_setup_record(doctype, name):
	if not frappe.db.table_exists("BulkBite Archived Setup Record"):
		return False
	archive_key = hashlib.sha256(f"{doctype}\0{name}".encode("utf-8")).hexdigest()
	return bool(frappe.db.exists("BulkBite Archived Setup Record", archive_key))


def _archive_auxiliary_setup_record(node, reason):
	archive_key = hashlib.sha256(f"{node['doctype']}\0{node['name']}".encode("utf-8")).hexdigest()
	if not frappe.db.exists("BulkBite Archived Setup Record", archive_key):
		frappe.get_doc({
			"doctype": "BulkBite Archived Setup Record",
			"archive_key": archive_key,
			"record_doctype": node["doctype"],
			"record_name": node["name"],
			"record_title": node.get("title") or node["name"],
			"archived_at": now_datetime(),
			"archived_by": frappe.session.user,
			"reason": reason,
		}).insert(ignore_permissions=True)
	meta = frappe.get_meta(node["doctype"])
	if meta.get_field("enabled"):
		frappe.db.set_value(node["doctype"], node["name"], "enabled", 0, update_modified=False)


def _auxiliary_form_contract(doctype):
	meta = frappe.get_meta(doctype)
	sections = [{"label": _AUXILIARY_FORM_DOCTYPES[doctype]["singular_label"].title(), "fields": []}]
	tables = []
	for field in meta.fields:
		if field.fieldtype not in _AUXILIARY_FIELD_TYPES or field.hidden or field.fieldtype in {"Section Break", "Column Break"}:
			continue
		serialized = _serialize_auxiliary_field(field)
		if field.fieldtype == "Table":
			child_meta = frappe.get_meta(field.options)
			tables.append({
				"name": field.fieldname,
				"label": field.label,
				"description": field.description or "",
				"fields": [_serialize_auxiliary_field(child) for child in child_meta.fields if child.fieldtype in _AUXILIARY_FIELD_TYPES and child.fieldtype != "Table" and not child.hidden],
			})
		else:
			sections[0]["fields"].append(serialized)
	return {"doctype": doctype, "sections": sections, "tables": tables}


def _serialize_auxiliary_field(field):
	options = [line for line in str(field.options or "").splitlines() if line] if field.fieldtype == "Select" else field.options
	link_options = []
	if field.fieldtype == "Link" and field.options in _AUXILIARY_FORM_DOCTYPES and frappe.has_permission(field.options, "read"):
		link_options = [{"label": row["label"], "value": row["name"]} for row in get_auxiliary_record_list(field.options)]
	return {
		"name": field.fieldname,
		"label": field.label,
		"type": field.fieldtype,
		"options": options,
		"description": field.description or "",
		"required": bool(field.reqd),
		"read_only": bool(field.read_only),
		"non_negative": bool(field.non_negative),
		"default": field.default,
		"link_options": link_options,
	}


# region 1. LIST CONTRACT

def _auxiliary_title_field(meta):
	title_field = meta.title_field or (meta.autoname.removeprefix("field:") if str(meta.autoname or "").startswith("field:") else None)
	return title_field if title_field and meta.get_field(title_field) else None


def _auxiliary_list_columns(meta):
	columns = [{"field": "title", "label": _AUXILIARY_FORM_DOCTYPES[meta.name]["singular_label"].title(), "type": "data", "sortable": False}]
	seen = {_auxiliary_title_field(meta), "name"}
	for field in meta.fields:
		if field.fieldname in seen or field.hidden or field.fieldtype not in _AUXILIARY_LIST_COLUMN_TYPES:
			continue
		columns.append({"field": field.fieldname, "label": field.label or field.fieldname, "type": _auxiliary_list_type(field), "sortable": True})
		seen.add(field.fieldname)
		if len(columns) >= 5:
			break
	return columns


def _auxiliary_filter_contract(meta):
	filters = []
	for field in meta.fields:
		if field.hidden or field.fieldtype not in _AUXILIARY_LIST_FILTER_TYPES:
			continue
		contract = {"field": field.fieldname, "label": field.label or field.fieldname, "type": _auxiliary_list_type(field)}
		if field.fieldtype == "Check":
			contract["options"] = [{"label": _("Yes"), "value": 1}, {"label": _("No"), "value": 0}]
		elif field.fieldtype == "Select":
			contract["options"] = [{"label": option, "value": option} for option in str(field.options or "").splitlines() if option]
		elif field.fieldtype == "Link" and field.options in _AUXILIARY_FORM_DOCTYPES and frappe.has_permission(field.options, "read"):
			contract["options"] = [{"label": row["label"], "value": row["name"]} for row in get_auxiliary_record_list(field.options)]
		filters.append(contract)
		if len(filters) >= 4:
			break
	return filters


def _auxiliary_list_filters(meta, filters):
	requested = json.loads(filters) if isinstance(filters, str) else filters
	if not requested:
		return []
	if not isinstance(requested, list):
		frappe.throw(_("Record filters must be a list."))
	result = []
	for item in requested:
		field = meta.get_field(item.get("field")) if isinstance(item, dict) else None
		if not field or field.fieldtype not in _AUXILIARY_LIST_FILTER_TYPES:
			frappe.throw(_("Unsupported record filter."))
		if item.get("operator", "=") != "=":
			frappe.throw(_("Only exact record filters are supported."))
		result.append([field.fieldname, "=", item.get("value")])
	return result


def _auxiliary_search_filters(search, title_field):
	term = str(search or "").strip()
	if not term:
		return []
	return [[fieldname, "like", f"%{term}%"] for fieldname in dict.fromkeys([title_field, "name"]) if fieldname]


def _auxiliary_list_order(meta, sort, columns):
	requested = _as_dict(sort)
	fieldname = requested.get("field")
	direction = str(requested.get("direction") or "asc").lower()
	allowed = {column["field"] for column in columns if column["sortable"]}
	if fieldname:
		if fieldname not in allowed or direction not in {"asc", "desc"}:
			frappe.throw(_("Unsupported record sort."))
		return f"{fieldname} {direction}"
	title_field = _auxiliary_title_field(meta)
	return f"{title_field} asc" if title_field else f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}"


def _auxiliary_list_type(field):
	return {
		"Check": "checkbox",
		"Currency": "currency",
		"Date": "date",
		"Float": "decimal",
		"Int": "integer",
		"Link": "link",
		"Select": "select",
	}.get(field.fieldtype, "data")


# endregion 1. LIST CONTRACT


# region 2. RECURSIVE DELETION PLANNER

def _auxiliary_deletion_plan(doctype, names):
	root_names = _auxiliary_delete_names(names)
	state = frappe._dict(nodes={}, edges=[], blockers=[], visiting=set(), visited=set())
	for name in root_names:
		_collect_auxiliary_delete_node(doctype, name, state, root=True)
	root_keys = {(doctype, name) for name in root_names}
	ordered = _auxiliary_delete_order(state.nodes, state.edges)
	common_blockers = _unique_auxiliary_blockers(state.blockers)
	unlink_edges = [edge for edge in state.edges if edge["from"] in root_keys]
	public = {
		"doctype": doctype,
		"roots": [_public_auxiliary_delete_node(state.nodes[(doctype, name)], state.edges) for name in root_names if (doctype, name) in state.nodes],
		"dependencies": [_public_auxiliary_delete_node(node, state.edges) for node in ordered if (node["doctype"], node["name"]) not in root_keys],
		"blockers": common_blockers,
		"total_records": len(ordered),
		"related_types": _public_auxiliary_related_types(state.nodes, state.edges, root_keys),
	}
	public["plan_token"] = _auxiliary_delete_plan_token(public)
	return frappe._dict(public=public, nodes=state.nodes, delete_order=ordered, delete_edges=state.edges, unlink_edges=unlink_edges)


def _auxiliary_delete_names(names):
	requested = json.loads(names) if isinstance(names, str) else names
	if not isinstance(requested, list):
		frappe.throw(_("Choose at least one record to delete."))
	result = list(dict.fromkeys(str(name).strip() for name in requested if str(name).strip()))
	if not result or len(result) > _AUXILIARY_DELETE_MAX_ROOTS:
		frappe.throw(_("Choose between 1 and {0} records at a time.").format(_AUXILIARY_DELETE_MAX_ROOTS))
	return result


def _collect_auxiliary_delete_node(doctype, name, state, root=False):
	key = (doctype, name)
	if key in state.visited:
		if root and key in state.nodes:
			state.nodes[key]["root"] = True
		return
	if key in state.visiting:
		state.blockers.append(_auxiliary_delete_blocker(doctype, name, _("A circular dependency requires manual review.")))
		return
	if len(state.nodes) >= _AUXILIARY_DELETE_MAX_RECORDS:
		state.blockers.append(_auxiliary_delete_blocker(doctype, name, _("The dependency set is too large for in-app deletion.")))
		return

	state.visiting.add(key)
	try:
		doc, blocker = _load_auxiliary_delete_document(doctype, name)
		node = {
			"doctype": doctype,
			"name": name,
			"title": name,
			"root": root,
			"managed": doctype in _AUXILIARY_FORM_DOCTYPES,
			"docstatus": 0,
			"can_write": False,
			"can_delete": False,
			"preserve_reason": blocker,
		}
		state.nodes[key] = node
		if blocker:
			if node["managed"]:
				state.blockers.append(_auxiliary_delete_blocker(doctype, name, blocker))
			return
		title_field = _auxiliary_title_field(frappe.get_meta(doctype))
		node["title"] = doc.get(title_field) if title_field else name
		node["docstatus"] = doc.docstatus
		node["can_write"] = doc.has_permission("write")
		node["can_delete"] = doc.has_permission("delete")
		node["preserve_reason"] = _auxiliary_delete_preserve_reason(doc)
		permission_blocker = _auxiliary_delete_permission_block_reason(doc)
		if permission_blocker:
			state.blockers.append(_auxiliary_delete_blocker(doctype, name, permission_blocker, node["title"]))
		for link in _auxiliary_delete_links(doc):
			child_key = (link["doctype"], link["name"])
			state.edges.append({"from": key, "to": child_key, **{field: link[field] for field in ("field", "field_label", "storage_doctype", "storage_names")}})
			_collect_auxiliary_delete_node(link["doctype"], link["name"], state)
	finally:
		state.visiting.discard(key)
		state.visited.add(key)


def _load_auxiliary_delete_document(doctype, name):
	if doctype not in _AUXILIARY_FORM_DOCTYPES:
		return None, _("This connected record belongs to operational history or an unmanaged record type.")
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} no longer exists.").format(doctype, name))
	try:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
		return doc, None
	except frappe.PermissionError:
		return None, _("You cannot inspect this connected record.")


def _auxiliary_delete_block_reason(doc):
	return _auxiliary_delete_preserve_reason(doc) or _auxiliary_delete_permission_block_reason(doc)


def _auxiliary_delete_preserve_reason(doc):
	if doc.doctype not in _AUXILIARY_FORM_DOCTYPES:
		return _("This record type is not managed through All setup.")
	if _is_archived_setup_record(doc.doctype, doc.name):
		return _("This record is retained as historical identity for immutable evidence.")
	if doc.docstatus != 0:
		return _("Submitted or cancelled records are retained as history.")
	return None


def _auxiliary_delete_permission_block_reason(doc):
	if not doc.has_permission("delete"):
		return _("Your role cannot delete this record.")
	return None


def _auxiliary_edge_unlink_blocker(edge, nodes):
	node = nodes.get(edge["to"])
	if not node or not node["managed"]:
		return _("Operational history is preserved with its original reference.")
	field = frappe.get_meta(edge["storage_doctype"]).get_field(edge["field"])
	if node["docstatus"] != 0:
		return _("Submitted or cancelled records keep their original reference.")
	if not node["can_write"]:
		return _("Your role cannot unlink this related record.")
	if field and field.reqd:
		return _("The required field {0} cannot be unlinked.").format(edge["field_label"])
	return None


def _public_auxiliary_related_types(nodes, edges, root_keys):
	groups = {}
	for key, node in nodes.items():
		if key in root_keys:
			continue
		group = groups.setdefault(node["doctype"], {
			"doctype": node["doctype"],
			"record_count": 0,
			"managed": bool(node["managed"]),
			"configurable": False,
			"history_count": 0,
			"link_count": 0,
		})
		group["record_count"] += 1
		group["configurable"] = bool(group["configurable"] or (node["managed"] and not node["preserve_reason"]))
		group["history_count"] += int(bool(node["preserve_reason"]))
		group["link_count"] += sum(1 for edge in edges if edge["to"] == key)
	return [groups[doctype] for doctype in sorted(groups)]


def _resolve_auxiliary_delete_execution(plan, default_outcome, outcomes_by_doctype=None):
	default_action = _normalize_auxiliary_delete_outcome(default_outcome)
	if default_action not in {"delete", "unlink"}:
		frappe.throw(_("Choose Delete or Unlink as the default related-record action."))
	requested = _as_dict(outcomes_by_doctype)
	known_types = {
		node["doctype"]
		for node in plan.nodes.values()
		if not node["root"] and node["managed"]
	}
	unknown_types = set(requested) - known_types
	if unknown_types:
		frappe.throw(_("The related record types changed. Review the deletion plan again."))
	decisions = {
		doctype: _normalize_auxiliary_delete_outcome(requested.get(doctype) or default_action)
		for doctype in known_types
	}
	if any(action not in {"delete", "unlink"} for action in decisions.values()):
		frappe.throw(_("Every related record type must use Delete or Unlink."))

	root_keys = {key for key, node in plan.nodes.items() if node["root"]}
	delete_candidates = set(root_keys)
	preserved_keys = set()
	archive_keys = set()
	for key, node in plan.nodes.items():
		if key in root_keys:
			if node["preserve_reason"]:
				archive_keys.add(key)
			continue
		if node["managed"] and decisions[node["doctype"]] == "delete":
			delete_candidates.add(key)
			if node["preserve_reason"]:
				archive_keys.add(key)
		else:
			preserved_keys.add(key)

	unlink_edges = []
	blockers = list(plan.public["blockers"])
	changed = True
	while changed:
		changed = False
		preserved = preserved_keys | archive_keys | (set(plan.nodes) - delete_candidates)
		for edge in plan.delete_edges:
			if edge["from"] not in delete_candidates or edge["from"] in archive_keys or edge["to"] not in preserved:
				continue
			blocker = _auxiliary_edge_unlink_blocker(edge, plan.nodes)
			if blocker and edge["from"] not in archive_keys:
				archive_keys.add(edge["from"])
				changed = True

	delete_keys = delete_candidates - archive_keys
	for edge in plan.delete_edges:
		target_action = decisions.get(edge["to"][0])
		needs_unlink = target_action == "unlink" or (edge["from"] in delete_keys and edge["to"] not in delete_keys)
		if not needs_unlink:
			continue
		blocker = _auxiliary_edge_unlink_blocker(edge, plan.nodes)
		if not blocker:
			unlink_edges.append(edge)

	delete_order = [node for node in plan.delete_order if (node["doctype"], node["name"]) in delete_keys]
	delete_edges = [edge for edge in plan.delete_edges if edge["to"] in delete_keys]
	archived = [plan.nodes[key] for key in sorted(archive_keys) if plan.nodes[key]["managed"]]
	preserved = [
		plan.nodes[key]
		for key in sorted(set(plan.nodes) - delete_keys - {key for key in archive_keys if plan.nodes[key]["managed"]})
	]
	return frappe._dict(
		allowed=not blockers,
		blockers=_unique_auxiliary_blockers(blockers),
		delete_order=delete_order,
		delete_edges=delete_edges,
		unlink_edges=_unique_auxiliary_delete_edges(unlink_edges),
		archived=archived,
		preserved=preserved,
		outcomes_by_doctype=decisions,
		default_outcome=default_action,
	)


def _public_auxiliary_delete_resolution(resolution):
	return {
		"allowed": resolution.allowed,
		"blockers": resolution.blockers,
		"default_outcome": resolution.default_outcome,
		"outcomes_by_doctype": resolution.outcomes_by_doctype,
		"delete_count": len(resolution.delete_order),
		"unlink_count": len(resolution.unlink_edges),
		"archive_count": len(resolution.archived),
		"preserve_count": len(resolution.preserved),
		"archived": [_public_auxiliary_execution_node(node) for node in resolution.archived],
		"preserved": [_public_auxiliary_execution_node(node) for node in resolution.preserved],
	}


def _public_auxiliary_execution_node(node):
	return {field: node.get(field) for field in ("doctype", "name", "title", "preserve_reason")}


def _normalize_auxiliary_delete_outcome(outcome):
	return "delete" if outcome == "recursive" else str(outcome or "").lower()


def _unique_auxiliary_delete_edges(edges):
	unique = {}
	for edge in edges:
		key = (edge["from"], edge["to"], edge["storage_doctype"], tuple(edge["storage_names"]), edge["field"])
		unique[key] = edge
	return list(unique.values())


def _auxiliary_delete_links(doc):
	unique = {(link["doctype"], link["name"], link["field"]): link for link in [*_static_auxiliary_delete_links(doc), *_dynamic_auxiliary_delete_links(doc)]}
	return [unique[key] for key in sorted(unique)]


def _static_auxiliary_delete_links(doc):
	links = []
	ignored = set(frappe.get_hooks("ignore_links_on_delete"))
	for link_field in get_link_fields(doc.doctype):
		storage_doctype = link_field["parent"]
		fieldname = link_field["fieldname"]
		if storage_doctype in ignored:
			continue
		meta = frappe.get_meta(storage_doctype)
		field = meta.get_field(fieldname)
		if link_field["issingle"]:
			if frappe.db.get_single_value(storage_doctype, fieldname) == doc.name:
				links.append(_auxiliary_delete_link(storage_doctype, storage_doctype, fieldname, field, storage_doctype, [storage_doctype]))
			continue
		fields = ["name"] + (["parent", "parenttype"] if meta.istable else [])
		for row in frappe.db.get_values(storage_doctype, {fieldname: doc.name}, fields, as_dict=True, order_by=None):
			reference_doctype = row.parenttype if meta.istable else storage_doctype
			reference_name = row.parent if meta.istable else row.name
			if reference_doctype in ignored or (reference_doctype == doc.doctype and reference_name == doc.name):
				continue
			links.append(_auxiliary_delete_link(reference_doctype, reference_name, fieldname, field, storage_doctype, [row.name]))
	return links


def _dynamic_auxiliary_delete_links(doc):
	links = []
	ignored = set(frappe.get_hooks("ignore_links_on_delete"))
	for field in get_dynamic_link_map().get(doc.doctype, []):
		if field.parent in ignored:
			continue
		meta = frappe.get_meta(field.parent)
		filters = {field.options: doc.doctype, field.fieldname: doc.name}
		fields = ["name"] + (["parent", "parenttype"] if meta.istable else [])
		if meta.issingle:
			values = frappe.db.get_singles_dict(field.parent)
			rows = [frappe._dict(name=field.parent, parent=None, parenttype=None)] if values.get(field.options) == doc.doctype and values.get(field.fieldname) == doc.name else []
		else:
			rows = frappe.get_all(field.parent, filters=filters, fields=fields)
		for row in rows:
			reference_doctype = row.parenttype if meta.istable else field.parent
			reference_name = row.parent if meta.istable else row.name
			if reference_doctype not in ignored:
				links.append(_auxiliary_delete_link(reference_doctype, reference_name, field.fieldname, field, field.parent, [row.name]))
	return links


def _auxiliary_delete_link(doctype, name, fieldname, field, storage_doctype, storage_names):
	return {"doctype": doctype, "name": name, "field": fieldname, "field_label": field.label if field and field.label else fieldname.replace("_", " ").title(), "storage_doctype": storage_doctype, "storage_names": storage_names}


def _unlink_auxiliary_delete_plan(edges):
	grouped = {}
	for edge in edges:
		grouped.setdefault(edge["to"], []).append(edge)
	for (doctype, name), linked_edges in grouped.items():
		if doctype not in _AUXILIARY_FORM_DOCTYPES:
			frappe.throw(_("Operational history and unmanaged records cannot be unlinked."))
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		for edge in linked_edges:
			storage_meta = frappe.get_meta(edge["storage_doctype"])
			if storage_meta.istable:
				for row in doc.get_all_children():
					if row.name in edge["storage_names"]:
						row.set(edge["field"], None)
			else:
				doc.set(edge["field"], None)
		doc.save()


def _clear_auxiliary_delete_plan_links(edges):
	seen = set()
	for edge in edges:
		if edge["to"][0] not in _AUXILIARY_FORM_DOCTYPES:
			continue
		for storage_name in edge["storage_names"]:
			key = (edge["storage_doctype"], storage_name, edge["field"])
			if key in seen:
				continue
			seen.add(key)
			meta = frappe.get_meta(edge["storage_doctype"])
			if meta.issingle:
				frappe.db.set_single_value(edge["storage_doctype"], edge["field"], None)
			else:
				frappe.db.set_value(edge["storage_doctype"], storage_name, edge["field"], None, update_modified=False)


def _public_auxiliary_unlink_edge(edge):
	return {
		"doctype": edge["to"][0],
		"name": edge["to"][1],
		"field": edge["field"],
		"field_label": edge["field_label"],
	}


def _auxiliary_delete_order(nodes, edges):
	children = {}
	for edge in edges:
		if edge["to"] in nodes:
			children.setdefault(edge["from"], []).append(edge["to"])
	ordered, visited = [], set()
	def visit(key):
		if key in visited or key not in nodes:
			return
		visited.add(key)
		for child in children.get(key, []):
			visit(child)
		ordered.append(nodes[key])
	for key in nodes:
		visit(key)
	return ordered


def _public_auxiliary_delete_node(node, edges):
	key = (node["doctype"], node["name"])
	linked_by = [{"doctype": edge["to"][0], "name": edge["to"][1], "field": edge["field"], "field_label": edge["field_label"]} for edge in edges if edge["to"] == key]
	return {field: node[field] for field in ("doctype", "name", "title", "root")} | {"linked_by": linked_by}


def _auxiliary_delete_blocker(doctype, name, reason, title=None):
	return {"doctype": doctype, "name": name, "title": title or name, "reason": reason}


def _unique_auxiliary_blockers(blockers):
	return list({(row["doctype"], row["name"], str(row["reason"])): row for row in blockers}.values())


def _auxiliary_delete_plan_token(plan, exclude_token=False):
	token_input = {key: value for key, value in plan.items() if key != "plan_token"} if exclude_token else plan
	stable = json.dumps(token_input, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(stable.encode("utf-8")).hexdigest()


# endregion 2. RECURSIVE DELETION PLANNER


# endregion AUXILIARY RECORD FORMS


# =============================================================================
# region ITEM IDENTITY
# =============================================================================


@frappe.whitelist(methods=["GET"])
def resolve_scan_code(code):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	value = normalize_scan_code(code)
	owner = find_scan_owner(value)
	item_code = owner.item_code if owner else None
	if not item_code:
		return {"matched": False, "scan_code": value, "reason": _("No item is mapped to this code yet.")}
	item = frappe.db.get_value(
		"BulkBite Item", item_code, ["item_code", "item_name", "stock_uom", "track_stock", "enabled"], as_dict=True
	)
	if not item.enabled:
		frappe.throw(_("Item {0} is disabled.").format(item_code))
	return {**item, "matched": True, "is_stock_item": item.track_stock, "scan_code": value, "uom": item.stock_uom}


@frappe.whitelist(methods=["POST"])
def assign_scan_code(item_code, code):
	"""Assign one supplier or internal scan code to one item, never more than one."""
	_require_roles("BulkBite Manager")
	item = frappe.get_doc("BulkBite Item", item_code)
	item.check_permission("write")
	value = normalize_scan_code(code)
	owner = find_scan_owner(value, exclude_item=item.item_code)
	if owner:
		frappe.throw(_("Scan code {0} is already assigned to item {1}.").format(value, owner.item_code))
	codes = item_scan_codes(item)
	codes.add(value)
	item.scan_codes = "\n".join(sorted(codes))
	item.save()
	return resolve_scan_code(value)


# endregion ITEM IDENTITY


# =============================================================================
# region PRODUCTION RUNS
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_recipe_expectation(recipe, planned_output_qty, source_location):
	_require_app_user()
	return load_expected_usage(recipe, planned_output_qty, source_location)


@frappe.whitelist(methods=["GET"])
def get_production_instructions(recipe, output_qty, team_size=1):
	"""Return deterministic scaled kitchen instructions for review and execution."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	return build_run_instruction_plan(recipe, output_qty, team_size)


@frappe.whitelist(methods=["GET"])
def get_kitchen_plan_snapshot(run_name):
	"""Load one saved production run and its deterministic cooking plan."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", run_name)
	run.check_permission("read")
	team_size = len([row for row in run.employees or [] if row.completion_status not in {"Absent", "Cancelled"}])
	if not team_size and run.team_template:
		team_size = frappe.db.count(
			"BulkBite Team Template Member",
			{"parent": run.team_template, "parenttype": "BulkBite Team Template", "enabled": 1},
		)
	team_size = max(int(team_size or 1), 1)
	return {
		"run": _serialize_run(run),
		"instructions": build_run_instruction_plan(run.recipe, run.planned_output_qty, team_size),
		"employees": frappe.get_all(
			"BulkBite Employee",
			filters={"status": "Active", "available_for_production": 1},
			fields=["name as value", "full_name as label", "employee_type", "available_hours_per_run"],
			order_by="full_name",
		),
		"team_templates": _get_team_templates(),
	}


@frappe.whitelist(methods=["POST"])
def create_production_run(payload=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	run = frappe.get_doc({"doctype": "BulkBite Production Run", **data})
	run.insert()
	return _serialize_run(run)


@frappe.whitelist(methods=["POST"])
def create_ad_hoc_production_run(recipe, planned_output_qty, production_date, source_location="Ingredients", target_location="Finished Meals"):
	"""Create an explicit off-plan production draft without advancing the meal direction."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	planned_output = round_operational_quantity(planned_output_qty)
	if planned_output <= 0:
		frappe.throw(_("Target output must be greater than zero."))
	return create_production_run(
		{
			"production_date": getdate(production_date),
			"business_name": "BulkBite",
			"direction_action": "Off Plan",
			"recipe": recipe,
			"planned_output_qty": planned_output,
			"actual_output_qty": planned_output,
			"source_location": source_location,
			"target_location": target_location,
			"notes": _("Created as an ad hoc production draft outside the current meal direction."),
		}
	)


@frappe.whitelist(methods=["GET"])
def get_finished_food_position(item_code=None, location="Finished Meals"):
	"""Return physical stock, reservations, and recent explicit finished-food allocations."""
	_require_app_user()
	from bulkbite.bulkbite.doctype.bulkbite_finished_food_allocation.bulkbite_finished_food_allocation import get_unallocated_finished_food

	items = [item_code] if item_code else frappe.get_all("BulkBite Item", filters={"item_type": "Finished Meal", "enabled": 1}, pluck="name")
	positions = []
	for code in items:
		physical = round_operational_quantity(get_available_stock(code, location))
		available = round_operational_quantity(get_unallocated_finished_food(code, location))
		positions.append(
			{
				"item_code": code,
				"item_name": frappe.get_cached_value("BulkBite Item", code, "item_name"),
				"uom": frappe.get_cached_value("BulkBite Item", code, "stock_uom"),
				"physical_qty": physical,
				"reserved_qty": round_operational_quantity(physical - available),
				"unallocated_qty": available,
			}
		)
	recent_allocations = frappe.get_all(
		"BulkBite Finished Food Allocation",
		filters={"finished_item": item_code} if item_code else None,
		fields=["name", "posting_date", "finished_item", "source_production_run", "allocation_type", "source_reservation", "demand_period", "quantity", "uom", "status", "docstatus"],
		order_by="posting_date desc, creation desc",
		limit=40,
	)
	from bulkbite.bulkbite.doctype.bulkbite_finished_food_allocation.bulkbite_finished_food_allocation import get_reservation_remaining
	for allocation in recent_allocations:
		allocation["remaining_qty"] = round_operational_quantity(get_reservation_remaining(allocation.name)) if allocation.allocation_type == "Future Customers" else 0
	return {
		"location": location,
		"items": positions,
		"recent_allocations": recent_allocations,
	}


@frappe.whitelist(methods=["GET"])
def get_production_history_snapshot(plan_name=None):
	"""Compare current customer theory with posted production and immutable allocations."""
	_require_app_user()
	plan_name = plan_name or frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")
	plan = frappe.get_doc("BulkBite Production Plan", plan_name) if plan_name else None
	plan_rows = build_plan_snapshot(plan, "Ingredients")[0] if plan else []
	run_filters = {"docstatus": 1}
	if plan_name:
		run_filters["production_plan"] = plan_name
	run_names = frappe.get_all(
		"BulkBite Production Run",
		filters=run_filters,
		fields=["name", "production_date", "production_plan_row", "plan_week_number", "cycle_number", "direction_action", "recipe", "finished_item", "planned_output_qty", "actual_output_qty", "finished_container_count", "average_container_qty", "actual_elapsed_hours", "actual_team_size", "actual_labour_hours", "actual_labour_minutes_per_kg", "planned_takt_minutes_per_kg", "takt_status", "material_cost_variance", "notes", "docstatus"],
		order_by="production_date desc, creation desc",
		limit=200,
	)
	service_periods = load_service_period_records(plan.name) if plan else []
	current_period = resolve_current_service_period(
		plan_rows, run_names, plan.period_start, intentional_skips=service_periods
	) if plan else None
	current_cycle = int((current_period or {}).get("cycle_number") or 1)
	allocation_filters = {"name": "__none__"}
	if run_names:
		allocation_filters = {"docstatus": 1, "source_production_run": ["in", [row.name for row in run_names]]}
	allocations = frappe.get_all(
		"BulkBite Finished Food Allocation",
		filters=allocation_filters,
		fields=["name", "posting_date", "source_production_run", "allocation_type", "demand_period", "quantity", "uom", "status"],
		order_by="posting_date asc, creation asc",
	)
	allocations_by_run = {}
	for row in allocations:
		allocations_by_run.setdefault(row.source_production_run, []).append(row)
	row_theory = {row["name"]: row for row in plan_rows}
	runs = []
	for run in run_names:
		run_allocations = allocations_by_run.get(run.name, [])
		allocated = sum(flt(row.quantity) for row in run_allocations if row.allocation_type != "Future Customers")
		reserved = sum(flt(row.quantity) for row in run_allocations if row.allocation_type == "Future Customers")
		theory = row_theory.get(run.production_plan_row) or {}
		customer_required = flt(theory.get("customer_required_output_qty") or run.planned_output_qty)
		runs.append({
			**run,
			"theory_customer_qty": round_operational_quantity(customer_required),
			"theory_extra_qty": round_operational_quantity(theory.get("extra_output_qty")),
			"output_variance_qty": round_operational_quantity(flt(run.actual_output_qty) - flt(run.planned_output_qty)),
			"allocations": run_allocations,
			"allocated_output_qty": round_operational_quantity(allocated),
			"reserved_output_qty": round_operational_quantity(reserved),
			"unallocated_output_qty": round_operational_quantity(max(flt(run.actual_output_qty) - allocated - reserved, 0)),
			"customer_coverage_status": "Covered" if flt(run.actual_output_qty) >= customer_required else "Short",
		})
	current_row = (current_period or {}).get("row") or {}
	current_meal = int(current_row.get("cycle_week") or current_row.get("week_number") or 0)
	customer_required = flt((current_period or {}).get("required_output_qty"))
	planned = flt((current_period or {}).get("planned_output_qty"))
	current_evidence = set((current_period or {}).get("evidence_runs") or [])
	current_runs = [row for row in run_names if row.name in current_evidence]
	current_run_names = {row.name for row in current_runs}
	current_allocations = [row for row in allocations if row.source_production_run in current_run_names]
	actual = flt((current_period or {}).get("actual_output_qty"))
	allocated_by_type = {
		allocation_type: round_operational_quantity(sum(flt(row.quantity) for row in current_allocations if row.allocation_type == allocation_type))
		for allocation_type in ["Current Customers", "Future Customers", "Future Customer Fulfilment", "Internal Consumption", "Waste or Spoilage"]
	}
	remaining = round_operational_quantity(max(customer_required - actual, 0))
	difference = round_operational_quantity(actual - customer_required)
	current_service_date = getdate((current_period or {}).get("planned_date") or nowdate())
	status = (
		"Ahead" if difference > 0.0005
		else "On target" if abs(difference) <= 0.0005
		else "Behind" if current_service_date <= getdate(nowdate())
		else "On pace"
	)
	skipped_weeks = _skipped_production_weeks(
		plan_rows, run_names, plan.period_start, intentional_skips=service_periods
	) if plan else []
	return {
		"plan": plan_name,
		"summary": {
			"cycle_number": current_cycle,
			"customer_required_qty": round_operational_quantity(customer_required),
			"planned_qty": round_operational_quantity(planned),
			"actual_qty": round_operational_quantity(actual),
			"remaining_customer_qty": remaining,
			"output_difference_qty": difference,
			"status": status,
			"needs_another_run": remaining > 0 and current_service_date <= getdate(nowdate()),
			"planned_date": (current_period or {}).get("planned_date"),
			"meal_number": current_meal,
			"allocations": allocated_by_type,
		},
		"runs": runs,
		"skipped_weeks": skipped_weeks,
		"service_periods": service_periods,
		"containers": get_container_position_snapshot(),
	}


@frappe.whitelist(methods=["GET"])
def get_operational_calendar(from_date=None, to_date=None):
	_require_app_user()
	return get_operational_calendar_snapshot(from_date, to_date)


@frappe.whitelist(methods=["GET"])
def get_container_position():
	_require_app_user()
	return get_container_position_snapshot()


@frappe.whitelist(methods=["GET"])
def get_container_suggestion(output_qty):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	return get_default_container_suggestion(output_qty)


@frappe.whitelist(methods=["POST"])
def update_operational_action(name, action, new_date=None, reason=None):
	_require_roles("BulkBite Manager")
	doc = frappe.get_doc("BulkBite Operational Action", name)
	if action == "complete":
		doc.status = "Completed"
		doc.completed_on = getdate(nowdate())
	elif action == "reschedule":
		if not new_date:
			frappe.throw(_("Choose a new date."))
		doc.status = "Rescheduled"
		doc.rescheduled_to = getdate(new_date)
		doc.notes = reason
	elif action == "cancel":
		if not reason:
			frappe.throw(_("Enter why the action is being cancelled."))
		doc.status = "Cancelled"
		doc.cancellation_reason = reason
	else:
		frappe.throw(_("Choose complete, reschedule, or cancel."))
	doc.save()
	if action == "reschedule":
		frappe.get_doc({
			"doctype": "BulkBite Operational Action",
			"title": doc.title,
			"action_type": doc.action_type,
			"schedule": doc.schedule,
			"due_date": doc.rescheduled_to,
			"status": "Due",
			"target_section": doc.target_section,
			"consequence_note": doc.consequence_note,
			"notes": _("Rescheduled from {0}.").format(doc.name),
		}).insert()
	return get_operational_calendar_snapshot()


@frappe.whitelist(methods=["POST"])
def create_custom_operational_action(title, due_date, consequence_note=None, target_section="operations", notes=None):
	"""Create one manager-owned calendar action without a recurring schedule."""
	_require_roles("BulkBite Manager")
	if not str(title or "").strip():
		frappe.throw(_("Enter an action title."))
	if not due_date:
		frappe.throw(_("Choose when the action is due."))
	doc = frappe.get_doc({
		"doctype": "BulkBite Operational Action",
		"title": str(title).strip(),
		"action_type": "Custom",
		"due_date": getdate(due_date),
		"status": "Due",
		"target_section": target_section or "operations",
		"consequence_note": consequence_note,
		"notes": notes,
	}).insert()
	return {"action": doc.name, "calendar": get_operational_calendar_snapshot()}


@frappe.whitelist(methods=["POST"])
def skip_production_service_period(plan_name, planned_date, reason):
	"""Record one manager-approved holiday or closure without creating later production debt."""
	_require_roles("BulkBite Manager")
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	rows = build_plan_snapshot(plan, "Ingredients")[0]
	period = mark_service_period_skipped(plan, rows, planned_date, reason)
	return {
		"name": period.name,
		"planned_date": period.planned_date,
		"status": period.status,
		"cycle_number": period.cycle_number,
		"meal_number": period.meal_number,
	}


@frappe.whitelist(methods=["POST"])
def skip_production_service_period_range(plan_name, from_date, to_date, reason):
	"""Record all scheduled service dates in one manager-approved vacation range."""
	_require_roles("BulkBite Manager")
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	rows = build_plan_snapshot(plan, "Ingredients")[0]
	result = mark_service_period_range_skipped(plan, rows, from_date, to_date, reason)
	return {
		"scheduled_dates": result["scheduled_dates"],
		"created": [_service_period_result(row) for row in result["created"]],
		"already_skipped": [_service_period_result(row) for row in result["already_skipped"]],
		"protected": [_service_period_result(row) for row in result["protected"]],
	}


def _service_period_result(period):
	value = period.get if isinstance(period, dict) else lambda key: getattr(period, key, None)
	return {
		"name": value("name"),
		"planned_date": value("planned_date"),
		"status": value("status"),
		"cycle_number": value("cycle_number"),
		"meal_number": value("meal_number"),
		"resolution_reason": value("resolution_reason"),
	}


@frappe.whitelist(methods=["POST"])
def record_container_movement(payload=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	doc = frappe.get_doc({"doctype": "BulkBite Container Movement", **data}).insert()
	doc.submit()
	return get_container_position_snapshot()


@frappe.whitelist(methods=["POST"])
def allocate_finished_food(payload=None):
	"""Submit one explicit customer, future, internal, or waste allocation exactly once."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	doc = frappe.get_doc(
		{
			"doctype": "BulkBite Finished Food Allocation",
			"posting_date": getdate(data.get("posting_date") or nowdate()),
			"finished_item": data.get("finished_item"),
			"source_location": data.get("source_location") or "Finished Meals",
			"source_production_run": data.get("source_production_run"),
			"allocation_type": data.get("allocation_type"),
			"source_reservation": data.get("source_reservation"),
			"demand_period": data.get("demand_period"),
			"quantity": round_operational_quantity(data.get("quantity")),
			"notes": data.get("notes"),
		}
	)
	doc.insert()
	doc.submit()
	return get_finished_food_position(doc.finished_item, doc.source_location)


@frappe.whitelist(methods=["POST"])
def update_production_actuals(name, actual_output_qty, ingredients, notes=None, finished_container_count=0):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus != 0:
		frappe.throw(_("Only a draft production run can be measured."))
	supplied = _as_list(ingredients)
	actual_by_item = {row["item_code"]: row for row in supplied if row.get("item_code")}
	if len(actual_by_item) != len(supplied) or set(actual_by_item) != {row.item_code for row in run.ingredients}:
		frappe.throw(_("Provide one actual measurement for every recipe ingredient."))
	if flt(actual_output_qty) <= 0:
		frappe.throw(_("Meals made must be greater than zero."))
	run.actual_output_qty = round_operational_quantity(actual_output_qty)
	run.finished_container_count = max(int(finished_container_count or 0), 0)
	run.notes = notes
	for row in run.ingredients:
		actual = actual_by_item.get(row.item_code)
		if actual:
			method = actual.get("measurement_method") or "Used"
			if method not in {"Used", "Remaining"}:
				frappe.throw(_("Choose used or remaining for {0}.").format(row.item_code))
			row.measurement_method = method
			if method == "Remaining":
				available = get_available_stock(row.item_code, row.source_location or run.source_location)
				remaining = round_operational_quantity(actual.get("remaining_qty"))
				row.available_before_measurement = available
				row.remaining_qty = remaining
				row.actual_qty = round_operational_quantity(derive_usage_from_remaining(available, remaining))
			else:
				row.remaining_qty = None
				row.available_before_measurement = get_available_stock(row.item_code, row.source_location or run.source_location)
				row.actual_qty = round_operational_quantity(actual.get("actual_qty"))
			row.notes = actual.get("notes")
	run.save()
	return _serialize_run(run)


@frappe.whitelist(methods=["POST"])
def submit_production_run(name):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	frappe.db.sql("select name from `tabBulkBite Production Run` where name = %s for update", (name,))
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus == 1:
		return _serialize_run(run)
	run.submit()
	return _serialize_run(run.reload())


@frappe.whitelist(methods=["POST"])
def calculate_variance_preview(expected_qty, actual_qty, valuation_rate=0, planned_output_qty=None, actual_output_qty=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	result = {"usage": calculate_usage_variance(expected_qty, actual_qty, valuation_rate)}
	if planned_output_qty is not None:
		result["output"] = calculate_output_variance(planned_output_qty, actual_output_qty)
	return result


# endregion PRODUCTION RUNS


# =============================================================================
# region PRODUCTION PLANNING
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_production_plan_snapshot(plan_name=None, location=None):
	"""Return planned recipes, expected ingredients, current stock, and shortages."""
	_require_app_user()
	plan_name = plan_name or frappe.db.get_value(
		"BulkBite Production Plan",
		{"status": ("in", ["Relative Draft", "Dated Draft", "Active"])},
		"name",
		order_by="modified desc",
	)
	if not plan_name:
		return None
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	location = location or "Ingredients"
	rows, requirements = build_plan_snapshot(plan, location)
	demand = calculate_customer_demand(plan.customer_mix)
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": plan.name},
		fields=["name", "production_plan_row", "plan_week_number", "cycle_number", "direction_action", "recipe", "finished_item", "production_date", "docstatus", "planned_output_qty", "actual_output_qty", "creation", "modified"],
		order_by="production_date, creation",
	)
	service_periods = load_service_period_records(plan.name)
	next_production = _next_production_station(rows, runs, plan.period_start, service_periods=service_periods)
	start_cycle_week = int((next_production.get("row") or {}).get("cycle_week") or (next_production.get("row") or {}).get("week_number") or 1)
	buying_rows, buying_requirements = build_plan_snapshot(plan, location, cover_with_finished_stock=True, start_cycle_week=start_cycle_week)
	buying = build_buying_plan(plan, buying_requirements, next_production=next_production)
	buying["planned_sessions"] = buying_rows
	result = {
		"name": plan.name,
		"modified": plan.modified,
		"plan_title": plan.plan_title,
		"status": plan.status,
		"period_start": plan.period_start,
		"period_end": plan.period_end,
		"date_note": plan.date_note,
		"location": location,
		"customer_demand": demand,
		"customer_mix": [{
			"plan_type": row.plan_type,
			"customer_count": row.customer_count,
			"serving_size_g": round_operational_quantity(row.serving_size_g),
			"meals_per_day": frappe.get_cached_value("BulkBite Customer Plan Type", row.plan_type, "meals_per_day"),
			"days_per_week": frappe.get_cached_value("BulkBite Customer Plan Type", row.plan_type, "days_per_week"),
			"weekly_servings": row.weekly_servings,
			"weekly_output_qty": round_operational_quantity(row.weekly_output_qty),
		} for row in plan.customer_mix],
		"purchase_routes": [{"item_category": row.item_category, "supplier": row.supplier, "use_discounted_price": row.use_discounted_price} for row in plan.purchase_routes],
		"rows": rows,
		"total_requirements": requirements,
		"buying": buying,
		"financial_summary": build_dashboard_financial_summary(demand, rows, plan.name),
		"workforce": get_employee_capacity_snapshot(demand),
		"runs": runs,
		"service_periods": service_periods,
	}
	result["capacity_plan"] = _build_capacity_plan(plan, result["customer_mix"], result["workforce"])
	result["next_production"] = next_production
	result["operations"] = build_operational_action_snapshot(result)
	return result


@frappe.whitelist(methods=["GET"])
def get_buying_recommendation(plan_name=None, location="Ingredients", horizon_weeks=4):
	"""Build a current advisory basket for the selected future horizon."""
	_require_app_user()
	plan_name = plan_name or frappe.db.get_value("BulkBite Production Plan", {"status": "Active"}, "name", order_by="modified desc")
	if not plan_name:
		return None
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	weeks = max(min(int(horizon_weeks or 4), 12), 1)
	direction_rows, _ = build_plan_snapshot(plan, location)
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": plan.name},
		fields=["name", "production_plan_row", "plan_week_number", "cycle_number", "direction_action", "finished_item", "production_date", "docstatus", "planned_output_qty", "actual_output_qty", "creation"],
		order_by="production_date, creation",
	)
	service_periods = load_service_period_records(plan.name)
	next_production = _next_production_station(
		direction_rows, runs, plan.period_start, service_periods=service_periods
	)
	start_cycle_week = int((next_production.get("row") or {}).get("cycle_week") or (next_production.get("row") or {}).get("week_number") or 1)
	rows, requirements = build_plan_snapshot(plan, location, weeks, cover_with_finished_stock=True, start_cycle_week=start_cycle_week)
	buying = build_buying_plan(plan, requirements, horizon_weeks=weeks, next_production=next_production)
	buying["planned_sessions"] = rows
	buying["advisory_only"] = True
	return buying


def _build_capacity_plan(plan, current_mix, workforce):
	"""Resolve saved weekly windows and return the rolling workforce forecast."""
	templates = {row["name"]: row for row in _get_team_templates()}
	windows = []
	for week in range(1, 5):
		saved = next((row for row in plan.capacity_windows if int(row.week_number or 0) == week), None)
		template_name = (saved.team_template if saved else None) or plan.default_team_template
		template = templates.get(template_name) or {}
		windows.append({
			"week_number": week,
			"scheduled_elapsed_hours": flt(saved.scheduled_elapsed_hours if saved else template.get("default_elapsed_hours")) or 4,
			"runs_per_week": int(saved.runs_per_week if saved else 1) or 1,
			"team_template": template_name,
			"team_size": int(template.get("team_size") or 0),
		})
	target_by_plan = {row.plan_type: row for row in plan.forecast_customer_mix or []}
	target_mix = [
		{
			"plan_type": row["plan_type"],
			"target_customers": int((target_by_plan.get(row["plan_type"]).target_customers if target_by_plan.get(row["plan_type"]) else row["customer_count"]) or 0),
			"target_week": int((target_by_plan.get(row["plan_type"]).target_week if target_by_plan.get(row["plan_type"]) else plan.forecast_weeks) or 4),
		}
		for row in current_mix
	]
	capacity_runs = [
		{
			"week_number": int(row.week_number or 1),
			"run_number": int(row.run_number or 1),
			"day_of_week": row.day_of_week,
			"planned_output_qty": round_operational_quantity(row.planned_output_qty),
			"output_mode": row.output_mode or "Auto",
			"scheduled_elapsed_hours": flt(row.scheduled_elapsed_hours),
			"team_template": row.team_template,
			"planned_people": int(row.planned_people or 0),
		}
		for row in plan.capacity_runs or []
	]
	return {
		"forecast_weeks": int(plan.forecast_weeks or 4),
		"default_team_template": plan.default_team_template,
		"windows": windows,
		"runs": capacity_runs,
		"target_customer_mix": target_mix,
		"forecast": calculate_capacity_forecast(
			current_mix,
			target_mix,
			plan.forecast_weeks or 4,
			windows,
			workforce.get("planning_labour_minutes_per_kg"),
			capacity_runs,
			[
				{"week_number": row.week_number, "required_output_qty": flt(row.planned_output_qty)}
				for row in plan.plan_rows or []
			],
		),
	}


@frappe.whitelist(methods=["POST"])
def calculate_capacity_scenario(payload=None):
	"""Calculate one unsaved production-capacity scenario without changing the active direction."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	result = {
		"forecast": calculate_capacity_forecast(
			_as_list(data.get("current_mix")),
			_as_list(data.get("target_mix")),
			data.get("forecast_weeks") or 4,
			_as_list(data.get("capacity_windows")),
			flt(data.get("labour_minutes_per_kg")),
			_as_list(data.get("capacity_runs")),
			_as_list(data.get("required_output_by_week")),
		)
	}
	weekly = data.get("weekly_capacity")
	if weekly:
		weekly = _as_dict(weekly)
		result["weekly_capacity"] = calculate_weekly_capacity(
			weekly.get("required_customer_qty"),
			weekly.get("extra_output_qty"),
			weekly.get("labour_minutes_per_kg"),
			_as_list(weekly.get("sessions")),
			weekly.get("storage_capacity_qty"),
		)
	return result


@frappe.whitelist(methods=["POST"])
def save_monthly_production_plan(payload=None):
	"""Create or update the one-month customer and recipe plan used by buying and production."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	plan = frappe.get_doc("BulkBite Production Plan", data.name) if data.get("name") else frappe.new_doc("BulkBite Production Plan")
	if not plan.is_new() and plan.status == "Cancelled":
		frappe.throw(_("A cancelled meal direction cannot be edited. Create a new direction instead."))
	plan.plan_title = data.get("plan_title") or _("Current meal direction")
	plan.status = "Active"
	plan.business_name = "BulkBite"
	plan.period_start = getdate(data.get("period_start") or plan.period_start or nowdate())
	plan.period_end = getdate(data.get("period_end") or plan.period_end or add_days(plan.period_start, 27))
	if "notes" in data:
		plan.notes = data.get("notes")
	plan.forecast_weeks = max(int(data.get("forecast_weeks") or 4), 1)
	plan.default_team_template = data.get("default_team_template")
	plan.set(
		"customer_mix",
		[
			{"plan_type": row.get("plan_type"), "customer_count": max(int(row.get("customer_count") or 0), 0)}
			for row in _as_list(data.get("customer_mix"))
			if row.get("plan_type")
		],
	)
	plan.set(
		"purchase_routes",
		[
			{
				"item_category": row.get("item_category"),
				"supplier": row.get("supplier"),
				"use_discounted_price": bool(row.get("use_discounted_price")),
			}
			for row in _as_list(data.get("purchase_routes"))
			if row.get("item_category") and row.get("supplier")
		],
	)
	enabled_categories = set(frappe.get_all("BulkBite Item Category", filters={"enabled": 1}, pluck="name"))
	routed_categories = {row.item_category for row in plan.purchase_routes if row.item_category and row.supplier}
	missing_categories = sorted(enabled_categories - routed_categories)
	if missing_categories:
		frappe.throw(
			_("Choose a supplier for every enabled food category: {0}.").format(", ".join(missing_categories))
		)
	rows = [row for row in _as_list(data.get("plan_rows")) if row.get("recipe")]
	if len(rows) != 4:
		frappe.throw(_("Choose one recipe for each of the four weeks."))
	plan.set(
		"plan_rows",
		[
			{
				"week_number": index,
				"recipe": row.get("recipe"),
				"customer_required_output_qty": flt(row.get("customer_required_output_qty") or row.get("planned_output_qty")),
				"extra_output_qty": max(flt(row.get("extra_output_qty")), 0),
				"extra_allocation_type": "Internal Consumption",
				"extra_allocation_reference": "",
				"planned_output_qty": flt(row.get("customer_required_output_qty") or row.get("planned_output_qty")) + max(flt(row.get("extra_output_qty")), 0),
				"uom": "Kg",
				"finished_item": row.get("finished_item") or frappe.get_cached_value("BulkBite Recipe", row.get("recipe"), "finished_item"),
			}
			for index, row in enumerate(rows, start=1)
		],
	)
	plan.set(
		"capacity_windows",
		[
			{"week_number": index, "scheduled_elapsed_hours": flt(row.get("scheduled_elapsed_hours")) or 4, "runs_per_week": max(int(row.get("runs_per_week") or 1), 1), "team_template": row.get("team_template") or plan.default_team_template}
			for index, row in enumerate(_as_list(data.get("capacity_windows"))[:4], start=1)
		],
	)
	plan.set(
		"forecast_customer_mix",
		[
			{"plan_type": row.get("plan_type"), "target_customers": max(int(row.get("target_customers") or 0), 0), "target_week": max(int(row.get("target_week") or plan.forecast_weeks), 1)}
			for row in _as_list(data.get("forecast_customer_mix")) if row.get("plan_type")
		],
	)
	plan.set(
		"capacity_runs",
		[
			{
				"week_number": max(min(int(row.get("week_number") or 1), 4), 1),
				"run_number": max(int(row.get("run_number") or 1), 1),
				"day_of_week": row.get("day_of_week") or "Monday",
				"planned_output_qty": max(flt(row.get("planned_output_qty")), 0),
				"output_mode": row.get("output_mode") if row.get("output_mode") in {"Auto", "Fixed"} else "Auto",
				"scheduled_elapsed_hours": max(flt(row.get("scheduled_elapsed_hours")), 0),
				"team_template": row.get("team_template") or plan.default_team_template,
				"planned_people": max(int(row.get("planned_people") or 0), 0),
			}
			for row in _as_list(data.get("capacity_runs"))
			if flt(row.get("scheduled_elapsed_hours")) > 0
		],
	)
	plan.save()
	frappe.db.set_value(
		"BulkBite Production Plan",
		{"name": ("!=", plan.name), "status": "Active"},
		"status",
		"Completed",
		update_modified=False,
	)
	freeze_buying_theory(plan, data.get("location") or "Ingredients")
	return get_production_plan_snapshot(plan.name, data.get("location") or "Ingredients")


@frappe.whitelist(methods=["POST"])
def create_run_from_plan(plan_name, plan_row_name, production_date, source_location, target_location, recipe=None, planned_output_qty=None, direction_action=None):
	"""Turn one planned recipe row into a measurable production draft."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	plan = frappe.get_doc("BulkBite Production Plan", plan_name)
	plan_row = next((row for row in plan.plan_rows if row.name == plan_row_name), None)
	if not plan_row:
		frappe.throw(_("The selected recipe row is not part of production plan {0}.").format(plan.name))
	station = get_production_plan_snapshot(plan.name, source_location).get("next_production") or {}
	cycle_number = int(station.get("cycle_number") or 1)
	if station.get("row") and station["row"].get("name") != plan_row.name:
		frappe.throw(_("This meal slot is not the next production in the current direction."))
	direction_action = direction_action or "Advance Direction"
	if direction_action not in {"Advance Direction", "Repeat Meal", "Off Plan"}:
		frappe.throw(_("Choose whether this run advances, repeats, or sits outside the meal direction."))
	recipe = recipe or plan_row.recipe
	planned_output_qty = round_operational_quantity(planned_output_qty or plan_row.planned_output_qty)
	existing = frappe.db.get_value(
		"BulkBite Production Run",
		{
			"production_plan": plan.name,
			"plan_week_number": plan_row.week_number,
			"cycle_number": cycle_number,
			"docstatus": 0,
		},
		"name",
		order_by="modified desc",
	)
	if existing:
		run = frappe.get_doc("BulkBite Production Run", existing)
		if run.docstatus:
			frappe.throw(_("This planned week has already been posted as production run {0}.").format(run.name))
		return _serialize_run(run)
	capacity_plan = get_production_plan_snapshot(plan.name, source_location).get("capacity_plan") or {}
	capacity_run = _capacity_run_for_meal(capacity_plan, plan_row.week_number)
	capacity_window = next((row for row in capacity_plan.get("windows") or [] if int(row.get("week_number") or 0) == int(plan_row.week_number or 0)), {})
	workforce = get_employee_capacity_snapshot(calculate_customer_demand(plan.customer_mix))
	return create_production_run(
		{
			"production_date": getdate(production_date),
			"business_name": plan.business_name,
			"production_plan": plan.name,
			"production_plan_row": plan_row.name,
			"plan_week_number": plan_row.week_number,
			"cycle_number": cycle_number,
			"direction_action": direction_action,
			"recipe": recipe,
			"planned_output_qty": planned_output_qty,
			"actual_output_qty": planned_output_qty,
			"team_template": capacity_run.get("team_template") or capacity_window.get("team_template") or plan.default_team_template,
			"scheduled_elapsed_hours": capacity_run.get("scheduled_elapsed_hours") or capacity_window.get("scheduled_elapsed_hours") or 8,
			"planned_takt_minutes_per_kg": workforce.get("planning_labour_minutes_per_kg"),
			"source_location": source_location,
			"target_location": target_location,
			"notes": _("Created from production plan {0}, meal {1}. Direction action: {2}.").format(plan.name, plan_row.week_number, direction_action),
		}
	)


def _capacity_run_for_meal(capacity_plan, meal_number):
	"""Return the first saved cooking session for one meal in the repeating direction."""
	return next(
		(
			row for row in (capacity_plan or {}).get("runs") or []
			if int(row.get("week_number") or 0) == int(meal_number or 0)
		),
		{},
	)

def _production_calendar_slot(rows, period_start, as_of_date=None, offset=0):
	"""Compatibility route for the dated production calendar resolver."""
	return production_calendar_slot(rows, period_start, as_of_date, offset)


def _skipped_production_weeks(rows, runs, period_start, as_of_date=None, intentional_skips=None):
	"""Return elapsed missed service periods without carrying their quantity forward."""
	return missed_service_periods(rows, runs, period_start, as_of_date, intentional_skips)


def _next_production_station(rows, runs, period_start=None, as_of_date=None, service_periods=None):
	"""Select current dated work while retaining old drafts as recoverable history."""
	ordered_rows = sorted(rows, key=lambda value: value.get("week_number") or 0)
	if not ordered_rows:
		return {"state": "empty", "row": None, "run": None, "cycle_number": 1, "skipped_weeks": []}
	calendar = resolve_current_service_period(rows, runs, period_start, as_of_date, service_periods)
	row_by_number = {int(row.get("cycle_week") or row["week_number"]): row for row in ordered_rows}
	drafts = sorted(
		(row for row in runs if not row.docstatus),
		key=lambda value: (int(value.cycle_number or 1), int(value.plan_week_number or 0), value.creation),
	)
	meal_number = int(calendar["row"]["week_number"])
	cycle_number = int(calendar["cycle_number"])
	current_draft = next(
		(
			draft for draft in drafts
			if int(draft.cycle_number or 1) == cycle_number
			and int(draft.plan_week_number or 0) == meal_number
		),
		None,
	)
	stale_drafts = [
		{"name": draft.name, "cycle_number": int(draft.cycle_number or 1), "meal_number": int(draft.plan_week_number or 0)}
		for draft in drafts if draft is not current_draft
	]
	skipped_weeks = _skipped_production_weeks(rows, runs, period_start, as_of_date, service_periods)
	if current_draft:
		return {
			"state": "draft",
			"row": row_by_number.get(meal_number) or calendar["row"],
			"run": _serialize_run(frappe.get_doc("BulkBite Production Run", current_draft.name)),
			"cycle_number": cycle_number,
			"calendar": calendar,
			"behind_calendar": False,
			"stale_drafts": stale_drafts,
			"skipped_weeks": skipped_weeks,
		}
	cycle_output = flt(calendar.get("actual_output_qty"))
	target_output = flt(calendar.get("planned_output_qty"))
	if cycle_output + 0.0005 < target_output:
		row = dict(calendar["row"])
		row["remaining_output_qty"] = round_operational_quantity(target_output - cycle_output)
		row["completed_output_qty"] = round_operational_quantity(cycle_output)
		return {"state": "remaining" if cycle_output else "ready", "row": row, "run": None, "cycle_number": cycle_number, "calendar": calendar, "behind_calendar": False, "stale_drafts": stale_drafts, "skipped_weeks": skipped_weeks}
	next_calendar = resolve_current_service_period(rows, runs, period_start, as_of_date, service_periods, offset=1)
	return {"state": "ready", "row": next_calendar["row"], "run": None, "cycle_number": next_calendar["cycle_number"], "calendar": next_calendar, "behind_calendar": False, "stale_drafts": stale_drafts, "skipped_weeks": skipped_weeks}


@frappe.whitelist(methods=["POST"])
def discard_production_run(name):
	"""Delete one unposted production draft so current direction can be loaded again."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus or run.stock_events_posted:
		frappe.throw(_("Posted production cannot be discarded. Use a correcting audit record."))
	run.delete()
	return {"name": name, "discarded": True}


@frappe.whitelist(methods=["POST"])
def cancel_production_plan(name):
	"""Delete an unused direction or cancel it while preserving posted production history."""
	_require_roles("BulkBite Manager")
	plan = frappe.get_doc("BulkBite Production Plan", name)
	posted = frappe.db.exists("BulkBite Production Run", {"production_plan": plan.name, "docstatus": 1})
	for draft_name in frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": plan.name, "docstatus": 0},
		pluck="name",
	):
		frappe.delete_doc("BulkBite Production Run", draft_name)
	if posted:
		plan.db_set("status", "Cancelled")
		return {"name": plan.name, "cancelled": True, "deleted": False}
	plan.delete()
	return {"name": name, "cancelled": False, "deleted": True}


# endregion PRODUCTION PLANNING


# =============================================================================
# region PURCHASING AND STOCK DRAFTS
# =============================================================================


@frappe.whitelist(methods=["POST"])
def start_receipt_extraction(file_url=None, file_urls=None):
	"""Queue private receipt extraction and return a pollable job. This never writes stock."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	urls = _as_list(file_urls) or ([file_url] if file_url else [])
	_validate_private_evidence(urls)
	sources = [resolve_private_source(url) for url in urls]
	for file_doc, _source_path, _source_hash in sources:
		attachment = frappe.db.get_value("File", file_doc.name, ["attached_to_doctype", "attached_to_name"], as_dict=True)
		duplicate = attachment.attached_to_name if attachment and attachment.attached_to_doctype == "BulkBite Receipt Intake" else None
		if duplicate:
			frappe.throw(_("This receipt file is already attached to {0}.").format(duplicate))
	combined_hash = frappe.generate_hash("|".join(row[2] for row in sources), 16)
	job_id = f"bulkbite-receipt-extraction-{sources[0][0].name}-{combined_hash}"
	job = frappe.enqueue(
		"bulkbite.api.process_receipt_extraction_job",
		queue="long",
		timeout=600,
		job_id=job_id,
		deduplicate=True,
		file_urls=urls,
		user=frappe.session.user,
	)
	return {"job_id": job.id if job else f"{frappe.local.site}||{job_id}", "status": "queued"}


def process_receipt_extraction_job(file_urls, user=None):
	results = []
	for index, file_url in enumerate(file_urls):
		file_doc, source_path, source_hash = resolve_private_source(file_url)
		result = extract_receipt_review(source_path, progress=_set_receipt_job_stage)
		result.update({"receipt_file": file_url, "source_hash": source_hash, "file_name": file_doc.file_name, "page_number": index + 1})
		results.append(result)
	return _merge_receipt_extractions(results)


def _merge_receipt_extractions(results):
	"""Merge several pages into one editable receipt proposal while keeping page evidence."""
	if not results:
		return {"lines": [], "warnings": ["No receipt pages were processed."]}
	first = results[0]
	lines, warnings, ocr_parts = [], [], []
	for result in results:
		for row in result.get("lines") or []:
			row["page_number"] = result["page_number"]
			lines.append(row)
		warnings.extend(result.get("warnings") or [])
		ocr_parts.append(f"FILE {result['page_number']}: {result['file_name']}\n{result.get('ocr_text') or ''}")
	return {
		**first,
		"receipt_files": [{"file_url": result["receipt_file"], "file_name": result["file_name"]} for result in results],
		"file_count": len(results),
		"lines": lines,
		"warnings": list(dict.fromkeys(warnings)),
		"ocr_text": "\n\n".join(ocr_parts),
		"confidence": round(sum(flt(result.get("confidence")) for result in results) / len(results), 3),
	}


@frappe.whitelist(methods=["POST"])
def start_cost_invoice_extraction(file_urls=None):
	"""Queue multi-file cost-invoice extraction. This never creates costs or stock."""
	_require_roles("BulkBite Manager")
	urls = _as_list(file_urls)
	_validate_private_evidence(urls)
	sources = [resolve_private_source(url) for url in urls]
	combined_hash = frappe.generate_hash("|".join(row[2] for row in sources), 16)
	job_id = f"bulkbite-cost-invoice-extraction-{sources[0][0].name}-{combined_hash}"
	job = frappe.enqueue(
		"bulkbite.api.process_cost_invoice_extraction_job", queue="long", timeout=600, job_id=job_id,
		deduplicate=True, file_urls=urls, user=frappe.session.user,
	)
	return {"job_id": job.id if job else f"{frappe.local.site}||{job_id}", "status": "queued"}


def process_cost_invoice_extraction_job(file_urls, user=None):
	"""Extract all invoice pages through the dedicated Pydantic expense contract."""
	sources = [resolve_private_source(file_url) for file_url in file_urls]
	return extract_cost_invoice_review([source_path for _file_doc, source_path, _source_hash in sources], progress=_set_receipt_job_stage)


def _set_receipt_job_stage(stage):
	from rq import get_current_job

	job = get_current_job()
	if job:
		job.meta["stage"] = stage
		job.save_meta()


@frappe.whitelist(methods=["GET"])
def get_receipt_extraction_status(job_id):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	job = get_job(str(job_id).removeprefix(f"{frappe.local.site}||"))
	if not job or job.kwargs.get("user") != frappe.session.user:
		frappe.throw(_("The receipt extraction job could not be found."), frappe.PermissionError)
	status = str(job.get_status(refresh=True))
	if status == "JobStatus.FINISHED" or status == "finished":
		return {"job_id": job.id, "status": "finished", "stage": "finished", "result": job.return_value(refresh=True)}
	if status == "JobStatus.FAILED" or status == "failed":
		return {"job_id": job.id, "status": "failed", "error": _("Receipt extraction failed. Check the file and try again.")}
	return {"job_id": job.id, "status": status.rsplit(".", 1)[-1].lower(), "stage": job.meta.get("stage") or "queued"}


@frappe.whitelist(methods=["GET"])
def get_cost_invoice_extraction_status(job_id):
	"""Return a manager's cost-invoice extraction status using the receipt job envelope."""
	_require_roles("BulkBite Manager")
	return get_receipt_extraction_status(job_id)


@frappe.whitelist(methods=["POST"])
def create_receipt_intake(payload=None):
	"""Store private purchase evidence and manually reviewed lines."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	if not data.get("supplier") or not data.get("invoice_date") or not data.get("default_location"):
		frappe.throw(_("Supplier, invoice date, and stock location are required."))
	if not _as_list(data.get("items")):
		frappe.throw(_("Add at least one receipt line."))
	evidence_urls = [data.get("receipt_file"), *[row.get("evidence_file") for row in _as_list(data.get("evidence_files"))]]
	_validate_private_evidence(evidence_urls)
	receipt = frappe.get_doc({"doctype": "BulkBite Receipt Intake", **data}).insert()
	_attach_private_evidence(evidence_urls, receipt.doctype, receipt.name)
	return {
		"name": receipt.name,
		"status": receipt.status,
		"total_amount": receipt.total_amount,
		"stock_events_posted": receipt.stock_events_posted,
	}


@frappe.whitelist(methods=["POST"])
def receive_stock_from_receipt(receipt_name):
	"""Add reviewed receipt quantities to stock exactly once."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	frappe.db.sql("select name from `tabBulkBite Receipt Intake` where name = %s for update", (receipt_name,))
	receipt = frappe.get_doc("BulkBite Receipt Intake", receipt_name)
	if receipt.stock_events_posted:
		return _serialize_received_receipt(receipt)
	if not receipt.items:
		frappe.throw(_("Review at least one receipt line before adding stock."))
	for row in receipt.items:
		event = append_stock_event(
			"Receipt",
			row.item_code,
			row.location or receipt.default_location,
			flt(row.qty),
			flt(row.rate),
			receipt.doctype,
			receipt.name,
			row.name,
		)
		row.db_set("stock_event", event.name, update_modified=False)
	receipt.db_set({"stock_events_posted": 1, "status": "Stock Received"})
	return _serialize_received_receipt(receipt.reload())


@frappe.whitelist(methods=["POST"])
def create_cost_invoice(payload=None):
	"""Store reviewed non-stock invoice evidence without creating actual costs yet."""
	_require_roles("BulkBite Manager")
	data = _as_dict(payload)
	evidence_urls = [row.get("evidence_file") for row in _as_list(data.get("evidence_files"))]
	_validate_private_evidence(evidence_urls)
	if not data.get("payee") or not data.get("invoice_date"):
		frappe.throw(_("Payee and invoice date are required."))
	if not _as_list(data.get("costs")):
		frappe.throw(_("Add at least one reviewed cost line."))
	data["costs"] = _resolve_cost_invoice_expense_types(_as_list(data.get("costs")))
	doc = frappe.get_doc({"doctype": "BulkBite Cost Invoice", **data}).insert()
	_attach_private_evidence(evidence_urls, doc.doctype, doc.name)
	return _serialize_cost_invoice(doc)


@frappe.whitelist(methods=["POST"])
def post_cost_invoice(name):
	"""Create ledger-backed miscellaneous actual expenses from one reviewed invoice once."""
	_require_roles("BulkBite Manager")
	frappe.db.sql("select name from `tabBulkBite Cost Invoice` where name = %s for update", (name,))
	invoice = frappe.get_doc("BulkBite Cost Invoice", name)
	if invoice.costs_posted:
		return _serialize_cost_invoice(invoice)
	if not invoice.costs:
		frappe.throw(_("Review at least one cost line before posting the invoice."))
	primary_evidence = invoice.evidence_files[0].evidence_file
	posted_entries = []
	line_vat_total = sum(flt(row.vat_amount) for row in invoice.costs)
	line_amount_total = sum(flt(row.amount) for row in invoice.costs)
	for row in invoice.costs:
		vat_amount = flt(row.vat_amount)
		if not line_vat_total and flt(invoice.tax_amount) and line_amount_total:
			vat_amount = round(flt(invoice.tax_amount) * flt(row.amount) / line_amount_total, 2)
		gross_amount = round(flt(row.amount) + vat_amount, 2)
		entry, event = create_actual_expense({
			"cost_date": invoice.invoice_date, "expense_type": row.expense_type, "cost_rule": row.cost_rule,
			"cost_category": row.cost_category, "payee": invoice.payee, "quantity": row.quantity,
			"unit_rate": row.unit_rate, "amount": gross_amount, "vat_amount": vat_amount,
			"currency": invoice.currency,
			"production_plan": invoice.production_plan, "evidence_file": primary_evidence,
			"accounting_category": row.accounting_category, "notes": f"From {invoice.name}: {row.description}. {row.notes or ''}".strip(),
		}, reference_doctype=invoice.doctype, reference_name=invoice.name, reference_line=row.name)
		row.db_set("cost_entry", entry.name, update_modified=False)
		row.db_set("finance_event", event.name, update_modified=False)
		posted_entries.append({"cost_entry": entry.name, "finance_event": event.name, "amount": flt(entry.amount)})
	truth = append_truth_event("COST_INVOICE_POSTED", invoice.doctype, invoice.name, {
		"invoice": invoice.name, "invoice_date": invoice.invoice_date, "document_type": invoice.document_type,
		"payee": invoice.payee, "invoice_number": invoice.invoice_number, "currency": invoice.currency,
		"subtotal_amount": flt(invoice.subtotal_amount), "tax_amount": flt(invoice.tax_amount),
		"total_amount": flt(invoice.total_amount), "actual_expenses": posted_entries,
	})
	invoice.db_set({"costs_posted": 1, "status": "Costs Posted", "truth_event": truth.name})
	return _serialize_cost_invoice(invoice.reload())


def _resolve_cost_invoice_expense_types(lines):
	"""Resolve reviewed expense types and create only manager-approved proposals."""
	resolved = []
	for supplied in lines:
		row = frappe._dict(supplied)
		expense_type = row.get("expense_type")
		if not expense_type and row.get("create_expense_type") and row.get("proposed_expense_type"):
			name = " ".join(str(row.proposed_expense_type).split())[:140]
			expense_type = frappe.db.get_value("BulkBite Expense Type", {"expense_type_name": name}, "name")
			if not expense_type:
				if not frappe.has_permission("BulkBite Expense Type", "create"):
					frappe.throw(_("You cannot create the proposed expense type {0}.").format(name), frappe.PermissionError)
				expense_type = frappe.get_doc({
					"doctype": "BulkBite Expense Type", "expense_type_name": name,
					"cost_category": row.get("cost_category") or "Other Production Overhead",
					"document_type": row.get("document_type") or "General Supplier Invoice",
					"default_vat_treatment": "Inclusive", "accounting_category": row.get("accounting_category"),
					"enabled": 1, "notes": _("Created during reviewed invoice intake."),
				}).insert().name
		if not expense_type or not frappe.db.exists("BulkBite Expense Type", expense_type):
			frappe.throw(_("Choose or approve an expense type for {0}.").format(row.get("description") or _("invoice line")))
		allowed = {"description", "cost_rule", "cost_category", "quantity", "unit_rate", "amount", "vat_amount", "accounting_category", "confidence", "source_quote", "uncertainty", "notes"}
		resolved.append({key: value for key, value in row.items() if key in allowed} | {"expense_type": expense_type})
	return resolved


@frappe.whitelist(methods=["GET"])
def get_purchase_price_history(item_code=None, supplier=None, from_date=None, to_date=None):
	"""Return chronological supplier-offer theory and reviewed-receipt actual prices."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	receipt_filters = {"status": ("!=", "Rejected")}
	if supplier:
		receipt_filters["supplier"] = supplier
	if from_date and to_date:
		start, end = getdate(from_date), getdate(to_date)
		if start > end:
			frappe.throw(_("From date must be on or before to date."))
		receipt_filters["invoice_date"] = ["between", [start, end]]
	elif from_date:
		receipt_filters["invoice_date"] = [">=", getdate(from_date)]
	elif to_date:
		receipt_filters["invoice_date"] = ["<=", getdate(to_date)]
	receipts = frappe.get_all(
		"BulkBite Receipt Intake",
		filters=receipt_filters,
		fields=["name", "invoice_date", "supplier", "supplier_invoice_number", "currency", "stock_events_posted"],
		order_by="invoice_date desc, name desc",
		limit_page_length=1000,
	)
	for receipt in receipts:
		receipt["adjustments"] = frappe.get_all(
			"BulkBite Receipt Adjustment",
			filters={"parenttype": "BulkBite Receipt Intake", "parent": receipt.name},
			fields=["adjustment_type", "description", "effect", "amount", "notes"],
			order_by="idx asc",
		)
	parent_names = [row.name for row in receipts]
	lines = []
	if parent_names:
		line_filters = {"parenttype": "BulkBite Receipt Intake", "parent": ["in", parent_names]}
		if item_code:
			line_filters["item_code"] = item_code
		lines = frappe.get_all(
			"BulkBite Receipt Line",
			filters=line_filters,
			fields=[
				"name", "parent", "item_code", "description", "purchase_qty", "units_per_pack", "unit_size",
				"purchase_uom", "qty", "uom", "amount", "price_per_pack", "price_per_unit", "rate",
			],
			order_by="parent desc, idx asc",
			limit_page_length=5000,
		)
	receipt_by_name = {row.name: row for row in receipts}
	item_records = frappe.get_all("BulkBite Item", fields=["item_code", "item_name", "stock_uom"])
	item_names = {row.item_code: row.item_name for row in item_records}
	item_uoms = {row.item_code: row.stock_uom for row in item_records}
	offer_filters = {}
	if item_code:
		offer_filters["item_code"] = item_code
	if supplier:
		offer_filters["supplier"] = supplier
	offers = frappe.get_all(
		"BulkBite Supplier Offer",
		filters=offer_filters,
		fields=[
			"name", "item_code", "supplier", "effective_from", "effective_to", "units_per_pack", "unit_size",
			"purchase_uom", "stock_qty_per_pack", "normal_price", "discounted_price", "discount_from", "discount_to",
			"currency", "price_includes_vat", "vat_rate", "enabled",
		],
		order_by="effective_from desc, creation desc",
		limit_page_length=5000,
	)
	rows = []
	for offer in offers:
		date = offer.effective_from
		if from_date and date and getdate(date) < getdate(from_date):
			continue
		if to_date and date and getdate(date) > getdate(to_date):
			continue
		from bulkbite.pricing import calculate_offer_price_bridge
		bridge = calculate_offer_price_bridge(offer, 1, date, True)
		selected_price = flt(bridge["landed_cost"])
		stock_qty = flt(offer.stock_qty_per_pack)
		rows.append({
			"record_type": "Theory",
			"record_name": offer.name,
			"date": date,
			"effective_to": offer.effective_to,
			"supplier": offer.supplier,
			"item_code": offer.item_code,
			"item_name": item_names.get(offer.item_code) or offer.item_code,
			"packs": 1,
			"units_per_pack": flt(offer.units_per_pack),
			"unit_size": flt(offer.unit_size),
			"purchase_uom": offer.purchase_uom,
			"stock_qty": stock_qty,
			"stock_uom": item_uoms.get(offer.item_code),
			"pack_price": selected_price,
			"inner_unit_price": selected_price / flt(offer.units_per_pack) if offer.units_per_pack else 0,
			"stock_unit_price": selected_price / stock_qty if stock_qty else 0,
			"theory_stock_unit_price": selected_price / stock_qty if stock_qty else 0,
			"variance": 0,
			"variance_percent": 0,
			"discounted_price": flt(offer.discounted_price),
			"base_pack_price": flt(offer.normal_price),
			"savings": bridge["savings"],
			"added_costs": bridge["added_costs"] + bridge["vat_added"],
			"price_bridge": bridge,
			"enabled": bool(offer.enabled),
			"reference": offer.name,
		})
	for line in lines:
		receipt = receipt_by_name[line.parent]
		theory = _applicable_supplier_offer(offers, line.item_code, receipt.supplier, receipt.invoice_date)
		theory_rate = _offer_stock_unit_price(theory, receipt.invoice_date) if theory else 0
		variance = flt(line.rate) - theory_rate if theory else None
		rows.append({
			"record_type": "Actual",
			"record_name": line.name,
			"date": receipt.invoice_date,
			"supplier": receipt.supplier,
			"stock_received": bool(receipt.stock_events_posted),
			"item_code": line.item_code,
			"item_name": item_names.get(line.item_code) or line.description or line.item_code,
			"packs": flt(line.purchase_qty),
			"units_per_pack": flt(line.units_per_pack),
			"unit_size": flt(line.unit_size),
			"purchase_uom": line.purchase_uom,
			"stock_qty": flt(line.qty),
			"stock_uom": line.uom,
			"pack_price": flt(line.price_per_pack),
			"inner_unit_price": flt(line.price_per_unit),
			"stock_unit_price": flt(line.rate),
			"theory_stock_unit_price": theory_rate or None,
			"variance": variance,
			"variance_percent": variance / theory_rate * 100 if theory_rate and variance is not None else None,
			"reference": receipt.name,
			"reference_detail": receipt.supplier_invoice_number,
		})
	rows.sort(key=lambda row: (str(row["date"] or ""), row["record_type"], row["record_name"]), reverse=True)
	return {
		"rows": rows,
		"summary": {
			"theory_count": sum(1 for row in rows if row["record_type"] == "Theory"),
			"actual_count": len(lines),
			"item_count": len({row["item_code"] for row in rows}),
			"supplier_count": len({row["supplier"] for row in rows}),
		},
	}


def _applicable_supplier_offer(offers, item_code, supplier, on_date):
	date = getdate(on_date)
	candidates = [
		offer for offer in offers
		if offer.item_code == item_code and offer.supplier == supplier
		and (not offer.effective_from or getdate(offer.effective_from) <= date)
		and (not offer.effective_to or getdate(offer.effective_to) >= date)
	]
	return sorted(candidates, key=lambda offer: str(offer.effective_from or ""), reverse=True)[0] if candidates else None


def _offer_stock_unit_price(offer, on_date):
	if not offer or not flt(offer.stock_qty_per_pack):
		return 0
	from bulkbite.pricing import calculate_offer_price_bridge
	price = flt(calculate_offer_price_bridge(offer, 1, on_date, True)["landed_cost"])
	return price / flt(offer.stock_qty_per_pack)


@frappe.whitelist(methods=["POST"])
def create_stock_count_draft(payload=None):
	"""Create a custom physical-count draft without changing stock."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	doc = frappe.get_doc(
		{
			"doctype": "BulkBite Stock Audit",
			"audit_date": getdate(data.get("posting_date")),
			"source_document": data.get("source_document"),
			"notes": data.get("notes"),
		}
	)
	for row in _as_list(data.get("items")):
		doc.append(
			"items",
			{
				"item_code": row.get("item_code"),
				"location": row.get("location"),
				"counted_qty": flt(row.get("qty")),
			},
		)
	doc.insert()
	return {"doctype": doc.doctype, "name": doc.name, "docstatus": doc.docstatus}


# endregion PURCHASING AND STOCK DRAFTS


# =============================================================================
# region AUDIT APPROVAL AND ACCOUNTANT EXPORT
# =============================================================================


@frappe.whitelist(methods=["GET"])
def get_spend_report(from_date, to_date):
	"""Return period theory versus actual purchasing without changing stock or accounting state."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	start, end = getdate(from_date), getdate(to_date)
	if start > end:
		frappe.throw(_("From date must be on or before to date."))
	report = enrich_spend_report(build_spend_report(start, end))
	report["production_capacity_actuals"] = _get_production_capacity_actuals(start, end)
	return report


def _get_production_capacity_actuals(from_date, to_date):
	"""Summarise posted team evidence for the selected reporting period."""
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"docstatus": 1, "production_date": ["between", [from_date, to_date]]},
		fields=["name", "production_date", "finished_item", "actual_output_qty", "actual_elapsed_hours", "actual_team_size", "actual_labour_hours", "actual_labour_minutes_per_kg", "planned_takt_minutes_per_kg", "takt_variance_minutes_per_kg", "takt_status"],
		order_by="production_date asc, name asc",
	)
	_enrich_run_workforce_evidence(runs)
	total_output = sum(flt(row.actual_output_qty) for row in runs)
	total_labour = sum(flt(row.actual_labour_hours) for row in runs)
	return {
		"summary": {
			"run_count": len(runs),
			"output_qty": round(total_output, 3),
			"labour_hours": round(total_labour, 2),
			"average_team_size": round(sum(flt(row.actual_team_size) for row in runs) / len(runs), 1) if runs else 0,
			"actual_labour_minutes_per_kg": round(total_labour * 60 / total_output, 2) if total_output else 0,
			"runs_on_pace": sum(1 for row in runs if row.takt_status in {"Faster than takt", "On pace"}),
		},
		"runs": runs,
	}


@frappe.whitelist(methods=["POST"])
def approve_stock_audit(name):
	"""Approve one reviewed physical count and append only its variances."""
	_require_roles("BulkBite Manager")
	audit = frappe.get_doc("BulkBite Stock Audit", name)
	if audit.docstatus == 1:
		return {"doctype": audit.doctype, "name": audit.name, "docstatus": audit.docstatus}
	audit.status = "Approved"
	audit.submit()
	return {"doctype": audit.doctype, "name": audit.name, "docstatus": audit.docstatus}


@frappe.whitelist(methods=["GET"])
def get_accountant_export(from_date, to_date):
	"""Return approved operational truth for an accountant. This station never changes stock."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	start = getdate(from_date)
	end = getdate(to_date)
	if start > end:
		frappe.throw(_("From date must be on or before to date."))
	receipts = frappe.get_all(
		"BulkBite Receipt Intake",
		filters={"invoice_date": ["between", [start, end]], "stock_events_posted": 1},
		fields=[
			"name",
			"invoice_date",
			"supplier",
			"supplier_invoice_number",
			"currency",
			"subtotal_amount",
			"tax_amount",
			"total_amount",
			"accounting_category",
		],
		order_by="invoice_date asc, name asc",
	)
	for receipt in receipts:
		receipt["adjustments"] = frappe.get_all(
			"BulkBite Receipt Adjustment",
			filters={"parenttype": "BulkBite Receipt Intake", "parent": receipt.name},
			fields=["adjustment_type", "description", "effect", "amount", "notes"],
			order_by="idx asc",
		)
	stock_events = frappe.get_all(
		"BulkBite Stock Event",
		filters={"posting_datetime": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]},
		fields=[
			"event_sequence",
			"posting_datetime",
			"event_type",
			"item_code",
			"location",
			"quantity_delta",
			"uom",
			"unit_cost",
			"value_delta",
			"reference_doctype",
			"reference_name",
			"actor",
			"event_hash",
		],
		order_by="event_sequence asc",
	)
	balances = frappe.get_all(
		"BulkBite Stock Balance",
		fields=["item_code", "location", "actual_qty", "uom", "valuation_rate", "stock_value", "last_event"],
		order_by="item_code asc, location asc",
	)
	cost_entries = frappe.get_all(
		"BulkBite Cost Entry",
		filters={"cost_date": ["between", [start, end]]},
		fields=["name", "cost_date", "expense_type", "cost_rule", "cost_category", "payee", "quantity", "unit_rate", "amount", "vat_amount", "currency", "production_plan", "production_run", "employee", "evidence_file", "accounting_category", "finance_event", "notes"],
		order_by="cost_date asc, name asc",
	)
	finance_ledger = get_finance_ledger(start, end)
	return {
		"period": {"from_date": start, "to_date": end, "currency": "ZAR"},
		"receipts": receipts,
		"stock_events": stock_events,
		"closing_stock": balances,
		"operating_costs": cost_entries,
		"finance_events": finance_ledger["rows"],
		"finance_chain": finance_ledger["summary"]["chain"],
		"note": _("Operational export only. The accountant assigns accounts, tax treatment, and journal entries."),
	}


@frappe.whitelist(methods=["GET"])
def download_accountant_export(from_date, to_date, dataset="receipts"):
	"""Download one accountant dataset as CSV without altering export state."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	data = get_accountant_export(from_date, to_date)
	if dataset not in {"receipts", "stock_events", "closing_stock", "operating_costs", "finance_events"}:
		frappe.throw(_("Choose receipts, stock_events, closing_stock, operating_costs, or finance_events."))
	rows = data[dataset]
	stream = io.StringIO()
	fieldnames = list(rows[0].keys()) if rows else ["no_records"]
	writer = csv.DictWriter(stream, fieldnames=fieldnames)
	writer.writeheader()
	if rows:
		writer.writerows(rows)
	frappe.response.filename = f"bulkbite-{dataset}-{getdate(from_date)}-to-{getdate(to_date)}.csv"
	frappe.response.filecontent = stream.getvalue()
	frappe.response.type = "download"


@frappe.whitelist(methods=["GET"])
def download_finance_ledger_workbook(from_date, to_date):
	"""Download verified immutable finance events as one plain Excel worksheet."""
	_require_roles("BulkBite Manager", "BulkBite Accountant")
	frappe.response.filename = f"bulkbite-finance-ledger-{getdate(from_date)}-to-{getdate(to_date)}.xlsx"
	frappe.response.filecontent = build_finance_ledger_workbook(from_date, to_date)
	frappe.response.type = "binary"


# endregion AUDIT APPROVAL AND ACCOUNTANT EXPORT


# =============================================================================
# region SPREADSHEET INTAKE
# =============================================================================


@frappe.whitelist(methods=["GET"])
def download_price_workbook(fields=None):
	"""Download selected supplier catalogue columns as one plain worksheet."""
	_require_roles("BulkBite Manager")
	frappe.response.filename = f"bulkbite-prices-{nowdate()}.xlsx"
	frappe.response.filecontent = build_price_workbook(fields)
	frappe.response.type = "binary"


@frappe.whitelist(methods=["GET"])
def get_price_import_fields():
	"""Return selectable export and import fields without reading or changing catalogue data."""
	_require_roles("BulkBite Manager")
	return get_price_field_contract()


@frappe.whitelist(methods=["POST"])
def inspect_catalogue_price_file(file_url):
	"""Suggest source-column matches. This station never changes catalogue or stock records."""
	_require_roles("BulkBite Manager")
	return inspect_price_import(file_url)


@frappe.whitelist(methods=["POST"])
def preview_catalogue_price_workbook(file_url, mapping=None):
	"""Create a reviewed change batch from the confirmed field map."""
	_require_roles("BulkBite Manager")
	return preview_price_import(file_url, mapping)


@frappe.whitelist(methods=["POST"])
def improve_catalogue_price_workbook(batch_name):
	"""Run AI improvement synchronously for backwards-compatible integrations."""
	_require_roles("BulkBite Manager")
	return improve_price_import(batch_name)


@frappe.whitelist(methods=["POST"])
def start_catalogue_price_improvement(batch_name):
	"""Queue AI suggestions for one saved review without applying catalogue changes."""
	_require_roles("BulkBite Manager")
	batch = frappe.get_doc("BulkBite Price Import Batch", batch_name)
	batch.check_permission("write")
	if batch.status == "Applied":
		frappe.throw(_("An applied import cannot be changed."))
	proposal_hash = hashlib.sha256((batch.preview_json or batch.name).encode("utf-8")).hexdigest()[:16]
	job_id = f"bulkbite-price-improvement-{batch.name}-{proposal_hash}"
	job = frappe.enqueue(
		"bulkbite.api.process_catalogue_price_improvement_job",
		queue="long",
		timeout=600,
		job_id=job_id,
		deduplicate=True,
		batch_name=batch.name,
		user=frappe.session.user,
	)
	return {"job_id": job.id if job else f"{frappe.local.site}||{job_id}", "status": "queued", "stage": "queued"}


def process_catalogue_price_improvement_job(batch_name, user=None):
	"""Improve the saved proposal in a worker and keep the initiating user's permissions."""
	if user:
		frappe.set_user(user)
	_set_catalogue_price_job_stage("matching existing setup")
	return improve_price_import(batch_name, progress=_set_catalogue_price_job_stage)


def _set_catalogue_price_job_stage(stage):
	"""Publish a safe progress label for the catalogue-review poller."""
	from rq import get_current_job

	job = get_current_job()
	if job:
		job.meta["stage"] = stage
		job.save_meta()


@frappe.whitelist(methods=["GET"])
def get_catalogue_price_improvement_status(job_id):
	"""Return AI progress only to the manager who started the job."""
	_require_roles("BulkBite Manager")
	job = get_job(str(job_id).removeprefix(f"{frappe.local.site}||"))
	if not job or job.kwargs.get("user") != frappe.session.user:
		frappe.throw(_("The catalogue improvement job could not be found."), frappe.PermissionError)
	status = str(job.get_status(refresh=True))
	if status == "JobStatus.FINISHED" or status == "finished":
		return {"job_id": job.id, "status": "finished", "stage": "ready for review", "result": job.return_value(refresh=True)}
	if status == "JobStatus.FAILED" or status == "failed":
		return {
			"job_id": job.id,
			"status": "failed",
			"stage": job.meta.get("stage") or "failed",
			"error": _("AI catalogue improvement failed. Your saved review was not applied. Check the AI configuration and try again."),
		}
	return {"job_id": job.id, "status": status.rsplit(".", 1)[-1].lower(), "stage": job.meta.get("stage") or "queued"}


@frappe.whitelist(methods=["POST"])
def review_catalogue_price_workbook(batch_name, proposal):
	"""Save and revalidate manager edits without changing setup, offers, stock, or ledgers."""
	_require_roles("BulkBite Manager")
	return review_price_import(batch_name, proposal)


@frappe.whitelist(methods=["POST"])
def apply_catalogue_price_workbook(batch_name):
	"""Apply an error-free reviewed price batch without creating stock or accounting entries."""
	_require_roles("BulkBite Manager")
	return apply_price_import(batch_name)


@frappe.whitelist(methods=["GET"])
def get_spreadsheet_workspace_contract(target="recipes", setup_doctype=None):
	"""Return the controlled recipe or setup-data spreadsheet contract."""
	_require_roles("BulkBite Manager")
	return get_workspace_contract(target, setup_doctype)


@frappe.whitelist(methods=["GET"])
def download_spreadsheet_workspace(target="recipes", fields=None, setup_doctype=None):
	"""Download one plain, context-aware spreadsheet from an approved target."""
	_require_roles("BulkBite Manager")
	contract = get_workspace_contract(target, setup_doctype)
	frappe.response.filename = f"bulkbite-{contract['label'].lower().replace(' ', '-')}-{nowdate()}.xlsx"
	frappe.response.filecontent = build_workspace_workbook(target, fields, setup_doctype)
	frappe.response.type = "binary"


@frappe.whitelist(methods=["POST"])
def inspect_spreadsheet_workspace_file(target, file_url, setup_doctype=None):
	"""Suggest source-column matches for an approved target without writing records."""
	_require_roles("BulkBite Manager")
	return inspect_workspace_file(target, file_url, setup_doctype)


@frappe.whitelist(methods=["POST"])
def preview_spreadsheet_workspace_import(target, file_url, mapping=None, setup_doctype=None):
	"""Save an editable recipe or setup-data preview without applying it."""
	_require_roles("BulkBite Manager")
	return preview_workspace_import(target, file_url, mapping, setup_doctype)


@frappe.whitelist(methods=["POST"])
def review_spreadsheet_workspace_import(batch_name, proposal):
	"""Revalidate manager edits without changing setup or operational truth."""
	_require_roles("BulkBite Manager")
	return review_workspace_import(batch_name, proposal)


@frappe.whitelist(methods=["POST"])
def apply_spreadsheet_workspace_import(batch_name):
	"""Apply only the reviewed allowlisted records, never stock or ledger movements."""
	_require_roles("BulkBite Manager")
	return apply_workspace_import(batch_name)


# =============================================================================
# region OFFLINE DRAFT SYNCHRONIZATION
# =============================================================================


@frappe.whitelist(methods=["POST"])
def sync_offline_mutation(client_mutation_id, operation, payload, base_modified=None, overwrite_conflict=False):
	"""Apply one safe draft mutation exactly once and pause on server-version conflicts."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	client_mutation_id = str(client_mutation_id or "").strip()
	if not client_mutation_id or len(client_mutation_id) > 140:
		frappe.throw(_("The offline change ID is invalid."))
	data = _as_dict(payload)
	payload_hash = hashlib.sha256(json.dumps({"operation": operation, "payload": data}, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
	frappe.db.sql("select name from `tabDocType` where name = %s for update", ("BulkBite Offline Mutation",))
	existing = frappe.db.get_value("BulkBite Offline Mutation", client_mutation_id, ["requested_by", "payload_hash", "status", "result_json"], as_dict=True)
	if existing:
		if existing.requested_by != frappe.session.user or existing.payload_hash != payload_hash:
			frappe.throw(_("This offline change ID belongs to a different request."), frappe.PermissionError)
		if existing.status == "Completed":
			return frappe.parse_json(existing.result_json)
		frappe.db.set_value("BulkBite Offline Mutation", client_mutation_id, {"status": "Processing", "result_json": None}, update_modified=False)
	if not existing:
		frappe.get_doc({"doctype": "BulkBite Offline Mutation", "client_mutation_id": client_mutation_id, "operation": operation, "status": "Processing", "requested_by": frappe.session.user, "payload_hash": payload_hash}).insert(ignore_permissions=True)
	savepoint = f"offline_mutation_{hashlib.sha256(client_mutation_id.encode('utf-8')).hexdigest()[:12]}"
	frappe.db.savepoint(savepoint)
	try:
		result = _apply_offline_draft(operation, data, base_modified, bool(overwrite_conflict))
	except Exception as exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.db.set_value(
			"BulkBite Offline Mutation", client_mutation_id,
			{"status": "Failed", "result_json": frappe.as_json({"error": str(exception)})},
			update_modified=False,
		)
		frappe.db.commit()
		raise
	response = {"client_mutation_id": client_mutation_id, "operation": operation, "status": "completed", "result": result}
	frappe.db.set_value("BulkBite Offline Mutation", client_mutation_id, {"status": "Completed", "result_json": frappe.as_json(response), "completed_on": now_datetime()}, update_modified=False)
	return response


def _apply_offline_draft(operation, data, base_modified, overwrite_conflict):
	"""Dispatch only draft-safe operations. Posted truth is intentionally excluded."""
	if operation == "save_production_plan":
		_assert_offline_version("BulkBite Production Plan", data.get("name"), base_modified, overwrite_conflict)
		return save_monthly_production_plan(data)
	if operation == "save_production_draft":
		return _sync_production_draft(data, base_modified, overwrite_conflict)
	if operation == "create_receipt_draft":
		if data.get("name"):
			frappe.throw(_("Existing receipts cannot be overwritten by offline synchronization."))
		return create_receipt_intake(data)
	frappe.throw(_("This operation is not allowed through offline synchronization."), frappe.PermissionError)


def _sync_production_draft(data, base_modified, overwrite_conflict):
	"""Create or update the production draft, measurements, and team as one replayable station."""
	run_name = data.get("name")
	if run_name:
		_assert_offline_version("BulkBite Production Run", run_name, base_modified, overwrite_conflict)
		run = frappe.get_doc("BulkBite Production Run", run_name)
		if run.docstatus:
			frappe.throw(_("Posted production cannot be changed by offline synchronization."))
	elif data.get("direction_action") == "Off Plan" and not data.get("plan_row_name"):
		run = create_ad_hoc_production_run(
			data.get("recipe"), data.get("planned_output_qty"), data.get("production_date"),
			data.get("source_location") or "Ingredients", data.get("target_location") or "Finished Meals",
		)
		run_name = run.get("name")
	else:
		run = create_run_from_plan(
			data.get("plan_name"), data.get("plan_row_name"), data.get("production_date"),
			data.get("source_location"), data.get("target_location"), data.get("recipe"),
			data.get("planned_output_qty"), data.get("direction_action"),
		)
		run_name = run.get("name")
	run = update_production_actuals(run_name, data.get("actual_output_qty"), data.get("ingredients"), data.get("notes"), data.get("finished_container_count"))
	run = save_production_employees(run_name, data.get("employees"), data.get("team_template"), data.get("actual_elapsed_hours"), data.get("scheduled_elapsed_hours"))
	return run


def _assert_offline_version(doctype, name, base_modified, overwrite_conflict):
	"""Reject silent last-write-wins when another session changed the draft."""
	if not name or not frappe.db.exists(doctype, name):
		return
	current = frappe.db.get_value(doctype, name, "modified")
	if base_modified and str(current) != str(base_modified) and not overwrite_conflict:
		server = frappe.get_doc(doctype, name).as_dict(no_nulls=True)
		frappe.throw(
			_("CONFLICT: {0}").format(frappe.as_json({
				"doctype": doctype,
				"name": name,
				"base_modified": base_modified,
				"server_modified": current,
				"server": _offline_conflict_fields(server),
			})),
			frappe.TimestampMismatchError,
		)


def _offline_conflict_fields(document, top_level=True):
	"""Return nested mutable business values without framework or posting metadata."""
	excluded = {
		"doctype", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
		"parent", "parentfield", "parenttype", "stock_events_posted", "employee_costs_posted",
		"truth_event", "output_stock_event",
	}
	if isinstance(document, (list, tuple)):
		return [_offline_conflict_fields(value, top_level=False) for value in document]
	if isinstance(document, dict):
		return {
			key: _offline_conflict_fields(value, top_level=False)
			for key, value in document.items()
			if key not in excluded and (top_level or key != "name")
		}
	return document


# endregion OFFLINE DRAFT SYNCHRONIZATION


@frappe.whitelist(methods=["POST"])
def preview_theory_workbook(file_url):
	"""Read workbook structure for mapping. This station never writes records."""
	_require_roles("BulkBite Manager")
	file_doc = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name", "is_private"], as_dict=True)
	if not file_doc:
		frappe.throw(_("Upload the spreadsheet before previewing it."))
	path = Path(frappe.get_site_path("private" if file_doc.is_private else "public", "files", file_doc.file_name))
	if path.suffix.lower() not in {".xlsx", ".xlsm"}:
		frappe.throw(_("Use an .xlsx or .xlsm workbook for the first import pass."))
	workbook = load_workbook(path, read_only=True, data_only=True)
	return {
		"file_name": file_doc.file_name,
		"sheets": [_preview_sheet(sheet) for sheet in workbook.worksheets],
		"next_step": "Map recipe, ingredient, quantity, unit, yield, and date columns before importing theory.",
	}


def _preview_sheet(sheet):
	rows = list(sheet.iter_rows(min_row=1, max_row=8, values_only=True))
	return {
		"name": sheet.title,
		"max_row": sheet.max_row,
		"max_column": sheet.max_column,
		"headers": [_cell(value) for value in (rows[0] if rows else [])],
		"sample_rows": [[_cell(value) for value in row] for row in rows[1:]],
	}


def _cell(value):
	return value.isoformat() if hasattr(value, "isoformat") else value


# endregion SPREADSHEET INTAKE


# =============================================================================
# region WORKER DOCUMENT INTAKE
# =============================================================================


@frappe.whitelist(methods=["POST"])
def create_document_extraction_draft(payload=None):
	"""Store private text evidence and parser suggestions for human review only."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	file_doc, source_path, source_hash = resolve_private_source(data.get("source_file"))
	existing = frappe.db.get_value("BulkBite Document Intake", {"source_hash": source_hash}, "name")
	if existing:
		frappe.throw(_("This document was already uploaded as {0}.").format(existing))
	extracted = extract_private_text(source_path)
	raw_text = str(data.get("raw_text") or extracted["raw_text"] or "").strip()
	if not raw_text:
		frappe.throw(_("No text could be extracted. Enter a transcription of the written measurements, then create the review draft."))
	parser_mode = "Local text parser"
	proposed_rows = None
	parser_warning = extracted.get("warning")
	if ai_is_configured():
		try:
			ai_result = extract_measurements_with_ai(raw_text, data.get("document_type"), extracted.get("evidence"))
			if ai_result:
				proposed_rows = [row.model_dump() for row in ai_result.lines]
				parser_mode = "Structured AI with local validation"
		except Exception:
			frappe.log_error(frappe.get_traceback(), "BulkBite document AI fallback")
			parser_warning = _("AI enhancement was unavailable. Local parsing was used instead.")
	rows = extract_measurement_rows(raw_text, proposed_rows)
	if not rows:
		frappe.throw(_("No measurement lines were found in the supplied text."))
	warnings = [parser_warning] if parser_warning else []
	warnings.extend(row["warning"] for row in rows if row.get("warning"))
	doc = frappe.get_doc(
		{
			"doctype": "BulkBite Document Intake",
			"status": "Needs Review" if warnings else "Extracted Draft",
			"document_type": data.get("document_type"),
			"source_file": data.get("source_file"),
			"source_hash": source_hash,
			"business_name": data.get("business_name") or "BulkBite",
			"production_run": data.get("production_run"),
			"default_location": data.get("default_location"),
			"raw_text": raw_text,
			"text_provider": extracted["provider"] if not data.get("raw_text") else "User transcription",
			"parser_mode": parser_mode,
			"extraction_evidence": extracted.get("evidence"),
			"processed_at": now_datetime(),
			"rows": rows,
			"warnings": "\n".join(dict.fromkeys(warnings)),
		}
	).insert()
	frappe.db.set_value("File", file_doc.name, {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}, update_modified=False)
	return _serialize_document_intake(doc)


@frappe.whitelist(methods=["POST"])
def review_document_extraction(name, rows):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	doc = frappe.get_doc("BulkBite Document Intake", name)
	if doc.status == "Applied":
		frappe.throw(_("Applied document measurements cannot be reviewed again."))
	reviewed_rows = _as_list(rows)
	if not any(row.get("accepted") for row in reviewed_rows):
		frappe.throw(_("Approve at least one reviewed measurement row."))
	for row in reviewed_rows:
		if row.get("accepted") and (not row.get("item_code") or flt(row.get("qty")) < 0 or not row.get("uom")):
			frappe.throw(_("Every approved row needs an item, a non-negative quantity, and a unit."))
	doc.set("rows", reviewed_rows)
	doc.status = "Reviewed"
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = now_datetime()
	doc.save()
	return _serialize_document_intake(doc)


@frappe.whitelist(methods=["POST"])
def apply_document_measurements(name):
	"""Apply reviewed rows to a production draft or create an audit draft. Never submit an audit."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	doc = frappe.get_doc("BulkBite Document Intake", name)
	if doc.status != "Reviewed":
		frappe.throw(_("Review and approve the extracted rows before applying them."))
	rows = [row for row in doc.rows if row.accepted]
	if not rows:
		frappe.throw(_("Approve at least one extracted row."))
	if doc.document_type == "Stock Audit":
		result = create_stock_count_draft(
			{
				"posting_date": getdate(),
				"source_document": doc.name,
				"items": [
					{"item_code": row.item_code, "location": doc.default_location, "qty": row.qty}
					for row in rows
				],
			}
		)
	else:
		run = frappe.get_doc("BulkBite Production Run", doc.production_run)
		by_item = {row.item_code: row for row in rows}
		measurements = []
		for usage in run.ingredients:
			extracted = by_item.get(usage.item_code)
			method = (
				"Remaining"
				if extracted and doc.document_type == "Remaining Stock Sheet"
				else "Used"
				if extracted and doc.document_type == "Usage Sheet"
				else usage.measurement_method or "Used"
			)
			measurements.append(
				{
					"item_code": usage.item_code,
					"actual_qty": extracted.qty if extracted and doc.document_type == "Usage Sheet" else usage.actual_qty,
					"remaining_qty": extracted.qty if extracted and doc.document_type == "Remaining Stock Sheet" else usage.remaining_qty,
					"measurement_method": method,
					"notes": _("Reviewed from worker document {0}").format(doc.name) if extracted else usage.notes,
				}
			)
		result = update_production_actuals(run.name, run.actual_output_qty, measurements, run.notes)
		result = {"doctype": "BulkBite Production Run", "name": result["name"], "docstatus": result["docstatus"]}
	doc.db_set({"status": "Applied", "applied_reference_doctype": result["doctype"], "applied_reference": result["name"]})
	return result


def _serialize_document_intake(doc):
	return {
		"name": doc.name,
		"status": doc.status,
		"document_type": doc.document_type,
		"warnings": doc.warnings,
		"text_provider": doc.text_provider,
		"parser_mode": doc.parser_mode,
		"rows": [row.as_dict() for row in doc.rows],
		"applied_reference_doctype": doc.applied_reference_doctype,
		"applied_reference": doc.applied_reference,
	}


# endregion WORKER DOCUMENT INTAKE


# =============================================================================
# region API BOUNDARIES
# =============================================================================


def _require_app_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Sign in to use BulkBite."), frappe.PermissionError)
	allowed_roles = {"System Manager", "BulkBite Worker", "BulkBite Manager", "BulkBite Accountant"}
	if frappe.session.user != "Administrator" and not allowed_roles.intersection(frappe.get_roles()):
		frappe.throw(_("Your account does not have a BulkBite operations role."), frappe.PermissionError)


def _require_roles(*roles):
	"""Authorize one API station without broadening document permissions."""
	_require_app_user()
	if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
		return
	if not set(roles).intersection(frappe.get_roles()):
		frappe.throw(_("Your BulkBite role cannot perform this action."), frappe.PermissionError)


def _as_dict(value):
	if isinstance(value, str):
		value = json.loads(value)
	return frappe._dict(value or {})


def _as_list(value):
	if isinstance(value, str):
		value = json.loads(value)
	return value or []


def _as_bool(value):
	return str(value).lower() in {"1", "true", "yes"}


def _serialize_run(run):
	quantity_fields = {
		"expected_qty",
		"actual_qty",
		"remaining_qty",
		"available_before_measurement",
		"variance_qty",
	}
	ingredients = []
	for row in run.ingredients:
		value = row.as_dict()
		for field in quantity_fields:
			if value.get(field) is not None:
				value[field] = round(flt(value[field]), 3)
		ingredients.append(value)
	employees = [row.as_dict() for row in run.employees or []]
	return {
		"name": run.name,
		"modified": run.modified,
		"docstatus": run.docstatus,
		"production_date": run.production_date,
		"business_name": run.business_name,
		"production_plan": run.production_plan,
		"production_plan_row": run.production_plan_row,
		"plan_week_number": run.plan_week_number,
		"cycle_number": run.cycle_number,
		"direction_action": run.direction_action,
		"recipe": run.recipe,
		"finished_item": run.finished_item,
		"planned_output_qty": round(flt(run.planned_output_qty), 3),
		"actual_output_qty": round(flt(run.actual_output_qty), 3),
		"finished_container_count": int(run.finished_container_count or 0),
		"average_container_qty": round(flt(run.average_container_qty), 3),
		"output_variance_qty": round(flt(run.output_variance_qty), 3),
		"output_variance_percent": run.output_variance_percent,
		"expected_material_cost": run.expected_material_cost,
		"actual_material_cost": run.actual_material_cost,
		"material_cost_variance": run.material_cost_variance,
		"team_template": run.team_template,
		"scheduled_elapsed_hours": round(flt(run.scheduled_elapsed_hours), 2),
		"actual_elapsed_hours": round(flt(run.actual_elapsed_hours), 2),
		"actual_team_size": int(run.actual_team_size or 0),
		"actual_labour_hours": round(flt(run.actual_labour_hours), 2),
		"actual_labour_minutes_per_kg": round(flt(run.actual_labour_minutes_per_kg), 2),
		"planned_takt_minutes_per_kg": round(flt(run.planned_takt_minutes_per_kg), 2),
		"takt_variance_minutes_per_kg": round(flt(run.takt_variance_minutes_per_kg), 2),
		"takt_status": run.takt_status,
		"output_stock_event": run.output_stock_event,
		"truth_event": run.truth_event,
		"notes": run.notes,
		"ingredients": ingredients,
		"employees": employees,
		"employee_costs_posted": run.employee_costs_posted,
	}


def _serialize_received_receipt(doc):
	return {
		"doctype": "BulkBite Receipt Intake",
		"name": doc.name,
		"docstatus": 1 if doc.stock_events_posted else 0,
		"total_qty": sum(flt(row.qty) for row in doc.items),
		"grand_total": doc.total_amount,
	}


def _serialize_cost_invoice(doc):
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"status": doc.status,
		"costs_posted": bool(doc.costs_posted),
		"line_count": len(doc.costs),
		"total_amount": doc.total_amount,
	}


def _validate_private_evidence(file_urls):
	urls = list(dict.fromkeys(url for url in file_urls if url))
	if not urls:
		frappe.throw(_("Upload at least one private evidence file."))
	files = frappe.get_all("File", filters={"file_url": ["in", urls]}, fields=["file_url", "is_private"])
	private_urls = {row.file_url for row in files if row.is_private}
	if private_urls != set(urls):
		frappe.throw(_("Every receipt or invoice file must be uploaded privately before saving."))


def _attach_private_evidence(file_urls, doctype, name):
	for url in dict.fromkeys(file_url for file_url in file_urls if file_url):
		frappe.db.set_value("File", {"file_url": url}, {"attached_to_doctype": doctype, "attached_to_name": name}, update_modified=False)


def _current_valuation_rate(item_code, location):
	return get_valuation_rate(item_code, location)


# endregion API BOUNDARIES
