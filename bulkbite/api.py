from __future__ import annotations

import json
import csv
import io
from pathlib import Path

import frappe
from frappe import _
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
from bulkbite.finance_ledger import create_actual_expense, get_finance_ledger
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
from bulkbite.workforce import calculate_assignment_pay, get_employee_capacity_snapshot, get_employee_production_history
from bulkbite.price_workbook import (
	apply_price_import,
	build_price_workbook,
	get_price_field_contract,
	inspect_price_import,
	preview_price_import,
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
		fields=["name", "production_date", "finished_item", "planned_output_qty", "actual_output_qty", "material_cost_variance", "docstatus", "output_stock_event"],
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
			"recipes": frappe.get_all("BulkBite Recipe", filters={"status": "Approved"}, fields=["name", "recipe_name", "finished_item as item", "nominal_output_qty as quantity", "output_uom as uom"], order_by="recipe_name"),
			"suppliers": frappe.get_all("BulkBite Supplier", filters={"enabled": 1}, pluck="name", order_by="name"),
			"production_plans": frappe.get_all("BulkBite Production Plan", filters={"status": ("in", ["Relative Draft", "Dated Draft", "Active"])}, fields=["name as value", "plan_title as label"], order_by="modified desc"),
			"customer_plan_types": frappe.get_all("BulkBite Customer Plan Type", filters={"enabled": 1}, fields=["name", "serving_size_g", "meals_per_day", "days_per_week", "cycle_weeks"], order_by="serving_size_g"),
			"item_categories": frappe.get_all("BulkBite Item Category", filters={"enabled": 1}, fields=["name", "default_supplier"], order_by="name"),
			"operating_cost_rules": frappe.get_all("BulkBite Operating Cost Rule", filters={"enabled": 1}, fields=["name as value", "cost_name as label", "cost_category", "basis", "rate"], order_by="cost_category, cost_name"),
			"employees": frappe.get_all("BulkBite Employee", filters={"status": "Active", "available_for_production": 1}, fields=["name as value", "full_name as label", "employee_type", "available_hours_per_run"], order_by="full_name"),
		},
	}
	for run in result["recent_runs"]:
		for field in ("planned_output_qty", "actual_output_qty"):
			run[field] = round_operational_quantity(run.get(field))
	_enrich_document_effects(result["recent_receipts"], "BulkBite Receipt Line", "items")
	_enrich_document_effects(result["recent_cost_invoices"], "BulkBite Cost Invoice Line", "costs")
	return result


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
		for row in frappe.get_all(doctype, fields=fields, order_by=f"{label_field} asc", limit_page_length=1000)
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
def save_production_employees(name, employees=None):
	"""Freeze reviewed employee attendance and pay facts for one draft run."""
	_require_roles("BulkBite Worker", "BulkBite Manager")
	run = frappe.get_doc("BulkBite Production Run", name)
	if run.docstatus != 0:
		frappe.throw(_("Employees can only be changed on a draft production run."))
	rows = []
	for supplied in _as_list(employees):
		if not supplied.get("employee"):
			continue
		employee = frappe.get_doc("BulkBite Employee", supplied.get("employee"))
		if employee.status != "Active":
			frappe.throw(_("{0} is not an active employee.").format(employee.full_name))
		employee_type = frappe.get_doc("BulkBite Employee Type", employee.employee_type)
		supplied_available_hours = supplied.get("available_hours")
		available_hours = flt(supplied_available_hours)
		if available_hours < 0:
			frappe.throw(_("Available hours for {0} cannot be negative.").format(employee.full_name))
		if supplied_available_hours in (None, ""):
			available_hours = flt(employee.available_hours_per_run) or flt(employee_type.expected_hours_per_run)
		payment_basis = employee.payment_basis_override if employee.use_payment_override and employee.payment_basis_override else employee_type.payment_basis
		payment_rate = employee.payment_rate_override if employee.use_payment_override else employee_type.payment_rate
		pay = calculate_assignment_pay(frappe._dict({"payment_basis": payment_basis, "payment_rate": payment_rate}), supplied.get("hours_worked"), supplied.get("completion_status") or "Completed")
		rows.append({
			"employee": employee.name, "employee_name": employee.full_name, "employee_type": employee.employee_type,
			"available_hours": available_hours, "hours_worked": flt(supplied.get("hours_worked")), "completion_status": supplied.get("completion_status") or "Completed",
			**pay, "notes": supplied.get("notes"),
		})
	run.set("employees", rows)
	run.save()
	return _serialize_run(run)


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
	"BulkBite Production Plan": {"label": "Production plans", "singular_label": "plan", "description": "Planned recipes and meal quantities used by the production workflow."},
}
_AUXILIARY_FIELD_TYPES = {"Data", "Int", "Float", "Currency", "Date", "Select", "Check", "Small Text", "Text", "Long Text", "Link", "Table"}


