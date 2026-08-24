from __future__ import annotations

import frappe


# =============================================================================
# region PRODUCTION RUN SEQUENCE MIGRATION
# =============================================================================


def execute():
	"""Backfill repeating meal slots and cycle numbers on legacy production runs."""
	if not frappe.db.table_exists("BulkBite Production Run"):
		return
	if not frappe.db.has_column("BulkBite Production Run", "plan_week_number"):
		return

	for plan_name in frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": ("is", "set")},
		pluck="production_plan",
		distinct=True,
	):
		_backfill_plan_runs(plan_name)


def _backfill_plan_runs(plan_name):
	"""Assign one stable slot and cycle sequence within a single meal direction."""
	week_by_row = {
		row.name: int(row.week_number or 0)
		for row in frappe.get_all(
			"BulkBite Production Plan Row",
			filters={"parent": plan_name, "parenttype": "BulkBite Production Plan"},
			fields=["name", "week_number"],
		)
	}
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={"production_plan": plan_name},
		fields=["name", "production_plan_row", "plan_week_number", "production_date", "creation"],
		order_by="production_date asc, creation asc",
	)
	cycle_number = 1
	previous_week = 0
	for run in runs:
		week_number = int(run.plan_week_number or week_by_row.get(run.production_plan_row) or 0)
		if not week_number:
			continue
		if previous_week and week_number <= previous_week:
			cycle_number += 1
		frappe.db.set_value(
			"BulkBite Production Run",
			run.name,
			{"plan_week_number": week_number, "cycle_number": cycle_number},
			update_modified=False,
		)
		previous_week = week_number


# endregion PRODUCTION RUN SEQUENCE MIGRATION
