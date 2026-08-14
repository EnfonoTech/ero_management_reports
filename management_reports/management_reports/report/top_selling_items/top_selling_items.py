import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Count
from frappe.utils import cint

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.query import (
	CHART_COLORS,
	add_profit_columns,
	base_query,
	cogs_available,
	cogs_expression,
	currency_label,
	rounded_sum,
	set_derived_profit,
)

DEFAULT_LIMIT = 50


def execute(filters=None):
	check_access()
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data, filters)
	return columns, data, None, chart, report_summary


def get_columns(filters):
	currency = get_currency((filters or {}).get("company"))

	columns = [
		{"label": _("Rank"), "fieldname": "rank", "fieldtype": "Int", "width": 60},
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 150,
		},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
		{"label": _("Qty Sold"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 80},
		{
			"label": currency_label("Revenue", currency),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]

	return add_profit_columns(columns, currency, profit_label=currency_label("Profit", currency))


def get_data(filters):
	filters = frappe._dict(filters or {})
	ctx = base_query(filters)
	currency = get_currency(filters.get("company"))
	limit = cint(filters.get("limit")) or DEFAULT_LIMIT

	query = ctx.query
	if filters.get("item_group"):
		query = query.where(ctx.SII.item_group == filters.item_group)

	selects = [
		ctx.SII.item_code,
		ctx.SII.item_name,
		ctx.SII.item_group,
		ctx.SII.stock_uom.as_("uom"),
		rounded_sum(ctx.SII.qty).as_("qty"),
		Count(ctx.SII.parent).distinct().as_("invoices"),
		rounded_sum(ctx.SII.amount).as_("revenue"),
	]

	cogs = cogs_expression(ctx.SII)
	if cogs is not None:
		selects.append(cogs.as_("cogs"))

	data = (
		query.select(*selects)
		.groupby(ctx.SII.item_code, ctx.SII.item_name, ctx.SII.item_group, ctx.SII.stock_uom)
		.orderby(rounded_sum(ctx.SII.amount), order=Order.desc)
		.limit(limit)
		.run(as_dict=True)
	)

	for index, row in enumerate(data, 1):
		row["rank"] = index
		row["currency"] = currency
		if cogs is not None:
			set_derived_profit(row)

	return data


def get_chart(data):
	if not data:
		return None

	top_10 = data[:10]
	datasets = [{"name": _("Revenue"), "values": [row.get("revenue") or 0 for row in top_10]}]

	if cogs_available():
		datasets.append({"name": _("Profit"), "values": [row.get("profit") or 0 for row in top_10]})

	return {
		"data": {
			"labels": [(row.get("item_name") or row.get("item_code") or "")[:20] for row in top_10],
			"datasets": datasets,
		},
		"type": "bar",
		"colors": list(CHART_COLORS[: len(datasets)]),
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_revenue = sum(row.get("revenue") or 0 for row in data)
	total_profit = sum(row.get("profit") or 0 for row in data)
	total_qty = sum(row.get("qty") or 0 for row in data)
	avg_margin = (total_profit / total_revenue * 100) if total_revenue else 0

	summary = [
		{
			"value": total_revenue,
			"label": _("Total Revenue"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		}
	]

	if cogs_available():
		summary.append(
			{
				"value": total_profit,
				"label": _("Total Profit"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Green" if total_profit >= 0 else "Red",
			}
		)

	summary.append(
		{"value": total_qty, "label": _("Total Qty Sold"), "datatype": "Float", "indicator": "Blue"}
	)

	if cogs_available():
		summary.append(
			{
				"value": avg_margin,
				"label": _("Avg Margin"),
				"datatype": "Percent",
				"indicator": "Green" if avg_margin >= 30 else "Orange",
			}
		)

	return summary
