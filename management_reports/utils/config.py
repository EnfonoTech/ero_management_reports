"""Per-company configuration lookups.

Settings holds what is true of the whole site; Management Report Config holds what
is true of one company — targets, branch owners, display names. Reports read
through here so a site with no Config behaves exactly as before.
"""

import frappe
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate

CONFIG_DOCTYPE = "Management Report Config"


def get_config(company: str | None):
	"""Active config document for a company, or None.

	Returns None for a missing or disabled config, so every caller degrades to
	"no targets configured" rather than erroring on a site that never set one up.
	"""
	if not company or not frappe.db.exists("DocType", CONFIG_DOCTYPE):
		return None

	name = frappe.db.exists(CONFIG_DOCTYPE, {"company": company, "disabled": 0})
	if not name:
		return None

	return frappe.get_cached_doc(CONFIG_DOCTYPE, name)


def get_branch_map(company: str | None) -> dict:
	"""``{branch: {display_name, manager, monthly_target}}`` for enabled rows."""
	config = get_config(company)
	if not config:
		return {}

	return {
		row.branch: {
			"display_name": row.display_name or row.branch,
			"manager": row.manager,
			"monthly_target": flt(row.monthly_target),
		}
		for row in config.branch_map or []
		if row.enabled and row.branch
	}


def get_branch_targets(company: str | None) -> dict:
	"""``{branch: monthly_target}`` for branches with a target above zero."""
	return {
		branch: values["monthly_target"]
		for branch, values in get_branch_map(company).items()
		if values["monthly_target"] > 0
	}


def get_branch_display_names(company: str | None) -> dict:
	return {branch: values["display_name"] for branch, values in get_branch_map(company).items()}


def get_company_target(company: str | None) -> float:
	config = get_config(company)

	return flt(config.monthly_revenue_target) if config else 0.0


def get_margin_floor(company: str | None) -> float:
	config = get_config(company)

	return flt(config.margin_floor) if config else 0.0


def period_months(from_date, to_date) -> float:
	"""Fractional calendar months covered by a date range.

	Targets are entered per month but reports are run over arbitrary ranges, so a
	raw comparison reports 900% for a nine-month filter and 3% for a single day.
	Each overlapped month contributes the share of its own days that the range
	covers, which makes a full month exactly 1.0 and February behave like
	February rather than like a 30-day approximation.
	"""
	# Checked before getdate, which turns None into today — that would silently
	# treat "no range given" as a single day and inflate every Achieved %.
	if not from_date or not to_date:
		return 0.0

	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		return 0.0

	months = 0.0
	cursor = get_first_day(start)
	while cursor <= end:
		month_end = get_last_day(cursor)
		covered_from = max(cursor, start)
		covered_to = min(month_end, end)
		days_in_month = (month_end - cursor).days + 1
		covered_days = (covered_to - covered_from).days + 1
		months += covered_days / days_in_month
		cursor = get_first_day(add_days(month_end, 1))

	return round(months, 6)


def prorate_target(monthly_target, from_date, to_date) -> float:
	"""Scale a monthly target to the filtered period."""
	return flt(monthly_target) * period_months(from_date, to_date)
