from frappe import _
from frappe.query_builder import Order

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import base_query, currency_label, invoice_count, rounded_sum

CHART_COLORS = (
	"#0f3460",
	"#2d6a4f",
	"#e07c24",
	"#7b2cbf",
	"#dc3545",
	"#17a2b8",
	"#6c757d",
	"#28a745",
	"#fd7e14",
	"#6610f2",
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

	return [
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 160,
		},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 80},
		{
			"label": currency_label("Revenue", currency),
			"fieldname": "revenue",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
		{"label": _("Share %"), "fieldname": "share", "fieldtype": "Percent", "width": 90},
		{
			"label": currency_label("Avg Invoice", currency),
			"fieldname": "avg_invoice",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


def get_data(filters):
	currency = get_currency((filters or {}).get("company"))

	# Invoice-level report: revenue is grand_total, so the item table is not joined.
	ctx = base_query(filters, with_items=False)
	data = (
		ctx.query.select(
			ctx.SI.customer,
			ctx.SI.customer_name,
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			rounded_sum(ctx.SI.grand_total).as_("revenue"),
		)
		.groupby(ctx.SI.customer, ctx.SI.customer_name, ctx.branch_column)
		.orderby(rounded_sum(ctx.SI.grand_total), order=Order.desc)
		.run(as_dict=True)
	)

	# Share is against the same scoped population the rows come from, so the
	# percentages always add up to 100 for the visible data.
	total_revenue = sum(row.get("revenue") or 0 for row in data)

	for row in data:
		revenue = row.get("revenue") or 0
		invoices = row.get("invoices") or 0
		row["share"] = (revenue / total_revenue * 100) if total_revenue else 0
		row["avg_invoice"] = (revenue / invoices) if invoices else 0
		row["currency"] = currency

	return data


def get_chart(data):
	if not data:
		return None

	top_10 = data[:10]
	return {
		"data": {
			"labels": [
				(row.get("customer_name") or row.get("customer") or _("Unknown"))[:20] for row in top_10
			],
			"datasets": [{"name": _("Revenue"), "values": [row.get("revenue") or 0 for row in top_10]}],
		},
		"type": "donut",
		"colors": list(CHART_COLORS),
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total_revenue = sum(row.get("revenue") or 0 for row in data)
	total_invoices = sum(row.get("invoices") or 0 for row in data)
	unique_customers = len({row.get("customer") for row in data})
	avg_invoice = (total_revenue / total_invoices) if total_invoices else 0

	return [
		{
			"value": total_revenue,
			"label": _("Total Revenue"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{"value": unique_customers, "label": _("Customers"), "datatype": "Int", "indicator": "Blue"},
		{"value": total_invoices, "label": _("Total Invoices"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": avg_invoice,
			"label": _("Avg Invoice"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
	]
