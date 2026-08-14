"""Low-level Settings reads that are safe before the DocType exists."""

import frappe

SETTINGS_DOCTYPE = "Management Reports Settings"


def get_setting(fieldname: str, default=None):
	"""Read one Management Reports Settings field.

	Deliberately avoids ``frappe.db.get_single_value``, which loads DocType meta
	and therefore raises DoesNotExistError whenever the DocType is not synced
	yet — during ``install-app``, during ``migrate``, and on any site carrying
	the app in code but not in the database. Reading Singles directly returns
	None in those cases so callers can fall back to a default.
	"""
	if not frappe.db.table_exists("Singles"):
		return default

	# Queried through the builder rather than frappe.db.get_value, which appends
	# an ORDER BY `modified` that the Singles table does not have.
	singles = frappe.qb.DocType("Singles")
	rows = (
		frappe.qb.from_(singles)
		.select(singles.value)
		.where(singles.doctype == SETTINGS_DOCTYPE)
		.where(singles.field == fieldname)
		.limit(1)
		.run()
	)

	value = rows[0][0] if rows else None

	return value if value not in (None, "") else default
