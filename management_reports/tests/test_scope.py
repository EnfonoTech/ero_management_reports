import frappe
from frappe.tests.utils import FrappeTestCase

from management_reports.utils import scope
from management_reports.utils.scope import get_permitted_branches

BRANCH_DOCTYPE = "Cost Center"


class TestBranchScope(FrappeTestCase):
	"""Script reports bypass Frappe's permission layer, so these guarantees are
	the only thing standing between a branch manager and the whole company."""

	def setUp(self):
		self.original_getter = scope.get_user_permissions
		self.leaf = frappe.db.get_value(BRANCH_DOCTYPE, {"is_group": 0}, "name")
		self.group = frappe.db.get_value(BRANCH_DOCTYPE, {"is_group": 1}, "name")

	def tearDown(self):
		scope.get_user_permissions = self.original_getter

	def stub_permissions(self, permissions):
		scope.get_user_permissions = lambda user=None: permissions

	def entry(self, doc, **overrides):
		values = {"doc": doc, "applicable_for": None, "is_default": 0, "hide_descendants": 1}
		values.update(overrides)
		return frappe._dict(values)

	def test_administrator_is_unrestricted(self):
		self.stub_permissions({BRANCH_DOCTYPE: [self.entry(self.leaf)]})
		self.assertIsNone(get_permitted_branches(BRANCH_DOCTYPE, "Administrator"))

	def test_no_permissions_means_unrestricted(self):
		self.stub_permissions({})
		self.assertIsNone(get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com"))

	def test_permission_on_another_doctype_does_not_restrict_branches(self):
		self.stub_permissions({"Customer": [self.entry("Some Customer")]})
		self.assertIsNone(get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com"))

	def test_single_branch_permission_restricts_to_that_branch(self):
		self.stub_permissions({BRANCH_DOCTYPE: [self.entry(self.leaf)]})
		self.assertEqual(get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com"), [self.leaf])

	def test_applicable_for_elsewhere_does_not_restrict(self):
		"""A permission scoped to another doctype must not lock reports down."""
		self.stub_permissions({BRANCH_DOCTYPE: [self.entry(self.leaf, applicable_for="Purchase Invoice")]})
		self.assertIsNone(get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com"))

	def test_descendants_are_included_by_default(self):
		if not self.group:
			self.skipTest("site has no group cost center")

		self.stub_permissions({BRANCH_DOCTYPE: [self.entry(self.group, hide_descendants=0)]})
		permitted = get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com")

		self.assertIn(self.group, permitted)
		self.assertGreater(len(permitted), 1)

	def test_hide_descendants_restricts_to_the_node_itself(self):
		if not self.group:
			self.skipTest("site has no group cost center")

		self.stub_permissions({BRANCH_DOCTYPE: [self.entry(self.group, hide_descendants=1)]})
		self.assertEqual(get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com"), [self.group])

	def test_permission_on_a_nonexistent_branch_permits_nothing(self):
		"""Must return that one name, so the query filters everything out.

		The failure mode this guards against is returning an empty list that a
		caller reads as "unrestricted" and then shows the whole company.
		"""
		self.stub_permissions({BRANCH_DOCTYPE: [self.entry("Does Not Exist - ZZ")]})
		permitted = get_permitted_branches(BRANCH_DOCTYPE, "someone@example.com")

		self.assertEqual(permitted, ["Does Not Exist - ZZ"])
		self.assertIsNotNone(permitted)
