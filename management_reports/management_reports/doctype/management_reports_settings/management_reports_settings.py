import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr

from management_reports.utils.dimensions import DEFAULT_DIMENSION, get_dimension_options


class ManagementReportsSettings(Document):
	def validate(self):
		self.validate_branch_dimension()
		self.validate_ai_model()
		self.validate_schedule()
		self.dedupe_recipients()

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

	def validate_ai_model(self):
		"""Keep the model consistent with the provider.

		The model list is one shared Select across three providers, so switching
		provider leaves a stale value behind. Snapping it to the provider default
		here means the first AI call cannot fail on a model the endpoint has never
		heard of.
		"""
		from management_reports.utils.ai import DEFAULT_PROVIDER, models_for

		self.ai_provider = self.ai_provider or DEFAULT_PROVIDER
		allowed = models_for(self.ai_provider)

		if allowed and self.ai_model not in allowed:
			self.ai_model = allowed[0]

	def validate_schedule(self):
		if not self.auto_email_enabled:
			return

		if cint(self.email_hour) < 0 or cint(self.email_hour) > 23:
			frappe.throw(_("Send At Hour must be between 0 and 23."), title=_("Invalid Hour"))

		if not self.email_frequency:
			frappe.throw(
				_("Choose an email frequency, or turn off Enable Auto Email Reports."),
				title=_("Incomplete Schedule"),
			)

		if not [row for row in (self.recipients or []) if row.enabled and row.email_id]:
			frappe.throw(
				_("Add at least one enabled recipient before enabling automated reports."),
				title=_("No Recipients"),
			)

	def dedupe_recipients(self):
		"""Collapse duplicate addresses so nobody receives the digest twice."""
		seen = set()
		kept = []

		for row in self.recipients or []:
			email = cstr(row.email_id).strip().lower()
			if not email or email in seen:
				continue
			seen.add(email)
			kept.append(row)

		if len(kept) != len(self.recipients or []):
			self.recipients = kept
			for index, row in enumerate(self.recipients, 1):
				row.idx = index

	def on_update(self):
		# Reports cache the resolved dimension via get_cached_doc / meta lookups.
		frappe.clear_cache()


@frappe.whitelist()
def get_branch_dimension_options():
	"""Selectable branch dimensions, for the Settings form's field description."""
	frappe.only_for("System Manager")
	return get_dimension_options()
