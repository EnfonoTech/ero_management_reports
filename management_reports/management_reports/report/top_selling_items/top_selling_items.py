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
		{"label": _("Rank"), "fieldname": "rank", "fieldtype": "Int", "width": 60},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 150},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
		{"label": _("Qty Sold"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 80},
		{"label": _("Revenue ({0})").format(currency), "fieldname": "revenue", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("COGS ({0})").format(currency), "fieldname": "cogs", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Profit ({0})").format(currency), "fieldname": "profit", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100},
	]


def get_data(filters):
	conditions = get_conditions(filters)
	limit = int(filters.get("limit") or 50)
	currency = get_currency(filters)

	data = frappe.db.sql("""
		SELECT
			sii.item_code,
			sii.item_name,
			sii.item_group,
			sii.stock_uom AS uom,
			ROUND(SUM(sii.qty), 2) AS qty,
			COUNT(DISTINCT sii.parent) AS invoices,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{conditions}
		GROUP BY sii.item_code, sii.item_name, sii.item_group, sii.stock_uom
		ORDER BY SUM(sii.amount) DESC
		LIMIT {limit}
	""".format(conditions=conditions, limit=limit), filters, as_dict=1)

	for i, row in enumerate(data, 1):
		row["rank"] = i
		row["profit"] = (row.get("revenue") or 0) - (row.get("cogs") or 0)
		row["margin"] = (row["profit"] / row["revenue"] * 100) if row.get("revenue") else 0
		row["currency"] = currency

	return data


def get_chart(data):
	if not data:
		return None

	top_10 = data[:10]
	return {
		"data": {
			"labels": [row["item_name"][:20] for row in top_10],
			"datasets": [
				{"name": _("Revenue"), "values": [row["revenue"] for row in top_10]},
				{"name": _("Profit"), "values": [row["profit"] for row in top_10]},
			],
		},
		"type": "bar",
		"colors": ["#0f3460", "#2d6a4f"],
	}


def get_report_summary(data, filters):
	currency = get_currency(filters)
	total_revenue = sum(row.get("revenue", 0) for row in data)
	total_profit = sum(row.get("profit", 0) for row in data)
	total_qty = sum(row.get("qty", 0) for row in data)
	avg_margin = (total_profit / total_revenue * 100) if total_revenue else 0

	return [
		{"value": total_revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"value": total_profit, "label": _("Total Profit"), "datatype": "Currency", "currency": currency, "indicator": "Green"},
		{"value": total_qty, "label": _("Total Qty Sold"), "datatype": "Float", "indicator": "Blue"},
		{"value": avg_margin, "label": _("Avg Margin"), "datatype": "Percent", "indicator": "Green" if avg_margin >= 30 else "Orange"},
	]


def get_conditions(filters):
	conditions = ""
	if filters.get("company"):
		conditions += " AND si.company = %(company)s"
	if filters.get("branch"):
		conditions += " AND si.cost_center = %(branch)s"
	if filters.get("item_group"):
		conditions += " AND sii.item_group = %(item_group)s"
	return conditions


def get_currency(filters):
	company = filters.get("company")
	if company:
		return frappe.get_cached_value("Company", company, "default_currency") or "SAR"
	return "SAR"
