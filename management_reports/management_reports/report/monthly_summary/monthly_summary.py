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
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 120},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 180},
		{"label": _("Income ({0})").format(currency), "fieldname": "income", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Expenses ({0})").format(currency), "fieldname": "expenses", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Gross Profit ({0})").format(currency), "fieldname": "profit", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{"label": _("Avg Invoice ({0})").format(currency), "fieldname": "avg_invoice", "fieldtype": "Currency", "options": "currency", "width": 140},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	currency = get_currency(filters)

	data = frappe.db.sql("""
		SELECT
			DATE_FORMAT(si.posting_date, '%%Y-%%m') AS month_key,
			si.cost_center AS branch,
			COUNT(DISTINCT si.name) AS invoices,
			ROUND(SUM(sii.amount), 2) AS income,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS expenses
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m'), si.cost_center
		ORDER BY month_key, si.cost_center
	""".format(conditions=conditions), filters, as_dict=1)

	month_names = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
		"06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}

	for row in data:
		row["profit"] = (row.get("income") or 0) - (row.get("expenses") or 0)
		row["margin"] = (row["profit"] / row["income"] * 100) if row.get("income") else 0
		row["avg_invoice"] = (row["income"] / row["invoices"]) if row.get("invoices") else 0
		row["currency"] = currency

		parts = row["month_key"].split("-")
		row["month"] = f"{month_names.get(parts[1], parts[1])} {parts[0]}"

	return data


def get_chart(data):
	if not data:
		return None

	# Aggregate by month across branches
	month_totals = {}
	for row in data:
		mk = row.get("month", "")
		if mk not in month_totals:
			month_totals[mk] = {"income": 0, "expenses": 0, "profit": 0}
		month_totals[mk]["income"] += row.get("income", 0)
		month_totals[mk]["expenses"] += row.get("expenses", 0)
		month_totals[mk]["profit"] += row.get("profit", 0)

	labels = list(month_totals.keys())
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Income"), "values": [month_totals[m]["income"] for m in labels]},
				{"name": _("Expenses"), "values": [month_totals[m]["expenses"] for m in labels]},
				{"name": _("Profit"), "values": [month_totals[m]["profit"] for m in labels]},
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

	# Count unique months
	unique_months = len(set(row.get("month_key", "") for row in data))
	avg_monthly = (total_income / unique_months) if unique_months else 0

	return [
		{"value": total_income, "label": _("Total Income"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": total_expenses, "label": _("Total Expenses"), "datatype": "Currency", "currency": currency, "indicator": "Red"},
		{"value": total_profit, "label": _("Total Profit"), "datatype": "Currency", "currency": currency,
			"indicator": "Green" if total_profit >= 0 else "Red"},
		{"value": avg_monthly, "label": _("Avg Monthly Income"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
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
