from __future__ import annotations

import math
from datetime import timedelta

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from bulkbite.stock_production import get_available_stock, load_expected_usage, round_operational_quantity
from bulkbite.pricing import calculate_basket_adjustments, calculate_offer_price_bridge


# =============================================================================
# region CUSTOMER DEMAND
# =============================================================================


def calculate_customer_demand(customer_mix):
	"""Convert customer counts into weekly servings and cooked kilograms."""
	result = []
	total_customers = 0
	weekly_servings = 0
	weekly_output_qty = 0
	cycle_revenue = 0
	for row in customer_mix or []:
		plan = frappe.get_cached_doc("BulkBite Customer Plan Type", row.plan_type)
		customers = max(int(row.customer_count or 0), 0)
		servings = customers * int(plan.meals_per_day) * int(plan.days_per_week)
		output_qty = round_operational_quantity(servings * flt(plan.serving_size_g) / 1000)
		customer_price = flt(plan.discounted_price) if flt(plan.discounted_price) > 0 else flt(plan.normal_price)
		plan_revenue = round(customers * customer_price, 2)
		result.append(
			{
				"plan_type": row.plan_type,
				"customer_count": customers,
				"serving_size_g": flt(plan.serving_size_g),
				"weekly_servings": servings,
				"weekly_output_qty": output_qty,
				"customer_price": customer_price,
				"price_basis": "Discounted" if flt(plan.discounted_price) > 0 else "Normal",
				"cycle_weeks": int(plan.cycle_weeks or 4),
				"cycle_revenue": plan_revenue,
			}
		)
		total_customers += customers
		weekly_servings += servings
		weekly_output_qty += output_qty
		cycle_revenue += plan_revenue
	return {
		"mix": result,
		"total_customers": total_customers,
		"weekly_servings": weekly_servings,
		"weekly_output_qty": round_operational_quantity(weekly_output_qty),
		"cycle_revenue": round(cycle_revenue, 2),
	}


# endregion CUSTOMER DEMAND


# =============================================================================
# region DASHBOARD FINANCIAL POSITION
# =============================================================================


def build_dashboard_financial_summary(demand, plan_rows, plan_name=None, as_of_date=None):
	"""Build a clearly qualified four-week gross-profit position for the dashboard."""
	as_of = getdate(as_of_date or nowdate())
	actual_from = add_days(as_of, -27)
	runs = frappe.get_all(
		"BulkBite Production Run",
		filters={
			"production_date": ["between", [actual_from, as_of]],
			"production_plan": plan_name,
			"docstatus": 1,
			"stock_events_posted": 1,
		},
		fields=["name", "actual_material_cost"],
		order_by="production_date desc, creation desc",
		limit=4,
	)
	revenue = round(flt(demand.get("cycle_revenue")), 2)
	expected_cost = round(
		sum(
			flt(ingredient.get("required_qty")) * flt(ingredient.get("valuation_rate"))
			for row in plan_rows or []
			for ingredient in row.get("ingredients") or []
		),
		2,
	)
	actual_cost = round(sum(flt(run.actual_material_cost) for run in runs), 2)
	return {
		"currency": "ZAR",
		"cycle_weeks": 4,
		"as_of_date": as_of,
		"revenue": revenue,
		"revenue_basis": "Current customers at the configured normal or discounted plan price",
		"expected": _gross_profit_position(revenue, expected_cost),
		"actual": _gross_profit_position(revenue, actual_cost) if len(runs) == 4 else None,
		"actual_period": {"from_date": actual_from, "to_date": as_of},
		"actual_run_count": len(runs),
		"qualification": "Gross profit before overheads, labour, packaging, tax, and other non-food costs",
	}


def _gross_profit_position(revenue, food_cost):
	"""Calculate one comparable revenue, food-cost, gross-profit, and margin position."""
	gross_profit = round(flt(revenue) - flt(food_cost), 2)
	margin = round(gross_profit / flt(revenue) * 100, 1) if flt(revenue) else 0
	return {"food_cost": round(flt(food_cost), 2), "gross_profit": gross_profit, "margin_percent": margin}


# endregion DASHBOARD FINANCIAL POSITION


# =============================================================================
# region MONTHLY REQUIREMENTS
# =============================================================================


