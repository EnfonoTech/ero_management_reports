"""What was actually taken at the counter, split by tender.

Answers the question the Daily Summary cannot: of the day's takings, how much
came in as cash and how much on card. That split is what gets counted against
the till at close, so it is reported GROSS (VAT included) — Daily Summary's
"Income" is net of VAT and the two are not meant to tie.

Invoices with no tender recorded (dine-in "pay at counter", or anything settled
by a separate Payment Entry) are reported on their own row rather than dropped,
so the rows always add up to the day's invoiced total.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import base_query, invoice_count

UNRECORDED_LABEL = _("Not recorded at till")


def settled_total(SI):
	"""What an invoice actually settles for.

	ERPNext takes payment against rounded_total when rounding is on, so the
	tender rows sum to the rounded figure, not grand_total — over 30 days on this
	site that is a real 5.50 gap. An untendered invoice has to be measured the
	same way or the report's own rows would not add up. rounded_total is 0 when
	rounding is disabled, hence the fallback.
	"""
	return Case().when(SI.rounded_total != 0, SI.rounded_total).else_(SI.grand_total)


def execute(filters=None):
	check_access()
	data = get_data(filters)
	return get_columns(filters), data, None, get_chart(data), get_report_summary(data, filters)


def get_columns(filters):
	currency = get_currency((filters or {}).get("company"))
	branch = get_branch_dimension()

	return [
		{
			"label": _("Payment Mode"),
			"fieldname": "mode_of_payment",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": branch.label,
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": branch.doctype,
			"width": 180,
		},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Int", "width": 90},
		{
			"label": _("Collected") + " (" + currency + ")",
			"fieldname": "amount",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 160,
		},
		{"label": _("Share"), "fieldname": "share", "fieldtype": "Percent", "width": 90},
	]


def get_tendered(filters) -> list:
	"""Amounts recorded against a Mode of Payment on the invoice itself."""
	ctx = base_query(filters, with_items=False)
	SIP = frappe.qb.DocType("Sales Invoice Payment")

	rows = (
		ctx.query.inner_join(SIP)
		.on(SIP.parent == ctx.SI.name)
		.select(
			SIP.mode_of_payment.as_("mode_of_payment"),
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			Sum(SIP.amount).as_("amount"),
		)
		.groupby(SIP.mode_of_payment, ctx.branch_column)
		.run(as_dict=True)
	)

	return [row for row in rows if flt(row.get("amount"))]


def get_untendered(filters) -> list:
	"""Invoiced value with no tender row against it.

	Without this the split would quietly under-report the day: an invoice left to
	be settled at the counter has a grand total but no Sales Invoice Payment row,
	so it belongs to no mode at all.
	"""
	ctx = base_query(filters, with_items=False)
	SIP = frappe.qb.DocType("Sales Invoice Payment")

	# LEFT JOIN + IS NULL rather than a NOT EXISTS subquery: the same set, and it
	# stays inside the shared query skeleton so the company/date/branch scope
	# already applied to ctx.query is not lost.
	rows = (
		ctx.query.left_join(SIP)
		.on(SIP.parent == ctx.SI.name)
		.where(SIP.parent.isnull())
		.select(
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			Sum(settled_total(ctx.SI)).as_("amount"),
		)
		.groupby(ctx.branch_column)
		.run(as_dict=True)
	)

	out = []
	for row in rows:
		if not flt(row.get("amount")):
			continue
		row["mode_of_payment"] = UNRECORDED_LABEL
		out.append(row)

	return out


def get_data(filters):
	currency = get_currency((filters or {}).get("company"))
	data = get_tendered(filters) + get_untendered(filters)

	# Biggest tender first — the reader wants to know what dominated the day.
	data.sort(key=lambda row: flt(row.get("amount")), reverse=True)

	total = sum(flt(row.get("amount")) for row in data)
	for row in data:
		row["currency"] = currency
		row["share"] = (flt(row["amount"]) / total * 100) if total else 0

	return data


def get_chart(data):
	if not data:
		return None

	return {
		"data": {
			"labels": [row.get("mode_of_payment") or "" for row in data],
			"datasets": [{"name": _("Collected"), "values": [flt(row.get("amount")) for row in data]}],
		},
		"type": "donut",
		"height": 240,
	}


def get_report_summary(data, filters):
	currency = get_currency((filters or {}).get("company"))
	total = sum(flt(row.get("amount")) for row in data)

	summary = [
		{
			"value": total,
			"label": _("Total Collected"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		}
	]

	# One tile per mode, so the split is readable straight off the email header
	# without reading the table.
	by_mode = {}
	for row in data:
		by_mode[row.get("mode_of_payment")] = by_mode.get(row.get("mode_of_payment"), 0) + flt(row.get("amount"))

	for mode, amount in sorted(by_mode.items(), key=lambda item: item[1], reverse=True):
		summary.append(
			{
				"value": amount,
				"label": mode,
				"datatype": "Currency",
				"currency": currency,
				"indicator": "Red" if mode == UNRECORDED_LABEL else "Green",
			}
		)

	return summary