@frappe.whitelist(methods=["GET"])
def get_auxiliary_form_catalogue():
	"""Return the permission-aware supporting-record destinations used by linked fields."""
	_require_app_user()
	return [
		{
			"doctype": doctype,
			**copy,
			"can_create": frappe.has_permission(doctype, "create"),
			"can_read": frappe.has_permission(doctype, "read"),
		}
		for doctype, copy in _AUXILIARY_FORM_DOCTYPES.items()
		if frappe.has_permission(doctype, "read")
	]


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record_list(doctype):
	"""List one approved supporting DocType through ordinary Frappe permissions."""
	_require_auxiliary_doctype(doctype, "read")
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field or (meta.autoname.removeprefix("field:") if str(meta.autoname or "").startswith("field:") else None)
	fields = ["name"] + ([title_field] if title_field and title_field != "name" else [])
	rows = frappe.get_list(doctype, fields=fields, order_by=f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}", limit_page_length=200)
	return [{"name": row.name, "label": row.get(title_field) or row.name} for row in rows]


@frappe.whitelist(methods=["GET"])
def get_auxiliary_record(doctype, name=None):
	"""Return one safe metadata contract plus values for create or edit."""
	_require_auxiliary_doctype(doctype, "read" if name else "create")
	contract = _auxiliary_form_contract(doctype)
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	if name:
		doc.check_permission("read")
	return {
		"contract": contract,
		"values": {field["name"]: doc.get(field["name"]) for section in contract["sections"] for field in section["fields"]},
		"tables": {table["name"]: [row.as_dict() for row in doc.get(table["name"])] for table in contract["tables"]},
	}


@frappe.whitelist(methods=["POST"])
def save_auxiliary_record(doctype, values, tables=None, name=None):
	"""Create or update only fields exposed by the approved auxiliary contract."""
	_require_auxiliary_doctype(doctype, "write" if name else "create")
	contract = _auxiliary_form_contract(doctype)
	allowed_values = {field["name"] for section in contract["sections"] for field in section["fields"] if not field["read_only"]}
	allowed_tables = {table["name"]: table for table in contract["tables"]}
	doc = frappe.get_doc(doctype, name) if name else frappe.new_doc(doctype)
	doc.check_permission("write" if name else "create")
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


def _require_auxiliary_doctype(doctype, permission):
	if permission == "read":
		_require_app_user()
	else:
		_require_roles("BulkBite Manager")
	if doctype not in _AUXILIARY_FORM_DOCTYPES:
		frappe.throw(_("{0} is not an approved BulkBite setup record.").format(doctype), frappe.PermissionError)
	if not frappe.has_permission(doctype, permission):
		frappe.throw(_("You do not have permission to {0} {1}.").format(permission, doctype), frappe.PermissionError)


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


@frappe.whitelist(methods=["POST"])
def create_production_run(payload=None):
	_require_roles("BulkBite Worker", "BulkBite Manager")
	data = _as_dict(payload)
	run = frappe.get_doc({"doctype": "BulkBite Production Run", **data})
	run.insert()
	return _serialize_run(run)


