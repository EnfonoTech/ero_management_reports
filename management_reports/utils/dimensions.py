"""Branch dimension resolution.

Every site this app is installed on may model "branch" differently — Cost Center
on most, Warehouse / Branch / a custom Accounting Dimension elsewhere. Reports
must never hardcode the field. They ask here instead, so switching a site is a
Settings change rather than a rewrite of every report.
"""

import frappe
from frappe import _

from management_reports.utils.settings import get_setting

DEFAULT_DIMENSION = "cost_center"
DEFAULT_LABEL = "Branch"
REF_DOCTYPE = "Sales Invoice"


def get_branch_dimension() -> frappe._dict:
	"""Return the branch dimension configured for this site.

	Returns a dict with ``fieldname``, ``doctype`` and ``label``.

	The fieldname ends up in SQL, so it is validated against Sales Invoice meta
	rather than trusted straight from the settings value — a bad or renamed
	field throws instead of reaching the database.
	"""
	fieldname = get_configured_fieldname()
	df = frappe.get_meta(REF_DOCTYPE).get_field(fieldname)

	if not df or df.fieldtype != "Link":
		frappe.throw(
			_(
				"Branch dimension %s is not a Link field on Sales Invoice. Fix it in Management Reports Settings."
			)
			% frappe.bold(fieldname),
			title=_("Invalid Branch Dimension"),
		)

	return frappe._dict(
		{
			"fieldname": df.fieldname,
			"doctype": df.options,
			# The business term, not the ERPNext field label — a report column
			# reading "Cost Center" means nothing to a manager who calls it a
			# branch, an outlet or a station.
			"label": get_branch_label(),
			# Cost Center and Warehouse are company-scoped; the ERPNext Branch
			# doctype is not. Report filters check this before narrowing the link
			# query by company, which would otherwise return nothing.
			"filter_by_company": bool(frappe.get_meta(df.options).get_field("company")),
		}
	)


def get_branch_dimension_safe() -> frappe._dict:
	"""Never-throwing variant, for session boot.

	Misconfigured reporting settings must not block anyone from logging in, so
	this falls back to the default dimension and logs the problem instead.
	"""
	try:
		return get_branch_dimension()
	except Exception:
		frappe.clear_messages()
		frappe.log_error(frappe.get_traceback(), "Management Reports: invalid branch dimension configured")
		return frappe._dict(
			{
				"fieldname": DEFAULT_DIMENSION,
				"doctype": "Cost Center",
				"label": _(DEFAULT_LABEL),
				"filter_by_company": True,
			}
		)


def get_configured_fieldname() -> str:
	"""Raw configured fieldname, or the default when unset / pre-install."""
	return get_setting("branch_dimension_fieldname", DEFAULT_DIMENSION)


def get_branch_label() -> str:
	"""What this site calls a branch."""
	return _(get_setting("branch_label", DEFAULT_LABEL))


def get_dimension_options() -> list[dict]:
	"""Link fields on Sales Invoice that can serve as the branch dimension.

	Used by the Settings form to offer a validated list instead of free text.
	Accounting dimensions are flagged so the correct one is easy to spot.
	"""
	try:
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
			get_accounting_dimensions,
		)

		accounting_dimensions = set(get_accounting_dimensions())
	except Exception:
		# ERPNext missing, or the dimension table not yet migrated
		accounting_dimensions = set()

	return [
		{
			"fieldname": df.fieldname,
			"label": _(df.label or df.fieldname),
			"doctype": df.options,
			"is_accounting_dimension": df.fieldname in accounting_dimensions,
		}
		for df in frappe.get_meta(REF_DOCTYPE).get_link_fields()
		if df.options
	]


@frappe.whitelist()
def get_branch_filter_meta() -> dict:
	"""Branch dimension descriptor for report filters and dashboard JS.

	Read-only metadata about the site's own configuration — no document data —
	so any authenticated user may read it. Report data itself stays gated by
	``permissions.check_access`` plus the branch scope in ``utils.scope``.
	"""
	dim = get_branch_dimension()
	return {"fieldname": dim.fieldname, "doctype": dim.doctype, "label": dim.label}
