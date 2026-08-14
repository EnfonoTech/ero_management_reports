import frappe
from frappe.tests.utils import FrappeTestCase

from management_reports.utils import dimensions
from management_reports.utils.dimensions import (
	DEFAULT_DIMENSION,
	get_branch_dimension,
	get_branch_dimension_safe,
	get_dimension_options,
)


class TestBranchDimension(FrappeTestCase):
	def test_default_dimension_resolves_to_cost_center(self):
		with patch_setting({}):
			dim = get_branch_dimension()

		self.assertEqual(dim.fieldname, DEFAULT_DIMENSION)
		self.assertEqual(dim.doctype, "Cost Center")
		self.assertTrue(dim.filter_by_company)

	def test_configured_dimension_is_honoured(self):
		with patch_setting({"branch_dimension_fieldname": "set_warehouse"}):
			dim = get_branch_dimension()

		self.assertEqual(dim.fieldname, "set_warehouse")
		self.assertEqual(dim.doctype, "Warehouse")

	def test_label_comes_from_settings_not_the_erpnext_field_label(self):
		with patch_setting({"branch_label": "Outlet"}):
			self.assertEqual(get_branch_dimension().label, "Outlet")

	def test_unknown_fieldname_throws(self):
		with patch_setting({"branch_dimension_fieldname": "not_a_field"}):
			self.assertRaises(frappe.ValidationError, get_branch_dimension)

	def test_non_link_fieldname_throws(self):
		# posting_date exists but is a Date, so it cannot identify a branch.
		with patch_setting({"branch_dimension_fieldname": "posting_date"}):
			self.assertRaises(frappe.ValidationError, get_branch_dimension)

	def test_safe_variant_never_throws(self):
		"""A broken setting must not be able to block session boot."""
		with patch_setting({"branch_dimension_fieldname": "not_a_field"}):
			dim = get_branch_dimension_safe()

		self.assertEqual(dim.fieldname, DEFAULT_DIMENSION)

	def test_options_include_cost_center_and_flag_accounting_dimensions(self):
		options = {option["fieldname"]: option for option in get_dimension_options()}

		self.assertIn("cost_center", options)
		self.assertEqual(options["cost_center"]["doctype"], "Cost Center")
		self.assertIn("is_accounting_dimension", options["cost_center"])

	def test_every_option_is_usable_as_a_dimension(self):
		"""Anything offered in Settings must actually resolve without throwing."""
		for option in get_dimension_options():
			with patch_setting({"branch_dimension_fieldname": option["fieldname"]}):
				self.assertEqual(get_branch_dimension().fieldname, option["fieldname"])


class patch_setting:
	"""Stub Settings reads without writing to the database."""

	def __init__(self, values):
		self.values = values
		self.original = None

	def __enter__(self):
		self.original = dimensions.get_setting
		dimensions.get_setting = lambda fieldname, default=None: self.values.get(fieldname) or default
		return self

	def __exit__(self, *exc_info):
		dimensions.get_setting = self.original
		return False
