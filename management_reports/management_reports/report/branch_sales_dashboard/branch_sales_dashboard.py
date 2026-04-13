import frappe
from frappe import _
from management_reports.management_reports.permissions import check_access


def execute(filters=None):
	check_access()
	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart(filters)
	report_summary = get_report_summary(data, filters)
	return columns, data, None, chart, report_summary


def get_columns(filters):
	currency = get_currency(filters)
	return [
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 200},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 100},
		{"label": _("Customers"), "fieldname": "customers", "fieldtype": "Int", "width": 100},
		{"label": _("Revenue ({0})").format(currency), "fieldname": "revenue", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("COGS ({0})").format(currency), "fieldname": "cogs", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Gross Profit ({0})").format(currency), "fieldname": "profit", "fieldtype": "Currency", "options": "currency", "width": 160},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	conditions = get_conditions(filters)

	data = frappe.db.sql("""
		SELECT
			si.cost_center AS branch,
			COUNT(DISTINCT si.name) AS invoices,
			COUNT(DISTINCT si.customer) AS customers,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY si.cost_center
		ORDER BY SUM(sii.amount) DESC
	""".format(conditions=conditions), filters, as_dict=1)

	for row in data:
		row["profit"] = (row.get("revenue") or 0) - (row.get("cogs") or 0)
		row["margin"] = (row["profit"] / row["revenue"] * 100) if row.get("revenue") else 0
		row["currency"] = get_currency(filters)

	return data


def get_chart(filters):
	conditions = get_conditions(filters)
	abbr = get_company_abbr(filters)

	monthly = frappe.db.sql("""
		SELECT
			si.cost_center AS branch,
			DATE_FORMAT(si.posting_date, '%%Y-%%m') AS month,
			ROUND(SUM(sii.amount), 2) AS revenue
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY si.cost_center, DATE_FORMAT(si.posting_date, '%%Y-%%m')
		ORDER BY month, si.cost_center
	""".format(conditions=conditions), filters, as_dict=1)

	if not monthly:
		return None

	months = sorted(set(row["month"] for row in monthly))
	branches = sorted(set(row["branch"] for row in monthly if row["branch"]))

	month_labels = []
	for m in months:
		parts = m.split("-")
		month_names = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
			"06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}
		month_labels.append(f"{month_names.get(parts[1], parts[1])} {parts[0]}")

	lookup = {}
	for row in monthly:
		lookup[(row["branch"], row["month"])] = row["revenue"]

	colors = ["#0f3460", "#2d6a4f", "#e07c24", "#7b2cbf", "#c1121f"]
	datasets = []
	for i, branch in enumerate(branches):
		short_name = branch.replace(f" - {abbr}", "").strip() if abbr else branch
		datasets.append({
			"name": short_name,
			"values": [lookup.get((branch, m), 0) for m in months],
		})

	return {
		"data": {
			"labels": month_labels,
			"datasets": datasets,
		},
		"type": "bar",
		"colors": colors[:len(branches)],
	}


def get_report_summary(data, filters):
	currency = get_currency(filters)
	total_revenue = sum(row.get("revenue", 0) for row in data)
	total_profit = sum(row.get("profit", 0) for row in data)
	total_invoices = sum(row.get("invoices", 0) for row in data)
	avg_margin = (total_profit / total_revenue * 100) if total_revenue else 0

	return [
		{"value": total_revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": total_profit, "label": _("Total Profit"), "datatype": "Currency", "currency": currency,
			"indicator": "Green" if total_profit >= 0 else "Red"},
		{"value": total_invoices, "label": _("Total Invoices"), "datatype": "Int", "indicator": "Blue"},
		{"value": avg_margin, "label": _("Avg Margin"), "datatype": "Percent", "indicator": "Green" if avg_margin >= 30 else "Orange"},
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


def get_company_abbr(filters):
	company = filters.get("company")
	if company:
		return frappe.get_cached_value("Company", company, "abbr") or ""
	return ""
