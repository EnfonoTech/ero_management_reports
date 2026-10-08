"""Pick up the new schedule fields on Management Reports Settings.

forced: a site whose doctype file is not newer than its stored copy would otherwise skip
the reload and the fields would never appear. Nothing is changed in the saved values.
"""

import frappe


def execute():
	frappe.reload_doc("management_reports", "doctype", "management_reports_settings", force=True)
