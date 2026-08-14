from frappe import _

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import (
	base_query,
	cogs_available,
	cogs_expression,
	currency_label,
	format_month_key,
	invoice_count,
	month_key_column,
	rounded_sum,
)


def execute(filters=None):
	check_access()
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(data)
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
		{
			"label": currency_label("Income", currency),
			"fieldname": "income",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]

	if cogs_available():
		columns.append(
			{
				"label": currency_label("Expenses", currency),
				"fieldname": "expenses",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 150,
			}
		)
		columns.append(
			{
				"label": currency_label("Gross Profit", currency),
				"fieldname": "profit",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 160,
			}
		)
		columns.append({"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100})

	columns.append({"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90})
	columns.append(
		{
			"label": currency_label("Avg Invoice", currency),
			"fieldname": "avg_invoice",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		}
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
		rounded_sum(ctx.SII.amount).as_("income"),
	]

	cogs = cogs_expression(ctx.SII)
	if cogs is not None:
		selects.append(cogs.as_("expenses"))

	data = (
		ctx.query.select(*selects)
		.groupby(month_key, ctx.branch_column)
		.orderby(month_key, ctx.branch_column)
		.run(as_dict=True)
	)

	for row in data:
		row["currency"] = currency
		row["month"] = format_month_key(row.get("month_key"))

		income = row.get("income") or 0
		invoices = row.get("invoices") or 0
		row["avg_invoice"] = (income / invoices) if invoices else 0

		if cogs is not None:
			expenses = row.get("expenses") or 0
			row["profit"] = income - expenses
			row["margin"] = (row["profit"] / income * 100) if income else 0

	return data


def get_chart(data):
	if not data:
		return None

	# Aggregate across branches so the chart reads one bar group per month.
	month_totals = {}
	for row in data:
		month = row.get("month") or ""
		totals = month_totals.setdefault(month, {"income": 0, "expenses": 0, "profit": 0})
		totals["income"] += row.get("income") or 0
		totals["expenses"] += row.get("expenses") or 0
		totals["profit"] += row.get("profit") or 0

	labels = list(month_totals)
	datasets = [{"name": _("Income"), "values": [month_totals[m]["income"] for m in labels]}]

	if cogs_available():
		datasets.append({"name": _("Expenses"), "values": [month_totals[m]["expenses"] for m in labels]})
		datasets.append({"name": _("Profit"), "values": [month_totals[m]["profit"] for m in labels]})

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "bar",
		"colors": ["#0f3460", "#dc3545", "#2d6a4f"][: len(datasets)],
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_income = sum(row.get("income") or 0 for row in data)
	total_expenses = sum(row.get("expenses") or 0 for row in data)
	total_profit = sum(row.get("profit") or 0 for row in data)

	unique_months = len({row.get("month_key") for row in data})
	avg_monthly = (total_income / unique_months) if unique_months else 0

	summary = [
		{
			"value": total_income,
			"label": _("Total Income"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		}
	]

	if cogs_available():
		summary.append(
			{
				"value": total_expenses,
				"label": _("Total Expenses"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Red",
			}
		)
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
		{
			"value": avg_monthly,
			"label": _("Avg Monthly Income"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		}
	)

	return summary