def build_plan_snapshot(plan, location="Ingredients", weeks=4, cover_with_finished_stock=False, finished_location="Finished Meals", start_cycle_week=1):
	"""Expand the meal cycle and optionally cover output demand with finished stock before ingredients."""
	weeks = max(int(weeks or 4), 1)
	rows = []
	aggregated = {}
	ordered_rows = sorted(plan.plan_rows, key=lambda value: int(value.week_number or 0))
	if not ordered_rows:
		return rows, []
	finished_balances = {}
	start_index = max(int(start_cycle_week or 1) - 1, 0) % len(ordered_rows)
	for horizon_week in range(1, weeks + 1):
		plan_row = ordered_rows[(start_index + horizon_week - 1) % len(ordered_rows)]
		planned_output = round_operational_quantity(plan_row.planned_output_qty)
		finished_item = plan_row.finished_item
		if cover_with_finished_stock and finished_item not in finished_balances:
			finished_balances[finished_item] = round_operational_quantity(get_available_stock(finished_item, finished_location))
		finished_available = finished_balances.get(finished_item, 0) if cover_with_finished_stock else 0
		finished_coverage = round_operational_quantity(min(planned_output, max(finished_available, 0)))
		production_required = round_operational_quantity(max(planned_output - finished_coverage, 0))
		if cover_with_finished_stock:
			finished_balances[finished_item] = round_operational_quantity(finished_available - finished_coverage)
		expectation = load_expected_usage(plan_row.recipe, production_required, location) if production_required > 0 else {"ingredients": []}
		ingredients = []
		for ingredient in expectation["ingredients"]:
			required = round_operational_quantity(ingredient["expected_qty"])
			item = frappe.get_cached_doc("BulkBite Item", ingredient["item_code"])
			line = {
				**ingredient,
				"available_qty": round_operational_quantity(ingredient["available_before_measurement"]),
				"required_qty": required,
				"item_category": item.item_category,
				"purchasable": bool(item.purchasable),
			}
			ingredients.append(line)
			total = aggregated.setdefault(
				ingredient["item_code"],
				{
					"item_code": ingredient["item_code"],
					"item_name": ingredient["item_name"],
					"item_category": item.item_category,
					"purchasable": bool(item.purchasable),
					"uom": ingredient["uom"],
					"required_qty": 0,
				},
			)
			total["required_qty"] = round_operational_quantity(total["required_qty"] + required)
		rows.append(
			{
				"name": plan_row.name,
				"week_number": horizon_week,
				"cycle_week": plan_row.week_number,
				"planned_date": plan_row.planned_date,
				"finished_item": finished_item,
				"finished_item_name": frappe.get_cached_value("BulkBite Item", finished_item, "item_name"),
				"recipe": plan_row.recipe,
				"weekly_servings": plan_row.weekly_servings,
				"planned_output_qty": planned_output,
				"customer_required_output_qty": round_operational_quantity(getattr(plan_row, "customer_required_output_qty", 0) or planned_output),
				"extra_output_qty": round_operational_quantity(getattr(plan_row, "extra_output_qty", 0)),
				"extra_allocation_type": getattr(plan_row, "extra_allocation_type", None),
				"extra_allocation_reference": getattr(plan_row, "extra_allocation_reference", None),
				"finished_stock_coverage_qty": finished_coverage,
				"production_required_qty": production_required,
				"finished_stock_closing_qty": round_operational_quantity(finished_balances.get(finished_item, 0)) if cover_with_finished_stock else 0,
				"uom": plan_row.uom,
				"ingredients": ingredients,
			}
		)
	for item in aggregated.values():
		item["available_qty"] = round_operational_quantity(get_available_stock(item["item_code"], location))
		item["shortage_qty"] = round_operational_quantity(max(item["required_qty"] - item["available_qty"], 0))
	return rows, sorted(aggregated.values(), key=lambda item: item["item_name"])


# endregion MONTHLY REQUIREMENTS


# =============================================================================
# region BUYING PLAN
# =============================================================================


