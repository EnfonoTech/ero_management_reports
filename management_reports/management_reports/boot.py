import frappe

from management_reports.management_reports.permissions import is_allowed_user
from management_reports.utils.dimensions import get_branch_dimension_safe


def boot_session(bootinfo):
	"""Expose report access and the site's branch dimension to the desk."""
	bootinfo.management_reports_access = is_allowed_user(frappe.session.user)

	# Report filters read this instead of hardcoding Cost Center, so a site that
	# models branches differently needs no JS change.
	bootinfo.management_reports_branch = get_branch_dimension_safe()
