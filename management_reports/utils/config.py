"""Per-company configuration lookups.

Settings holds what is true of the whole site; Management Report Config holds what
is true of one company — targets, branch owners, display names. Reports read
through here so a site with no Config behaves exactly as before.
"""

import frappe
from frappe.utils import flt

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
