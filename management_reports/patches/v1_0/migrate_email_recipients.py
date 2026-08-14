"""Move comma-separated email_recipients into the Recipients child table.

The old Small Text field could not express per-recipient enable/disable, could
not be validated, and silently accepted typos that only surfaced as a failed
background send. Existing values are carried over so no site loses its
configured recipients on upgrade.
"""

import frappe
from frappe.utils import cstr, validate_email_address

SETTINGS = "Management Reports Settings"


def execute():
	if not frappe.db.exists("DocType", SETTINGS):
		return

	raw = frappe.db.get_value(
		"Singles", {"doctype": SETTINGS, "field": "email_recipients"}, "value", order_by=None
	)
	if not raw:
		return

	settings = frappe.get_doc(SETTINGS)
	existing = {cstr(row.email_id).strip().lower() for row in settings.recipients or []}

	added = 0
	skipped = []
	for candidate in cstr(raw).replace(";", ",").split(","):
		email = candidate.strip()
		if not email or email.lower() in existing:
			continue

		# A malformed legacy value must not block the whole migration — record it
		# and let a human fix it, rather than failing `bench migrate`.
		try:
			validate_email_address(email, throw=True)
		except Exception:
			skipped.append(email)
			continue

		settings.append("recipients", {"email_id": email, "enabled": 1})
		existing.add(email.lower())
		added += 1

	if added:
		settings.flags.ignore_permissions = True
		settings.save()

	if skipped:
		frappe.log_error(
			"Not migrated (invalid address): " + ", ".join(skipped),
			"Management Reports: email recipient migration",
		)
