import frappe
from frappe import _
from management_reports.management_reports.permissions import check_access


def execute(filters=None):
	check_access()
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(data)
	report_summary = get_report_summary(data, filters)
	return columns, data, None, chart, report_summary


def get_columns(filters):
	currency = get_currency(filters)
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 180},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{"label": _("Income ({0})").format(currency), "fieldname": "income", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Expenses ({0})").format(currency), "fieldname": "expenses", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Profit ({0})").format(currency), "fieldname": "profit", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	currency = get_currency(filters)
	report_date = filters.get("date")

	data = frappe.db.sql("""
		SELECT
			si.posting_date AS date,
			si.cost_center AS branch,
			COUNT(DISTINCT si.name) AS invoices,
			ROUND(SUM(sii.amount), 2) AS income,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS expenses
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date = %(date)s
			{conditions}
		GROUP BY si.posting_date, si.cost_center
		ORDER BY si.cost_center
	""".format(conditions=conditions), filters, as_dict=1)

	# Also add returns (Credit Notes) as negative income
	returns = frappe.db.sql("""
		SELECT
			si.cost_center AS branch,
			ROUND(SUM(sii.amount), 2) AS return_amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.is_return = 1
			AND si.posting_date = %(date)s
			{conditions}
		GROUP BY si.cost_center
	""".format(conditions=conditions), filters, as_dict=1)

	return_lookup = {r["branch"]: r["return_amount"] for r in returns}

	for row in data:
		returns_amt = return_lookup.get(row["branch"], 0)
		row["expenses"] = (row.get("expenses") or 0) + abs(returns_amt)
		row["profit"] = (row.get("income") or 0) - (row.get("expenses") or 0)
		row["margin"] = (row["profit"] / row["income"] * 100) if row.get("income") else 0
		row["currency"] = currency

	return data


def get_chart(data):
	if not data:
		return None

	abbr_lookup = {}

	return {
		"data": {
			"labels": [row.get("branch", "")[:20] for row in data],
			"datasets": [
				{"name": _("Income"), "values": [row["income"] for row in data]},
				{"name": _("Expenses"), "values": [row["expenses"] for row in data]},
				{"name": _("Profit"), "values": [row["profit"] for row in data]},
			],
		},
		"type": "bar",
		"colors": ["#0f3460", "#dc3545", "#2d6a4f"],
	}


def get_report_summary(data, filters):
	currency = get_currency(filters)
	total_income = sum(row.get("income", 0) for row in data)
	total_expenses = sum(row.get("expenses", 0) for row in data)
	total_profit = sum(row.get("profit", 0) for row in data)
	margin = (total_profit / total_income * 100) if total_income else 0

	return [
		{"value": total_income, "label": _("Day's Income"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": total_expenses, "label": _("Day's Expenses"), "datatype": "Currency", "currency": currency, "indicator": "Red"},
		{"value": total_profit, "label": _("Day's Profit"), "datatype": "Currency", "currency": currency,
			"indicator": "Green" if total_profit >= 0 else "Red"},
		{"value": margin, "label": _("Margin"), "datatype": "Percent",
			"indicator": "Green" if margin >= 30 else "Orange"},
	]


def get_conditions(filters):
	conditions = ""
	if filters.get("company"):
		conditions += " AND si.company = %(company)s"
	if filters.get("branch"):
		conditions += " AND si.cost_center = %(branch)s"
	return conditions


def get_currency(filters):
	company = filters.get("company")
	if company:
		return frappe.get_cached_value("Company", company, "default_currency") or "SAR"
	return "SAR"