def build_buying_plan(plan, requirements, as_of_date=None, horizon_weeks=4, next_production=None):
	"""Round ingredient shortages to chosen supplier packs and price the theoretical basket."""
	as_of_date = getdate(as_of_date or nowdate())
	production_date = _next_planned_production_date(plan, as_of_date, next_production)
	routes = {row.item_category: row for row in plan.purchase_routes}
	lines = []
	for item in requirements:
		if not item.get("purchasable"):
			continue
		route = routes.get(item["item_category"])
		supplier = route.supplier if route else None
		if not supplier and item.get("item_category"):
			supplier = frappe.get_cached_value("BulkBite Item Category", item["item_category"], "default_supplier")
		offer = _select_offer(item["item_code"], supplier, bool(route and route.use_discounted_price), as_of_date)
		line = {**item, "supplier": supplier, "offer": offer, "quantity_basis": "Raw purchase quantity"}
		if offer and item["shortage_qty"] > 0:
			packs = math.ceil(item["shortage_qty"] / offer["stock_qty_per_pack"])
			price_bridge = calculate_offer_price_bridge(offer, packs, as_of_date, bool(route and route.use_discounted_price))
			line.update(
				{
					"packs_to_buy": packs,
					"purchase_qty": round_operational_quantity(packs * offer["stock_qty_per_pack"]),
					"surplus_qty": round_operational_quantity(packs * offer["stock_qty_per_pack"] - item["shortage_qty"]),
					"base_cost": price_bridge["base_subtotal"],
					"expected_savings": price_bridge["savings"],
					"expected_added_costs": price_bridge["added_costs"] + price_bridge["vat_added"],
					"expected_cost": price_bridge["landed_cost"],
					"price_bridge": price_bridge,
				}
			)
		else:
			line.update({"packs_to_buy": 0, "purchase_qty": 0, "surplus_qty": 0, "base_cost": 0, "expected_savings": 0, "expected_added_costs": 0, "expected_cost": 0, "price_bridge": None})
		lines.append(line)
	groups = {}
	for line in lines:
		if flt(line.get("shortage_qty")) <= 0:
			continue
		key = line["supplier"] or "Supplier not chosen"
		group = groups.setdefault(key, {"supplier": key, "base_cost": 0, "expected_savings": 0, "expected_added_costs": 0, "expected_cost": 0, "items": []})
		group["base_cost"] += line["base_cost"]
		group["expected_savings"] += line["expected_savings"]
		group["expected_added_costs"] += line["expected_added_costs"]
		group["expected_cost"] += line["expected_cost"]
		group["items"].append(line)
	for group in groups.values():
		group.update(_supplier_order_deadline(plan, group["supplier"], as_of_date, production_date))
		basket_bridge = calculate_basket_adjustments(group["supplier"], group["base_cost"], as_of_date)
		group["basket_adjustments"] = basket_bridge
		group["expected_savings"] += basket_bridge["savings"]
		group["expected_added_costs"] += basket_bridge["added_costs"]
		group["expected_cost"] += basket_bridge["net_adjustment"]
		group.update(_delivery_threshold_recommendation(group["supplier"], group["base_cost"], as_of_date, group["items"], horizon_weeks))
		group.update(_supplier_minimum_position(group["supplier"], group["base_cost"], as_of_date))
	missing_offers = sum(1 for row in lines if row["shortage_qty"] > 0 and not row["offer"])
	return {
		"lines": lines,
		"suppliers": list(groups.values()),
		"base_cost": sum(group["base_cost"] for group in groups.values()),
		"expected_savings": sum(group["expected_savings"] for group in groups.values()),
		"expected_added_costs": sum(group["expected_added_costs"] for group in groups.values()),
		"expected_cost": sum(group["expected_cost"] for group in groups.values()),
		"shortage_count": sum(1 for row in lines if row["shortage_qty"] > 0),
		"missing_offer_count": missing_offers,
		"horizon_weeks": max(int(horizon_weeks or 4), 1),
		"as_of_date": as_of_date,
		"production_date": production_date,
		"all_stock_covered": not any(flt(row.get("shortage_qty")) > 0 for row in lines),
	}


