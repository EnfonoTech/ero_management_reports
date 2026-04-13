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
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Cost Center", "width": 160},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 80},
		{"label": _("Revenue ({0})").format(currency), "fieldname": "revenue", "fieldtype": "Currency", "options": "currency", "width": 150},
		{"label": _("Share %"), "fieldname": "share", "fieldtype": "Percent", "width": 90},
		{"label": _("Avg Invoice ({0})").format(currency), "fieldname": "avg_invoice", "fieldtype": "Currency", "options": "currency", "width": 140},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	currency = get_currency(filters)

	total_revenue = frappe.db.sql("""
		SELECT ROUND(SUM(si.grand_total), 2)
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
	""".format(conditions=conditions), filters)[0][0] or 0

	data = frappe.db.sql("""
		SELECT
			si.customer,
			si.customer_name,
			si.cost_center AS branch,
			COUNT(si.name) AS invoices,
			ROUND(SUM(si.grand_total), 2) AS revenue
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY si.customer, si.customer_name, si.cost_center
		ORDER BY SUM(si.grand_total) DESC
	""".format(conditions=conditions), filters, as_dict=1)

	for row in data:
		row["share"] = (row["revenue"] / total_revenue * 100) if total_revenue else 0
		row["avg_invoice"] = (row["revenue"] / row["invoices"]) if row.get("invoices") else 0
		row["currency"] = currency

	return data


def get_chart(data):
	if not data:
		return None

	top_10 = data[:10]
	return {
		"data": {
			"labels": [(row.get("customer_name") or row.get("customer") or "Unknown")[:20] for row in top_10],
			"datasets": [
				{"name": _("Revenue"), "values": [row["revenue"] for row in top_10]},
			],
		},
		"type": "donut",
		"colors": ["#0f3460", "#2d6a4f", "#e07c24", "#7b2cbf", "#dc3545",
			"#17a2b8", "#6c757d", "#28a745", "#fd7e14", "#6610f2"],
	}


def get_report_summary(data, filters):
	currency = get_currency(filters)
	total_revenue = sum(row.get("revenue", 0) for row in data)
	total_invoices = sum(row.get("invoices", 0) for row in data)
	unique_customers = len(set(row.get("customer") for row in data))
	avg_invoice = (total_revenue / total_invoices) if total_invoices else 0

	return [
		{"value": total_revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": unique_customers, "label": _("Customers"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_invoices, "label": _("Total Invoices"), "datatype": "Int", "indicator": "Blue"},
		{"value": avg_invoice, "label": _("Avg Invoice"), "datatype": "Currency", "currency": currency, "indicator": "Green"},
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
