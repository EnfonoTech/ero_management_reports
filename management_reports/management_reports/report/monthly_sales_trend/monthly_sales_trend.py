from frappe import _

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_company_abbr, get_currency, strip_abbr
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import (
	CHART_COLORS,
	add_profit_columns,
	base_query,
	cogs_available,
	cogs_expression,
	currency_label,
	format_month_key,
	invoice_count,
	month_key_column,
	rounded_sum,
	set_derived_profit,
)


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
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 120},
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 180,
		},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{
			"label": currency_label("Revenue", currency),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]

	columns = add_profit_columns(columns, currency, profit_label=currency_label("Profit", currency))
	columns.append(
		{"label": _("Revenue Growth %"), "fieldname": "growth", "fieldtype": "Percent", "width": 130}
	)

	return columns


def get_data(filters):
	ctx = base_query(filters)
	currency = get_currency((filters or {}).get("company"))
	month_key = month_key_column(ctx.SI)

	selects = [
		month_key.as_("month_key"),
		ctx.branch_column.as_("branch"),
		invoice_count(ctx.SI).as_("invoices"),
		rounded_sum(ctx.SII.amount).as_("revenue"),
	]

	cogs = cogs_expression(ctx.SII)
	if cogs is not None:
		selects.append(cogs.as_("cogs"))

	data = (
		ctx.query.select(*selects)
		.groupby(month_key, ctx.branch_column)
		.orderby(month_key, ctx.branch_column)
		.run(as_dict=True)
	)

	previous_revenue = {}
	for row in data:
		row["currency"] = currency
		row["month"] = format_month_key(row.get("month_key"))
		if cogs is not None:
			set_derived_profit(row)

		# Growth is month-over-month within the same branch, so each branch
		# carries its own running previous value.
		branch_key = row.get("branch") or "All"
		previous = previous_revenue.get(branch_key)
		revenue = row.get("revenue") or 0
		row["growth"] = ((revenue - previous) / previous * 100) if previous else 0
		previous_revenue[branch_key] = revenue

	return data


def get_chart(filters):
	ctx = base_query(filters)
	abbr = get_company_abbr((filters or {}).get("company"))
	month_key = month_key_column(ctx.SI)

	monthly = (
		ctx.query.select(
			ctx.branch_column.as_("branch"),
			month_key.as_("month_key"),
			rounded_sum(ctx.SII.amount).as_("revenue"),
		)
		.groupby(ctx.branch_column, month_key)
		.orderby(month_key)
		.run(as_dict=True)
	)

	if not monthly:
		return None

	months = sorted({row["month_key"] for row in monthly})
	branches = sorted({row["branch"] for row in monthly if row["branch"]})
	lookup = {(row["branch"], row["month_key"]): row["revenue"] for row in monthly}

	datasets = [
		{
			"name": strip_abbr(branch, abbr),
			"values": [lookup.get((branch, month), 0) for month in months],
		}
		for branch in branches
	]

	return {
		"data": {"labels": [format_month_key(month) for month in months], "datasets": datasets},
		"type": "line",
		"colors": list(CHART_COLORS[: len(branches)]),
		"lineOptions": {"regionFill": 1},
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_revenue = sum(row.get("revenue") or 0 for row in data)
	total_profit = sum(row.get("profit") or 0 for row in data)
	total_invoices = sum(row.get("invoices") or 0 for row in data)

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

	return summary