def _supplier_order_deadline(plan, supplier, as_of_date, production_date=None):
	"""Return the production, customer handoff, and supplier order-by dates."""
	production_date = getdate(production_date or _next_planned_production_date(plan, as_of_date))
	delivery_date = production_date + timedelta(days=(6 - production_date.weekday()) % 7)
	if supplier == "Supplier not chosen":
		return {"production_date": production_date, "customer_delivery_date": delivery_date, "order_by_date": None, "lead_time_days": 0, "safety_days": 0}
	settings = frappe.db.get_value("BulkBite Supplier", supplier, ["delivery_lead_time_days", "order_safety_days"], as_dict=True) or frappe._dict()
	lead_time = max(int(settings.delivery_lead_time_days or 0), 0)
	safety_days = max(int(settings.order_safety_days or 0), 0)
	return {
		"production_date": production_date,
		"customer_delivery_date": delivery_date,
		"order_by_date": production_date - timedelta(days=lead_time + safety_days),
		"lead_time_days": lead_time,
		"safety_days": safety_days,
	}


def _next_planned_production_date(plan, as_of_date, next_production=None):
	"""Resolve the first saved cooking session which can still happen on or after today."""
	as_of = getdate(as_of_date or nowdate())
	weekday_index = {name: index for index, name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])}
	next_row = (next_production or {}).get("row") or {}
	target_week = int(next_row.get("cycle_week") or next_row.get("week_number") or 0)
	candidates = []
	for run in plan.capacity_runs or []:
		week = max(int(run.week_number or 1), 1)
		if target_week and week != target_week:
			continue
		weekday = weekday_index.get(run.day_of_week or "Saturday", 5)
		candidate = as_of + timedelta(days=(weekday - as_of.weekday()) % 7)
		candidates.append(candidate)
	return min(candidates) if candidates else _next_cycle_date(plan, "Saturday", as_of)


def _next_cycle_date(plan, weekday_name, as_of_date):
	"""Resolve the next named weekday on or after the advisory calculation date."""
	start = getdate(as_of_date or plan.period_start or nowdate())
	target = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(weekday_name)
	return start + timedelta(days=(target - start.weekday()) % 7)


def _supplier_minimum_position(supplier, basket_subtotal, as_of_date):
	"""Return the supplier's active order threshold without turning it into a purchase."""
	rules = frappe.get_all(
		"BulkBite Price Adjustment",
		filters={"enabled": 1, "supplier": supplier, "scope_type": ["in", ["Supplier", "Basket"]]},
		fields=["adjustment_type", "threshold_amount", "effective_from", "effective_to"],
	)
	active = [
		row for row in rules
		if row.adjustment_type == "Minimum Order"
		and flt(row.threshold_amount) > 0
		and (not row.effective_from or getdate(row.effective_from) <= as_of_date)
		and (not row.effective_to or getdate(row.effective_to) >= as_of_date)
	]
	minimum = max((flt(row.threshold_amount) for row in active), default=0)
	gap = round(max(minimum - flt(basket_subtotal), 0), 2)
	return {
		"supplier_order_minimum": round(minimum, 2),
		"supplier_order_minimum_gap": gap,
		"supplier_order_minimum_met": bool(minimum and not gap),
	}


def _delivery_threshold_recommendation(supplier, basket_subtotal, as_of_date, basket_items=None, horizon_weeks=4):
	"""Model one safe extra pack when it costs less than delivery and respects holding limits."""
	rules = frappe.get_all(
		"BulkBite Price Adjustment",
		filters={"enabled": 1, "supplier": supplier, "adjustment_type": ["in", ["Delivery Fee", "Free Delivery"]]},
		fields=["name", "adjustment_name", "adjustment_type", "value", "threshold_amount", "effective_from", "effective_to"],
		order_by="priority asc, name asc",
	)
	active = [row for row in rules if (not row.effective_from or getdate(row.effective_from) <= as_of_date) and (not row.effective_to or getdate(row.effective_to) >= as_of_date)]
	threshold = max((flt(row.threshold_amount) for row in active if flt(row.threshold_amount) > 0), default=0)
	delivery_fee = max((flt(row.value) for row in active if row.adjustment_type == "Delivery Fee"), default=0)
	gap = round(max(threshold - flt(basket_subtotal), 0), 2)
	candidates = _pull_forward_candidates(supplier, basket_items or [], as_of_date, horizon_weeks, gap, delivery_fee)
	selected = candidates[0] if candidates else None
	return {
		"delivery_threshold": round(threshold, 2),
		"delivery_fee_below_threshold": round(delivery_fee, 2),
		"threshold_gap": gap,
		"threshold_status": "reached" if threshold and not gap else "below" if threshold else "not_configured",
		"pull_forward_candidates": candidates,
		"recommended_pull_forward_cost": selected["expected_cost"] if selected else 0,
		"estimated_delivery_saving": round(max(delivery_fee - flt(selected["expected_cost"]), 0), 2) if selected else 0,
		"pull_forward_recommendation": (
			f"Add one extra pack of {selected['item_name']} for about R {selected['expected_cost']:.2f}. This reaches the threshold and is about R {max(delivery_fee - selected['expected_cost'], 0):.2f} cheaper than delivery."
			if selected else
			f"The basket is R {gap:.2f} below the free-delivery threshold. Paying delivery may use less cash than adding stock."
			if gap and delivery_fee else
			"The current basket reaches the configured delivery threshold." if threshold else
			"No delivery threshold is configured for this supplier."
		),
	}


