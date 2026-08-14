import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_days, add_months, get_first_day, getdate, nowdate

from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.query import (
	base_query,
	customer_count,
	format_month_key,
	invoice_count,
	rounded_sum,
)


@frappe.whitelist()
def get_dashboard_kpis(company=None):
	check_access()

	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)

	if not company:
		return {"error": _("No default company found. Please set a default company.")}

	today = getdate(nowdate())
	mtd_start = get_first_day(today)

	mtd = get_period_totals(company, mtd_start, today)
	last_12m = get_period_totals(company, add_months(today, -12), today)

	result = {
		"company": company,
		"currency": get_currency(company),
		"mtd_revenue": mtd.revenue,
		"mtd_invoices": mtd.invoices,
		"mtd_customers": mtd.customers,
		"last_12m_revenue": last_12m.revenue,
		"active_branches": get_active_branches(company, add_months(today, -12), today),
		"last_month_revenue": 0,
		"last_month_invoices": 0,
		"last_month_customers": 0,
		"last_month_label": "",
	}

	# Early in the month there is often nothing to show yet, so fall back to the
	# last completed month rather than presenting a dashboard full of zeros.
	if not mtd.revenue:
		prev_month_end = add_days(mtd_start, -1)
		prev_month = get_period_totals(company, get_first_day(prev_month_end), prev_month_end)

		result["last_month_revenue"] = prev_month.revenue
		result["last_month_invoices"] = prev_month.invoices
		result["last_month_customers"] = prev_month.customers
		result["last_month_label"] = format_month_key(prev_month_end.strftime("%Y-%m"))

	return result


def get_period_totals(company, from_date, to_date) -> frappe._dict:
	"""Revenue, invoice count and customer count for a period, in one query.

	Replaces three separate scans per period. Branch scope comes from
	``base_query``, so a restricted user's KPI cards match the reports they can
	actually open.
	"""
	filters = {"company": company, "from_date": from_date, "to_date": to_date}
	ctx = base_query(filters, with_items=False)

	rows = ctx.query.select(
		rounded_sum(ctx.SI.grand_total).as_("revenue"),
		invoice_count(ctx.SI).as_("invoices"),
		customer_count(ctx.SI).as_("customers"),
	).run(as_dict=True)

	row = rows[0] if rows else {}

	return frappe._dict(
		{
			"revenue": row.get("revenue") or 0,
			"invoices": row.get("invoices") or 0,
			"customers": row.get("customers") or 0,
		}
	)


def get_active_branches(company, from_date, to_date) -> int:
	"""Distinct branches that invoiced anything in the period."""
	filters = {"company": company, "from_date": from_date, "to_date": to_date}
	ctx = base_query(filters, with_items=False)

	rows = ctx.query.select(Count(ctx.branch_column).distinct().as_("branches")).run(as_dict=True)

	return (rows[0].get("branches") if rows else 0) or 0
