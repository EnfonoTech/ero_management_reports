"""Shared Sales Invoice query skeleton for every report in this app.

Reports previously each hand-rolled raw SQL with a string-built WHERE clause and
a hardcoded ``si.cost_center``. Building the skeleton once means the branch
dimension, the company filter and the User Permission branch scope cannot be
forgotten in one report and present in another.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count, DateFormat, Round, Sum
from frappe.utils import cint, cstr, getdate

from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.scope import apply_branch_scope
from management_reports.utils.settings import get_setting

COGS_VALUATION = "Item Valuation"
COGS_NONE = "None"

MONTH_KEY_FORMAT = "%Y-%m"
MONTH_ABBR = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

CHART_COLORS = ("#0f3460", "#2d6a4f", "#e07c24", "#7b2cbf", "#c1121f", "#17a2b8", "#28a745", "#fd7e14")


def base_query(filters=None, with_items=True, only_returns=False) -> frappe._dict:
	"""Sales Invoice query with company, date range and branch scope applied.

	Returns ``{query, SI, SII, dim, branch_column}``. ``SII`` is None when
	``with_items`` is False. Callers add their own select/group-by/order-by.
	"""
	filters = frappe._dict(filters or {})
	dim = get_branch_dimension()

	SI = frappe.qb.DocType("Sales Invoice")
	SII = frappe.qb.DocType("Sales Invoice Item") if with_items else None

	if with_items:
		query = frappe.qb.from_(SII).inner_join(SI).on(SI.name == SII.parent)
	else:
		query = frappe.qb.from_(SI)

	query = query.where(SI.docstatus == 1)
	query = apply_date_range(query, SI, filters)

	if filters.get("company"):
		query = query.where(SI.company == filters.company)

	branch_column = SI[dim.fieldname]
	if filters.get("branch"):
		query = query.where(branch_column == filters.branch)

	if only_returns:
		query = query.where(SI.is_return == 1)

	query = apply_branch_scope(query, branch_column, dim.doctype)

	return frappe._dict({"query": query, "SI": SI, "SII": SII, "dim": dim, "branch_column": branch_column})


def apply_date_range(query, SI, filters):
	"""Apply a single ``date`` filter, or a ``from_date``/``to_date`` range."""
	if filters.get("date"):
		return query.where(SI.posting_date == getdate(filters.date))

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if from_date and to_date:
		return query.where(SI.posting_date[getdate(from_date) : getdate(to_date)])
	if from_date:
		return query.where(SI.posting_date >= getdate(from_date))
	if to_date:
		return query.where(SI.posting_date <= getdate(to_date))

	return query


# --- COGS -----------------------------------------------------------------


def get_cogs_source() -> str:
	"""Configured COGS source for this site."""
	return get_setting("cogs_source", COGS_VALUATION)


def cogs_available() -> bool:
	"""Whether this site can produce COGS, and therefore profit and margin.

	Sites without perpetual inventory leave ``incoming_rate`` at zero, which
	turns every margin into a meaningless 100%. Such sites set the source to
	"None" and the reports drop the derived columns instead of publishing
	numbers nobody can trust.
	"""
	return get_cogs_source() != COGS_NONE


def cogs_expression(SII):
	"""``SUM(qty * incoming_rate)`` rounded, or None when COGS is unavailable."""
	if not cogs_available():
		return None

	return Round(Sum(SII.qty * SII.incoming_rate), 2)


def add_profit_columns(columns, currency, *, profit_label, cogs_label=None):
	"""Append COGS / Profit / Margin columns when the site supports COGS."""
	if not cogs_available():
		return columns

	columns.append(
		{
			"label": cogs_label or currency_label("COGS", currency),
			"fieldname": "cogs",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		}
	)
	columns.append(
		{
			"label": profit_label,
			"fieldname": "profit",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		}
	)
	columns.append({"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 100})

	return columns


def set_derived_profit(row, revenue_field="revenue", cost_field="cogs"):
	"""Fill profit and margin on a result row, tolerating missing COGS."""
	revenue = row.get(revenue_field) or 0
	cost = row.get(cost_field) or 0

	row["profit"] = revenue - cost
	row["margin"] = (row["profit"] / revenue * 100) if revenue else 0

	return row


# --- month helpers --------------------------------------------------------


def month_key_column(SI):
	"""``DATE_FORMAT(posting_date, '%Y-%m')`` — the literal is bound as a param."""
	return DateFormat(SI.posting_date, MONTH_KEY_FORMAT)


def format_month_key(key) -> str:
	"""Turn ``2026-03`` into ``Mar 2026``."""
	parts = cstr(key).split("-")
	if len(parts) != 2:
		return cstr(key)

	month = cint(parts[1])
	label = MONTH_ABBR[month] if 1 <= month <= 12 else parts[1]

	return label + " " + parts[0]


# --- shared aggregates ----------------------------------------------------


def invoice_count(SI):
	return Count(SI.name).distinct()


def customer_count(SI):
	return Count(SI.customer).distinct()


def rounded_sum(column):
	return Round(Sum(column), 2)


def currency_label(label, currency) -> str:
	"""``"Revenue (SAR)"`` — label translated, currency appended."""
	return _(label) + " (" + currency + ")"
