import frappe
from frappe import _
from frappe.model.document import Document

from management_reports.utils.dimensions import DEFAULT_DIMENSION, get_dimension_options


class ManagementReportsSettings(Document):
	def validate(self):
		self.validate_branch_dimension()

	def validate_branch_dimension(self):
		"""Reject a branch dimension that is not a real Link field.

		The fieldname reaches SQL through every report, so it is checked here at
		the only point a human can set it — a typo must fail on save, not at
		query time on a client's dashboard.
		"""
		self.branch_dimension_fieldname = (self.branch_dimension_fieldname or DEFAULT_DIMENSION).strip()

		options = {option["fieldname"]: option["doctype"] for option in get_dimension_options()}
		if self.branch_dimension_fieldname not in options:
			frappe.throw(
				_("%s is not a Link field on Sales Invoice. Valid options: %s")
				% (
					frappe.bold(self.branch_dimension_fieldname),
					", ".join(sorted(options)),
				),
				title=_("Invalid Branch Dimension"),
			)

		self.branch_dimension_doctype = options[self.branch_dimension_fieldname]

	def on_update(self):
		# Reports cache the resolved dimension via get_cached_doc / meta lookups.
		frappe.clear_cache()


@frappe.whitelist()
def get_branch_dimension_options():
	"""Selectable branch dimensions, for the Settings form's field description."""
	frappe.only_for("System Manager")
	return get_dimension_options()
