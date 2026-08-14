import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

NUMERIC_FIELDTYPES = ("Currency", "Float", "Int", "Percent")
DATE_FIELDTYPES = ("Date", "Datetime")


class ManagementReportMetric(Document):
	"""A counter defined by configuration rather than code.

	Exists so a client-specific figure — complimentary meals, wastage, voided
	tickets — can be added to the digest without this app learning that client's
	DocTypes. Every fieldname here reaches SQL, so all of them are validated
	against the target DocType's meta on save.
	"""

	def validate(self):
		self.validate_doctype()
		self.validate_function()
		self.validate_date_field()
		self.validate_group_by_field()
		self.validate_filters()

	def validate_doctype(self):
		if not frappe.db.exists("DocType", self.document_type):
			frappe.throw(
				_("No such DocType: ") + frappe.bold(cstr(self.document_type)),
				title=_("Unknown DocType"),
			)

	def target_meta(self):
		"""Meta of the DocType being counted.

		Deliberately not named `meta` — that shadows Document.meta, which Frappe
		itself calls during __init__, and the shadow breaks every save.
		"""
		return frappe.get_meta(self.document_type)

	def validate_function(self):
		if self.function != "Sum":
			self.value_field = None
			return

		if not self.value_field:
			frappe.throw(
				_("Set a Value Field to sum, or change the function to Count."),
				title=_("Value Field Required"),
			)

		field = self.target_meta().get_field(self.value_field)
		if not field or field.fieldtype not in NUMERIC_FIELDTYPES:
			frappe.throw(
				_("Value Field must be a numeric field on the selected DocType: ")
				+ frappe.bold(cstr(self.value_field)),
				title=_("Invalid Value Field"),
			)

	def validate_date_field(self):
		"""Blank means `creation`, which every DocType has."""
		if not self.date_field:
			return

		field = self.target_meta().get_field(self.date_field)
		if not field or field.fieldtype not in DATE_FIELDTYPES:
			frappe.throw(
				_("Date Field must be a Date or Datetime field on the selected DocType: ")
				+ frappe.bold(cstr(self.date_field)),
				title=_("Invalid Date Field"),
			)

	def validate_group_by_field(self):
		if not self.group_by_field:
			return

		if not self.target_meta().get_field(self.group_by_field):
			frappe.throw(
				_("Break Down By must be a field on the selected DocType: ")
				+ frappe.bold(cstr(self.group_by_field)),
				title=_("Invalid Field"),
			)

	def validate_filters(self):
		"""Filters must be a flat JSON object of fieldname to value."""
		if not self.filters_json or not cstr(self.filters_json).strip():
			self.filters_json = None
			return

		try:
			filters = json.loads(self.filters_json)
		except ValueError:
			frappe.throw(_("Filters must be valid JSON."), title=_("Invalid Filters"))

		if not isinstance(filters, dict):
			frappe.throw(
				_('Filters must be a JSON object, for example {"status": "Approved"}.'),
				title=_("Invalid Filters"),
			)

		meta = self.target_meta()
		for fieldname in filters:
			if fieldname in ("name", "owner", "docstatus"):
				continue
			if not meta.get_field(fieldname):
				frappe.throw(
					_("Filter field does not exist on the selected DocType: ") + frappe.bold(fieldname),
					title=_("Invalid Filters"),
				)
