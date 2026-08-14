import frappe
from frappe import _

SETTINGS_DOCTYPE = "Management Reports Settings"
USER_TABLE_DOCTYPE = "Management Reports User"


def is_allowed_user(user=None):
	"""Check if user is allowed to access management reports.
	Administrator always has access. Other users must be in the allowed list.
	If no users are configured, only Administrator has access (default on install)."""
	if not user:
		user = frappe.session.user

	if user == "Administrator":
		return True

	# The table is absent mid-install and mid-migrate; checking beats catching,
	# which would also swallow real errors and lock everyone out silently.
	if not frappe.db.table_exists(USER_TABLE_DOCTYPE):
		return False

	allowed_users = frappe.db.get_all(
		USER_TABLE_DOCTYPE,
		filters={"parenttype": SETTINGS_DOCTYPE, "parent": SETTINGS_DOCTYPE},
		pluck="user",
	)

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
