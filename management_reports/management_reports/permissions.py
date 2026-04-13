import frappe
from frappe import _


def is_allowed_user(user=None):
	"""Check if user is allowed to access management reports.
	Administrator always has access. Other users must be in the allowed list.
	If no users are configured, only Administrator has access (default on install)."""
	if not user:
		user = frappe.session.user

	if user == "Administrator":
		return True

	try:
		allowed_users = frappe.db.get_all(
			"Management Reports User",
			filters={"parenttype": "Management Reports Settings", "parent": "Management Reports Settings"},
			pluck="user",
		)
	except Exception:
		# Table may not exist yet during install
		return False

	# If no users configured, only Administrator has access
	if not allowed_users:
		return False

	return user in allowed_users


def check_access():
	"""Call at the start of report execute() and whitelisted APIs.
	Throws PermissionError if user is not allowed."""
	if not is_allowed_user():
		frappe.throw(
			_("You do not have access to Management Reports. Please contact your Administrator."),
			frappe.PermissionError,
		)