@frappe.whitelist(methods=["POST"])
def update_production_actuals(name, actual_output_qty, ingredients, notes=None):
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
	buying = load_buying_theory(plan, location)
	demand = calculate_customer_demand(plan.customer_mix)
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": plan.name},
		fields=["name", "production_plan_row", "plan_week_number", "cycle_number", "production_date", "docstatus", "planned_output_qty", "actual_output_qty", "creation", "modified"],
		order_by="production_date, creation",
	)
	result = {
		"name": plan.name,
		"plan_title": plan.plan_title,
		"status": plan.status,
		"period_start": plan.period_start,
		"period_end": plan.period_end,
		"date_note": plan.date_note,
		"location": location,
		"customer_demand": demand,
		"customer_mix": [{"plan_type": row.plan_type, "customer_count": row.customer_count, "serving_size_g": round_operational_quantity(row.serving_size_g), "weekly_servings": row.weekly_servings, "weekly_output_qty": round_operational_quantity(row.weekly_output_qty)} for row in plan.customer_mix],
		"purchase_routes": [{"item_category": row.item_category, "supplier": row.supplier, "use_discounted_price": row.use_discounted_price} for row in plan.purchase_routes],
		"rows": rows,
		"total_requirements": requirements,
		"buying": buying,
		"financial_summary": build_dashboard_financial_summary(demand, rows, plan.name),
		"workforce": get_employee_capacity_snapshot(demand),
		"runs": runs,
	}
	result["next_production"] = _next_production_station(result["rows"], runs)
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
	plan.notes = data.get("notes")
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
				"planned_output_qty": flt(row.get("planned_output_qty")),
				"uom": "Kg",
				"finished_item": row.get("finished_item") or frappe.get_cached_value("BulkBite Recipe", row.get("recipe"), "finished_item"),
			}
			for index, row in enumerate(rows, start=1)
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
def create_run_from_plan(plan_name, plan_row_name, production_date, source_location, target_location):
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
	return create_production_run(
		{
			"production_date": getdate(production_date),
			"business_name": plan.business_name,
			"production_plan": plan.name,
			"production_plan_row": plan_row.name,
			"plan_week_number": plan_row.week_number,
			"cycle_number": cycle_number,
			"recipe": plan_row.recipe,
			"planned_output_qty": plan_row.planned_output_qty,
			"actual_output_qty": plan_row.planned_output_qty,
			"source_location": source_location,
			"target_location": target_location,
			"notes": _("Created from production plan {0}, week {1}.").format(plan.name, plan_row.week_number),
		}
	)


def _next_production_station(rows, runs):
	"""Resume a draft or advance through the repeating meal direction."""
	ordered_rows = sorted(rows, key=lambda value: value.get("week_number") or 0)
	if not ordered_rows:
		return {"state": "empty", "row": None, "run": None, "cycle_number": 1}
	row_by_number = {int(row["week_number"]): row for row in ordered_rows}
	row_by_name = {row["name"]: row for row in ordered_rows}
	drafts = sorted(
		(row for row in runs if not row.docstatus),
		key=lambda value: (int(value.cycle_number or 1), int(value.plan_week_number or 0), value.creation),
	)
	if drafts:
		draft = drafts[0]
		week_number = int(draft.plan_week_number or 0)
		row = row_by_number.get(week_number) or row_by_name.get(draft.production_plan_row)
		if row:
			return {
				"state": "draft",
				"row": row,
				"run": _serialize_run(frappe.get_doc("BulkBite Production Run", draft.name)),
				"cycle_number": int(draft.cycle_number or 1),
			}
	posted = sorted(
		(row for row in runs if row.docstatus),
		key=lambda value: (int(value.cycle_number or 1), int(value.plan_week_number or 0), value.production_date, value.creation),
	)
	if not posted:
		return {"state": "ready", "row": ordered_rows[0], "run": None, "cycle_number": 1}
	latest = posted[-1]
	latest_week = int(latest.plan_week_number or 0)
	if not latest_week and latest.production_plan_row in row_by_name:
		latest_week = int(row_by_name[latest.production_plan_row]["week_number"])
	latest_week = latest_week or 1
	next_week = latest_week + 1 if latest_week < len(ordered_rows) else 1
	next_cycle = int(latest.cycle_number or 1) + (1 if next_week == 1 else 0)
	return {"state": "ready", "row": row_by_number[next_week], "run": None, "cycle_number": next_cycle}


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
	return enrich_spend_report(build_spend_report(start, end))


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
def apply_catalogue_price_workbook(batch_name):
	"""Apply an error-free reviewed price batch without creating stock or accounting entries."""
	_require_roles("BulkBite Manager")
	return apply_price_import(batch_name)


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
		"docstatus": run.docstatus,
		"production_date": run.production_date,
		"business_name": run.business_name,
		"production_plan": run.production_plan,
		"production_plan_row": run.production_plan_row,
		"plan_week_number": run.plan_week_number,
		"cycle_number": run.cycle_number,
		"recipe": run.recipe,
		"finished_item": run.finished_item,
		"planned_output_qty": round(flt(run.planned_output_qty), 3),
		"actual_output_qty": round(flt(run.actual_output_qty), 3),
		"output_variance_qty": round(flt(run.output_variance_qty), 3),
		"output_variance_percent": run.output_variance_percent,
		"expected_material_cost": run.expected_material_cost,
		"actual_material_cost": run.actual_material_cost,
		"material_cost_variance": run.material_cost_variance,
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