def _pull_forward_candidates(supplier, basket_items, as_of_date, horizon_weeks, threshold_gap, delivery_fee):
	"""Return extra-pack options whose cost, shelf life, and stock ceiling make them safe."""
	if not supplier or threshold_gap <= 0 or delivery_fee <= 0:
		return []
	candidates = []
	for basket_item in basket_items:
		item = frappe.get_cached_doc("BulkBite Item", basket_item["item_code"])
		if not item.pull_forward_allowed or int(item.shelf_life_days or 0) < max(int(horizon_weeks or 1) * 7, 1):
			continue
		maximum = flt(item.maximum_preferred_stock_qty)
		if maximum <= 0:
			continue
		offer = basket_item.get("offer") or _select_offer(item.name, supplier, True, as_of_date)
		if not offer:
			continue
		projected = flt(basket_item.get("available_qty")) + flt(basket_item.get("purchase_qty"))
		extra_qty = flt(offer["stock_qty_per_pack"])
		if projected + extra_qty > maximum:
			continue
		bridge = calculate_offer_price_bridge(offer, 1, as_of_date, True)
		extra_cost = round(flt(bridge["landed_cost"]), 2)
		if extra_cost < threshold_gap or extra_cost >= delivery_fee:
			continue
		candidates.append({
			"item_code": item.name,
			"item_name": item.item_name,
			"packs": 1,
			"purchase_qty": round_operational_quantity(extra_qty),
			"uom": item.stock_uom,
			"expected_cost": extra_cost,
			"projected_stock_qty": round_operational_quantity(projected + extra_qty),
			"maximum_preferred_stock_qty": round_operational_quantity(maximum),
			"shelf_life_days": int(item.shelf_life_days or 0),
		})
	return sorted(candidates, key=lambda row: (row["expected_cost"], row["item_name"]))


def load_buying_theory(plan, location="Ingredients"):
	"""Return the immutable buying theory saved with a plan, or calculate legacy theory."""
	if plan.buying_snapshot_json:
		return _normalize_buying_theory(frappe.parse_json(plan.buying_snapshot_json))
	_rows, requirements = build_plan_snapshot(plan, location)
	return build_buying_plan(plan, requirements)


def _normalize_buying_theory(buying):
	"""Remove binary floating-point tails from a frozen buying snapshot."""
	quantity_fields = {"available_qty", "required_qty", "shortage_qty", "purchase_qty", "surplus_qty"}
	for line in buying.get("lines") or []:
		for field in quantity_fields:
			if line.get(field) is not None:
				line[field] = round_operational_quantity(line[field])
	for group in buying.get("suppliers") or []:
		for line in group.get("items") or []:
			for field in quantity_fields:
				if line.get(field) is not None:
					line[field] = round_operational_quantity(line[field])
	return buying


def freeze_buying_theory(plan, location="Ingredients"):
	"""Freeze the supplier basket produced by the current plan and current stock position."""
	_rows, requirements = build_plan_snapshot(plan, location)
	buying = build_buying_plan(plan, requirements)
	plan.db_set(
		{
			"expected_purchase_cost": flt(buying["expected_cost"]),
			"buying_snapshot_json": frappe.as_json(buying),
		},
		update_modified=False,
	)
	return buying


