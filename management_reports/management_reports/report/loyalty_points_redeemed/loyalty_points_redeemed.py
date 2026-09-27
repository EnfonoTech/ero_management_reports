"""Who spent loyalty points, how many, and against which bill.

Answers a question nothing else could: the points a customer claims never appear
as a tender, because ERPNext leaves grand_total alone on a redemption and posts a
separate credit to the receivable. Collections by Payment Mode now shows the
day's TOTAL settled with points; this names the customers behind it.

One redemption produces several Loyalty Point Entry rows -- ERPNext consumes the
member's oldest points first, so a single 153-point claim on EMR-2026-01609 left
seven rows, one per expiry bucket. Reporting those raw would read as seven
redemptions, so rows are grouped back to one line per invoice.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import base_query


def execute(filters=None):
	check_access()
	data = get_data(filters)
	return get_columns(filters), data, None, get_chart(data), get_report_summary(data, filters)


def get_columns(filters):
	currency = get_currency((filters or {}).get("company"))
	branch = get_branch_dimension()

	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 200,
		},
		{
			"label": _("Invoice"),
			"fieldname": "invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 150,
		},
		{"label": _("Points Used"), "fieldname": "points", "fieldtype": "Float", "precision": 0, "width": 110},
		{
			"label": _("Points Value") + " (" + currency + ")",
			"fieldname": "points_value",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Paid in Money") + " (" + currency + ")",
			"fieldname": "paid_amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{
			"label": _("Bill Total") + " (" + currency + ")",
			"fieldname": "bill_total",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


def get_data(filters):
	"""One row per invoice that redeemed points.

	Driven off Sales Invoice (not Loyalty Point Entry) so the company, date and
	branch scope every other report uses applies unchanged; the point COUNT is
	summed back from the ledger, which is the only place it is recorded per entry.
	"""
	currency = get_currency((filters or {}).get("company"))
	ctx = base_query(filters, with_items=False)

	rows = (
		ctx.query.select(
			ctx.SI.name.as_("invoice"),
			ctx.SI.customer.as_("customer"),
			ctx.SI.posting_date.as_("posting_date"),
			ctx.branch_column.as_("branch"),
			ctx.SI.loyalty_amount.as_("points_value"),
			ctx.SI.grand_total.as_("bill_total"),
		)
		.where(Coalesce(ctx.SI.loyalty_amount, 0) > 0)
		.orderby(ctx.SI.posting_date)
		.run(as_dict=True)
	)
	if not rows:
		return []

	LPE = frappe.qb.DocType("Loyalty Point Entry")
	used = dict(
		frappe.qb.from_(LPE)
		.select(LPE.invoice, Sum(-LPE.loyalty_points))
		.where((LPE.invoice.isin([row["invoice"] for row in rows])) & (LPE.loyalty_points < 0))
		.groupby(LPE.invoice)
		.run()
	)

	for row in rows:
		row["currency"] = currency
		row["points"] = flt(used.get(row["invoice"]))
		# What the customer actually handed over. ERPNext does not reduce
		# grand_total for a redemption, so this is the subtraction the counter
		# does in its head.
		row["paid_amount"] = flt(row["bill_total"]) - flt(row["points_value"])

	return rows


def get_chart(data):
	if not data:
		return None

	by_customer = {}
	for row in data:
		key = row.get("customer") or ""
		by_customer[key] = by_customer.get(key, 0) + flt(row.get("points_value"))

	top = sorted(by_customer.items(), key=lambda item: item[1], reverse=True)[:10]

	return {
		"data": {
			"labels": [name for name, _value in top],
			"datasets": [{"name": _("Points Value"), "values": [value for _name, value in top]}],
		},
		"type": "bar",
		"height": 240,
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	value = sum(flt(row.get("points_value")) for row in data)
	points = sum(flt(row.get("points")) for row in data)
	customers = len({row.get("customer") for row in data if row.get("customer")})

	return [
		{
			"value": value,
			"label": _("Settled with Points"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{"value": points, "label": _("Points Redeemed"), "datatype": "Float", "indicator": "Blue"},
		{"value": customers, "label": _("Customers"), "datatype": "Int", "indicator": "Green"},
		{"value": len(data), "label": _("Redemptions"), "datatype": "Int", "indicator": "Green"},
	]
