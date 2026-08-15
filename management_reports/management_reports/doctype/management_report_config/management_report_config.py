import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

from management_reports.utils.currency import get_company_abbr, get_currency, strip_abbr
from management_reports.utils.dimensions import get_branch_dimension


class ManagementReportConfig(Document):
	def before_validate(self):
		# Must also run here, not only in validate: Document.insert() calls
		# _validate_links() before any controller hook, so a Dynamic Link whose
		# options field is filled in validate() fails with
		# "Branch DocType must be set first" the first time a row is saved.
		# before_validate does not fix insert either — the child field carries a
		# default of Cost Center for that path — but it keeps updates correct.
		self.apply_branch_dimension()

	def validate(self):
		self.currency = get_currency(self.company)
		self.apply_branch_dimension()
		self.fill_display_names()
		self.validate_unique_branches()
		self.validate_branch_company()

	def apply_branch_dimension(self):
		"""Point every row's Dynamic Link at the site's configured dimension.

		Rows are stored against whatever the site uses for a branch, so this is
		refreshed on every save — if an implementer switches the dimension in
		Settings, the stale rows become visible instead of silently linking to a
		doctype that no longer applies.
		"""
		dim = get_branch_dimension()

		for row in self.branch_map or []:
			row.branch_doctype = dim.doctype

	def fill_display_names(self):
		"""Default the short name to the branch minus the company abbreviation."""
		abbr = get_company_abbr(self.company)

		for row in self.branch_map or []:
			if not row.display_name:
				row.display_name = strip_abbr(row.branch, abbr)

	def validate_unique_branches(self):
		seen = set()

		for row in self.branch_map or []:
			key = cstr(row.branch)
			if key in seen:
				frappe.throw(
					_("Branch is listed more than once: ") + frappe.bold(key),
					title=_("Duplicate Branch"),
				)
			seen.add(key)

	def validate_branch_company(self):
		"""Reject branches belonging to another company.

		A Cost Center from a different company would silently contribute nothing
		to this company's reports, which reads as missing data rather than as a
		configuration mistake.
		"""
		dim = get_branch_dimension()
		if not frappe.get_meta(dim.doctype).get_field("company"):
			return

		for row in self.branch_map or []:
			if not row.branch:
				continue

			owner = frappe.db.get_value(dim.doctype, row.branch, "company")
			if owner and owner != self.company:
				frappe.throw(
					_("Branch belongs to another company: ")
					+ frappe.bold(cstr(row.branch))
					+ " ("
					+ cstr(owner)
					+ ")",
					title=_("Wrong Company"),
				)
