import frappe
from management_reports.management_reports.permissions import is_allowed_user


def boot_session(bootinfo):
	"""Add management reports access flag to boot session"""
	bootinfo.management_reports_access = is_allowed_user(frappe.session.user)