def build_spend_report(from_date, to_date):
	"""Compare frozen plan baskets with every reviewed receipt in a reporting period."""
	start, end = getdate(from_date), getdate(to_date)
	plans = frappe.get_all(
		"BulkBite Production Plan",
		filters={
			"period_start": ["<=", end],
			"period_end": [">=", start],
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "plan_title", "period_start", "period_end", "expected_purchase_cost", "buying_snapshot_json"],
		order_by="period_start asc, name asc",
	)
	breakdown = {}
	savings_breakdown = {}
	expected_base_total = 0
	expected_savings_total = 0
	expected_added_costs_total = 0
	plan_rows = []
	for plan_row in plans:
		plan = frappe.get_doc("BulkBite Production Plan", plan_row.name)
		buying = load_buying_theory(plan)
		expected = flt(buying.get("expected_cost"))
		expected_base_total += flt(buying.get("base_cost")) or expected
		expected_savings_total += flt(buying.get("expected_savings"))
		expected_added_costs_total += flt(buying.get("expected_added_costs"))
		plan_rows.append(
			{
				"name": plan.name,
				"plan_title": plan.plan_title,
				"period_start": plan.period_start,
				"period_end": plan.period_end,
				"expected_spend": expected,
				"actual_spend": 0,
				"variance": -expected,
			}
		)
		for line in buying.get("lines") or []:
			_add_spend_breakdown(
				breakdown,
				line.get("supplier") or "Supplier not chosen",
				line.get("item_category") or "Uncategorised",
				expected=flt(line.get("expected_cost")),
			)
			for component in (line.get("price_bridge") or {}).get("components") or []:
				_add_savings_breakdown(savings_breakdown, line.get("supplier"), component)
		for group in buying.get("suppliers") or []:
			for component in (group.get("basket_adjustments") or {}).get("components") or []:
				_add_savings_breakdown(savings_breakdown, group.get("supplier"), component)

	receipts = frappe.get_all(
		"BulkBite Receipt Intake",
		filters={"invoice_date": ["between", [start, end]], "status": ["!=", "Rejected"]},
		fields=["name", "invoice_date", "supplier", "subtotal_amount", "tax_amount", "total_amount"],
		order_by="invoice_date asc, name asc",
	)
	plan_by_name = {row["name"]: row for row in plan_rows}
	unassigned_receipts = 0
	actual_total = 0
	if receipts:
		items = {
			row.item_code: row.item_category or "Uncategorised"
			for row in frappe.get_all("BulkBite Item", fields=["item_code", "item_category"])
		}
		for receipt in receipts:
			actual_total += flt(receipt.total_amount)
			matching_plans = [
				row for row in plan_rows
				if getdate(row["period_start"]) <= getdate(receipt.invoice_date) <= getdate(row["period_end"])
			]
			if len(matching_plans) == 1:
				matching_plans[0]["actual_spend"] += flt(receipt.total_amount)
			else:
				unassigned_receipts += 1
			for line in frappe.get_all(
				"BulkBite Receipt Line",
				filters={"parenttype": "BulkBite Receipt Intake", "parent": receipt.name},
				fields=["item_code", "amount"],
			):
				_add_spend_breakdown(
					breakdown,
					receipt.supplier or "Supplier not recorded",
					items.get(line.item_code, "Uncategorised"),
					actual=flt(line.amount),
				)
			if flt(receipt.tax_amount):
				_add_spend_breakdown(
					breakdown,
					receipt.supplier or "Supplier not recorded",
					"VAT and tax",
					actual=flt(receipt.tax_amount),
				)
			for adjustment in frappe.get_all(
				"BulkBite Receipt Adjustment",
				filters={"parenttype": "BulkBite Receipt Intake", "parent": receipt.name},
				fields=["adjustment_type", "description", "effect", "amount"],
			):
				adjustment_amount = flt(adjustment.amount)
				is_saving = adjustment.effect == "Saving"
				_add_spend_breakdown(
					breakdown,
					receipt.supplier or "Supplier not recorded",
					"Receipt savings" if is_saving else "Delivery and buying costs",
					actual=-adjustment_amount if is_saving else adjustment_amount,
				)
				key = (adjustment.description or adjustment.adjustment_type, adjustment.adjustment_type, adjustment.effect.lower())
				row = savings_breakdown.setdefault(key, {"name": key[0], "type": key[1], "effect": key[2], "expected_amount": 0, "actual_amount": 0, "suppliers": []})
				row["actual_amount"] += adjustment_amount
				if receipt.supplier and receipt.supplier not in row["suppliers"]:
					row["suppliers"].append(receipt.supplier)

	for row in plan_rows:
		row["variance"] = row["actual_spend"] - row["expected_spend"]
	expected_total = sum(flt(row["expected_spend"]) for row in plan_rows)
	rows = sorted(breakdown.values(), key=lambda row: (row["supplier"], row["item_category"]))
	for row in rows:
		row["variance"] = row["actual_spend"] - row["expected_spend"]
	savings_rows = sorted(savings_breakdown.values(), key=lambda row: (row["effect"], row["name"]))
	return {
		"period": {"from_date": start, "to_date": end, "currency": "ZAR"},
		"summary": {
			"expected_base_spend": expected_base_total,
			"expected_savings": expected_savings_total,
			"expected_added_buying_costs": expected_added_costs_total,
			"expected_spend": expected_total,
			"actual_spend": actual_total,
			"variance": actual_total - expected_total,
			"plan_count": len(plan_rows),
			"receipt_count": len(receipts),
			"unassigned_receipt_count": unassigned_receipts,
		},
		"plans": plan_rows,
		"breakdown": rows,
		"savings": savings_rows,
		"savings_by_type": _summarize_savings_by_type(savings_rows),
	}


