from frappe import _

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import (
	cogs_available,
	ctx_cogs,
	currency_label,
	invoice_count,
	rounded_sum,
)
from management_reports.utils.sources import collect


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
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 180,
		},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{
			"label": currency_label("Income", currency),
			"fieldname": "income",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{
			"label": currency_label("Expenses", currency),
			"fieldname": "expenses",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]

	# Without a COGS source, "Expenses" holds returns only — reporting that
	# difference as Profit would overstate it, so those columns are dropped.
	if cogs_available():
		columns.append(
			{
				"label": currency_label("Profit", currency),
				"fieldname": "profit",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 150,
			}
		)
		columns.append({"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100})

	return columns


def get_data(filters):
	currency = get_currency((filters or {}).get("company"))
	cogs = cogs_available()

	def build(ctx):
		selects = [
			ctx.date_column.as_("date"),
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			rounded_sum(ctx.amount).as_("income"),
		]

		if cogs:
			selects.append(ctx_cogs(ctx).as_("expenses"))

		return (
			ctx.query.select(*selects)
			.groupby(ctx.date_column, ctx.branch_column)
			.orderby(ctx.branch_column)
			.run(as_dict=True)
		)

	data = collect(
		filters,
		build,
		keys=("date", "branch"),
		sums=("invoices", "income", "expenses"),
		sort=lambda row: (row.get("branch") or ""),
	)

	returns = get_returns_by_branch(filters)

	for row in data:
		row["currency"] = currency
		income = row.get("income") or 0
		expenses = (row.get("expenses") or 0) + abs(returns.get(row.get("branch"), 0))
		row["expenses"] = expenses
		row["profit"] = income - expenses
		row["margin"] = (row["profit"] / income * 100) if income else 0

	return data


def get_returns_by_branch(filters) -> dict:
	"""Credit note totals per branch for the reported day.

	Kept as its own query so the returns figure stays visible and auditable.
	"""

	def build(ctx):
		return (
			ctx.query.select(ctx.branch_column.as_("branch"), rounded_sum(ctx.amount).as_("return_amount"))
			.groupby(ctx.branch_column)
			.run(as_dict=True)
		)

	rows = collect(filters, build, only_returns=True, keys=("branch",), sums=("return_amount",))

	return {row["branch"]: row["return_amount"] or 0 for row in rows}


def get_chart(data):
	if not data:
		return None

	datasets = [
		{"name": _("Income"), "values": [row.get("income") or 0 for row in data]},
		{"name": _("Expenses"), "values": [row.get("expenses") or 0 for row in data]},
	]

	if cogs_available():
		datasets.append({"name": _("Profit"), "values": [row.get("profit") or 0 for row in data]})

	return {
		"data": {
			"labels": [(row.get("branch") or "")[:20] for row in data],
			"datasets": datasets,
		},
		"type": "bar",
		"colors": ["#0f3460", "#dc3545", "#2d6a4f"][: len(datasets)],
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_income = sum(row.get("income") or 0 for row in data)
	total_expenses = sum(row.get("expenses") or 0 for row in data)
	total_profit = sum(row.get("profit") or 0 for row in data)
	margin = (total_profit / total_income * 100) if total_income else 0

	summary = [
		{
			"value": total_income,
			"label": _("Day's Income"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"value": total_expenses,
			"label": _("Day's Expenses"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red",
		},
	]

	if cogs_available():
		summary.append(
			{
				"value": total_profit,
				"label": _("Day's Profit"),
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Green" if total_profit >= 0 else "Red",
			}
		)
		summary.append(
			{
				"value": margin,
				"label": _("Margin"),
				"datatype": "Percent",
				"indicator": "Green" if margin >= 30 else "Orange",
			}
		)

	return summary
