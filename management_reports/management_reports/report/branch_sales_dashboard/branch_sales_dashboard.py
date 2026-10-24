from frappe import _
from frappe.query_builder import Order
from frappe.utils import flt

from management_reports.management_reports.permissions import check_access
from management_reports.utils.config import (
	get_branch_display_names,
	get_branch_targets,
	period_months,
)
from management_reports.utils.currency import get_company_abbr, get_currency, strip_abbr
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import (
	CHART_COLORS,
	add_profit_columns,
	cogs_available,
	ctx_cogs,
	currency_label,
	customer_count,
	format_month_key,
	invoice_count,
	month_key_column,
	rounded_sum,
	set_derived_profit,
)
from management_reports.utils.sources import collect, count_distinct, has_extra_sources


def execute(filters=None):
	check_access()
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(filters)
	report_summary = get_report_summary(data, filters)
	return columns, data, None, chart, report_summary


def get_columns(filters):
	currency = get_currency((filters or {}).get("company"))
	branch = get_branch_dimension()

	columns = [
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 200,
		},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 100},
		{"label": _("Customers"), "fieldname": "customers", "fieldtype": "Int", "width": 100},
		{
			"label": currency_label("Revenue", currency),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]

	columns = add_profit_columns(columns, currency, profit_label=currency_label("Gross Profit", currency))

	# Target columns appear only once somebody has configured targets, so a site
	# with no Management Report Config sees exactly the report it saw before.
	if get_branch_targets((filters or {}).get("company")):
		columns.append(
			{
				"label": currency_label("Target", currency),
				"fieldname": "target",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 140,
			}
		)
		columns.append(
			{
				"label": _("Achieved %"),
				"fieldname": "achieved",
				"fieldtype": "Percent",
				"width": 110,
			}
		)

	return columns


def get_data(filters):
	currency = get_currency((filters or {}).get("company"))
	cogs = cogs_available()

	def build(ctx):
		selects = [
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			customer_count(ctx).as_("customers"),
			rounded_sum(ctx.amount).as_("revenue"),
		]

		if cogs:
			selects.append(ctx_cogs(ctx).as_("cogs"))

		return (
			ctx.query.select(*selects)
			.groupby(ctx.branch_column)
			.orderby(rounded_sum(ctx.amount), order=Order.desc)
			.run(as_dict=True)
		)

	data = collect(
		filters,
		build,
		keys=("branch",),
		sums=("invoices", "customers", "revenue", "cogs"),
		sort=lambda row: row.get("revenue") or 0,
		reverse=True,
	)

	if has_extra_sources():
		# Summed per-source customer counts would count one customer twice.
		customers = count_distinct(filters, lambda ctx: ctx.customer, group=lambda ctx: ctx.branch_column)
		for row in data:
			row["customers"] = customers.get(row.get("branch"), 0)

	filters = filters or {}
	targets = get_branch_targets(filters.get("company"))
	# Targets are entered per month; scale them to whatever range is filtered so
	# a quarter reads ~100% rather than ~300%.
	months = period_months(filters.get("from_date"), filters.get("to_date")) if targets else 0

	for row in data:
		row["currency"] = currency
		if cogs:
			set_derived_profit(row)

		target = flt(targets.get(row.get("branch"))) * months
		if target:
			row["target"] = target
			row["achieved"] = (flt(row.get("revenue")) / target) * 100

	return data


def get_chart(filters):
	abbr = get_company_abbr((filters or {}).get("company"))

	def build(ctx):
		month_key = month_key_column(ctx)
		return (
			ctx.query.select(
				ctx.branch_column.as_("branch"),
				month_key.as_("month_key"),
				rounded_sum(ctx.amount).as_("revenue"),
			)
			.groupby(ctx.branch_column, month_key)
			.orderby(month_key)
			.run(as_dict=True)
		)

	monthly = collect(
		filters,
		build,
		keys=("branch", "month_key"),
		sums=("revenue",),
		sort=lambda row: row.get("month_key") or "",
	)

	if not monthly:
		return None

	months = sorted({row["month_key"] for row in monthly})
	branches = sorted({row["branch"] for row in monthly if row["branch"]})
	lookup = {(row["branch"], row["month_key"]): row["revenue"] for row in monthly}

	# A configured display name wins; otherwise fall back to stripping the
	# company abbreviation ERPNext appends to Cost Center names.
	names = get_branch_display_names((filters or {}).get("company"))
	datasets = [
		{
			"name": names.get(branch) or strip_abbr(branch, abbr),
			"values": [lookup.get((branch, month), 0) for month in months],
		}
		for branch in branches
	]

	return {
		"data": {"labels": [format_month_key(month) for month in months], "datasets": datasets},
		"type": "bar",
		"colors": list(CHART_COLORS[: len(branches)]),
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_revenue = sum(row.get("revenue") or 0 for row in data)
	total_invoices = sum(row.get("invoices") or 0 for row in data)

	total_profit = sum(row.get("profit") or 0 for row in data)
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
		{"value": total_invoices, "label": _("Total Invoices"), "datatype": "Int", "indicator": "Blue"}
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