def _add_spend_breakdown(target, supplier, item_category, expected=0, actual=0):
	key = (supplier, item_category)
	row = target.setdefault(
		key,
		{
			"supplier": supplier,
			"item_category": item_category,
			"expected_spend": 0,
			"actual_spend": 0,
		},
	)
	row["expected_spend"] += flt(expected)
	row["actual_spend"] += flt(actual)


def _add_savings_breakdown(target, supplier, component):
	key = (component.get("name"), component.get("type"), component.get("effect"))
	row = target.setdefault(key, {"name": component.get("name"), "type": component.get("type"), "effect": component.get("effect"), "expected_amount": 0, "actual_amount": 0, "suppliers": []})
	row["expected_amount"] += flt(component.get("amount"))
	if supplier and supplier not in row["suppliers"]:
		row["suppliers"].append(supplier)


def _summarize_savings_by_type(rows):
	"""Group exact evidence rows by adjustment type without discarding their source names."""
	summary = {}
	for row in rows:
		key = (row.get("type") or "Other", row.get("effect") or "saving")
		group = summary.setdefault(
			key,
			{
				"type": key[0],
				"effect": key[1],
				"expected_amount": 0,
				"actual_amount": 0,
				"evidence_count": 0,
			},
		)
		group["expected_amount"] += flt(row.get("expected_amount"))
		group["actual_amount"] += flt(row.get("actual_amount"))
		group["evidence_count"] += 1
	return sorted(summary.values(), key=lambda row: (row["effect"], row["type"]))


def _select_offer(item_code, supplier, use_discounted_price, as_of_date):
	if not supplier:
		return None
	offers = frappe.get_all(
		"BulkBite Supplier Offer",
		filters={"item_code": item_code, "supplier": supplier, "enabled": 1},
		fields=["name", "item_code", "supplier", "supplier_item_code", "effective_from", "effective_to", "units_per_pack", "unit_size", "purchase_uom", "stock_qty_per_pack", "normal_price", "discounted_price", "discount_from", "discount_to", "currency", "price_includes_vat", "vat_rate", "preferred"],
		order_by="effective_from desc, preferred desc, creation desc",
	)
	offers = [
		offer for offer in offers
		if (not offer.effective_from or getdate(offer.effective_from) <= as_of_date)
		and (not offer.effective_to or getdate(offer.effective_to) >= as_of_date)
	]
	if not offers:
		return None
	offer = offers[0]
	discount_active = bool(
		use_discounted_price
		and flt(offer.discounted_price) > 0
		and (not offer.discount_from or getdate(offer.discount_from) <= as_of_date)
		and (not offer.discount_to or getdate(offer.discount_to) >= as_of_date)
	)
	offer["discount_active"] = discount_active
	bridge = calculate_offer_price_bridge(offer, 1, as_of_date, use_discounted_price)
	offer["selected_price"] = bridge["landed_pack_price"]
	offer["base_price"] = bridge["base_pack_price"]
	offer["price_bridge"] = bridge
	return offer


# endregion BUYING PLAN
