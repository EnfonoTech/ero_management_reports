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
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 120},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 180},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{"label": _("Revenue ({0})").format(currency), "fieldname": "revenue", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("COGS ({0})").format(currency), "fieldname": "cogs", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Profit ({0})").format(currency), "fieldname": "profit", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100},
		{"label": _("Revenue Growth %"), "fieldname": "growth", "fieldtype": "Percent", "width": 130},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	currency = get_currency(filters)

	data = frappe.db.sql("""
		SELECT
			DATE_FORMAT(si.posting_date, '%%Y-%%m') AS month_key,
			si.cost_center AS branch,
			COUNT(DISTINCT si.name) AS invoices,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
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

	prev_revenue = {}
	for row in data:
		row["profit"] = (row.get("revenue") or 0) - (row.get("cogs") or 0)
		row["margin"] = (row["profit"] / row["revenue"] * 100) if row.get("revenue") else 0
		row["currency"] = currency

		parts = row["month_key"].split("-")
		row["month"] = f"{month_names.get(parts[1], parts[1])} {parts[0]}"

		branch_key = row.get("branch") or "All"
		prev = prev_revenue.get(branch_key)
		if prev and prev > 0:
			row["growth"] = ((row["revenue"] - prev) / prev) * 100
		else:
			row["growth"] = 0
		prev_revenue[branch_key] = row["revenue"]

	return data


def get_chart(filters):
	conditions = get_conditions(filters)
	abbr = get_company_abbr(filters)

	monthly = frappe.db.sql("""
		SELECT
			si.cost_center AS branch,
			DATE_FORMAT(si.posting_date, '%%Y-%%m') AS month_key,
			ROUND(SUM(sii.amount), 2) AS revenue
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY si.cost_center, DATE_FORMAT(si.posting_date, '%%Y-%%m')
		ORDER BY month_key
	""".format(conditions=conditions), filters, as_dict=1)

	if not monthly:
		return None

	months = sorted(set(row["month_key"] for row in monthly))
	branches = sorted(set(row["branch"] for row in monthly if row["branch"]))

	month_names = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May",
		"06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}
	labels = [f"{month_names.get(m.split('-')[1], m.split('-')[1])} {m.split('-')[0]}" for m in months]

	lookup = {}
	for row in monthly:
		lookup[(row["branch"], row["month_key"])] = row["revenue"]

	colors = ["#0f3460", "#2d6a4f", "#e07c24", "#7b2cbf"]
	datasets = []
	for branch in branches:
		short_name = branch.replace(f" - {abbr}", "").strip() if abbr else branch
		datasets.append({
			"name": short_name,
			"values": [lookup.get((branch, m), 0) for m in months],
		})

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"colors": colors[:len(branches)],
		"lineOptions": {"regionFill": 1},
	}


def get_report_summary(data, filters):
	currency = get_currency(filters)
	total_revenue = sum(row.get("revenue", 0) for row in data)
	total_profit = sum(row.get("profit", 0) for row in data)
	total_invoices = sum(row.get("invoices", 0) for row in data)

	return [
		{"value": total_revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": total_profit, "label": _("Total Profit"), "datatype": "Currency", "currency": currency, "indicator": "Green"},
		{"value": total_invoices, "label": _("Total Invoices"), "datatype": "Int", "indicator": "Blue"},
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
