import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate, nowdate

from management_reports.management_reports.report.branch_sales_dashboard import (
	branch_sales_dashboard,
)
from management_reports.management_reports.report.customer_analysis import customer_analysis
from management_reports.management_reports.report.daily_summary import daily_summary
from management_reports.management_reports.report.monthly_sales_trend import monthly_sales_trend
from management_reports.management_reports.report.monthly_summary import monthly_summary
from management_reports.management_reports.report.top_selling_items import top_selling_items
from management_reports.utils import query as query_utils
from management_reports.utils.scope import get_permitted_branches

RANGE_REPORTS = (
	branch_sales_dashboard,
	top_selling_items,
	monthly_sales_trend,
	customer_analysis,
	monthly_summary,
)


class TestReports(FrappeTestCase):
	"""Runs every report end to end. Data-independent assertions only, so this
	passes on a fresh site and on a site with years of invoices."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.to_date = getdate(nowdate())
		cls.from_date = add_months(cls.to_date, -6)

	def filters(self, **overrides):
		values = {"company": self.company, "from_date": self.from_date, "to_date": self.to_date}
		values.update(overrides)
		return values

	def test_every_range_report_executes(self):
		if not self.company:
			self.skipTest("no company on site")

		for report in RANGE_REPORTS:
			with self.subTest(report=report.__name__):
				columns, data, message, chart, summary = report.execute(self.filters())

				self.assertTrue(columns)
				self.assertIsInstance(data, list)
				self.assertIsNone(message)
				self.assertIsInstance(summary, list)

	def test_daily_summary_executes(self):
		if not self.company:
			self.skipTest("no company on site")

		columns, data, _message, _chart, summary = daily_summary.execute(
			{"company": self.company, "date": self.to_date}
		)

		self.assertTrue(columns)
		self.assertIsInstance(data, list)
		self.assertIsInstance(summary, list)

	def test_every_row_carries_currency_for_the_currency_columns(self):
		"""Currency columns declare options="currency", so each row must supply it
		or the desk renders bare numbers with no symbol."""
		if not self.company:
			self.skipTest("no company on site")

		for report in RANGE_REPORTS:
			with self.subTest(report=report.__name__):
				columns, data, *_ = report.execute(self.filters())
				needs_currency = any(column.get("options") == "currency" for column in columns)

				if needs_currency and data:
					self.assertTrue(all(row.get("currency") for row in data))

	def test_branch_column_uses_the_configured_dimension(self):
		if not self.company:
			self.skipTest("no company on site")

		columns = branch_sales_dashboard.get_columns(self.filters())
		branch_column = next(column for column in columns if column["fieldname"] == "branch")

		self.assertEqual(branch_column["fieldtype"], "Link")
		self.assertEqual(branch_column["options"], "Cost Center")

	def test_profit_columns_disappear_without_a_cogs_source(self):
		original = query_utils.get_cogs_source
		query_utils.get_cogs_source = lambda: query_utils.COGS_NONE
		try:
			columns = branch_sales_dashboard.get_columns(self.filters())
			fieldnames = [column["fieldname"] for column in columns]

			self.assertNotIn("cogs", fieldnames)
			self.assertNotIn("profit", fieldnames)
			self.assertNotIn("margin", fieldnames)
			self.assertIn("revenue", fieldnames)
		finally:
			query_utils.get_cogs_source = original

	def test_scoped_user_sees_a_subset_of_branches(self):
		"""The whole point of the scope layer: a restricted user must not read
		every branch out of a raw SQL report."""
		if not self.company:
			self.skipTest("no company on site")

		_columns, unrestricted, *_ = branch_sales_dashboard.execute(self.filters())
		branches = [row.get("branch") for row in unrestricted if row.get("branch")]

		if len(branches) < 2:
			self.skipTest("site has fewer than two invoicing branches")

		from management_reports.utils import scope

		original_getter = scope.get_user_permissions
		original_access = branch_sales_dashboard.check_access
		scope.get_user_permissions = lambda user=None: {
			"Cost Center": [frappe._dict({"doc": branches[0], "applicable_for": None, "hide_descendants": 1})]
		}
		branch_sales_dashboard.check_access = lambda: None
		frappe.set_user(self.restricted_user())
		try:
			_columns, restricted, *_ = branch_sales_dashboard.execute(self.filters())
			self.assertEqual([row["branch"] for row in restricted], [branches[0]])
		finally:
			frappe.set_user("Administrator")
			scope.get_user_permissions = original_getter
			branch_sales_dashboard.check_access = original_access

	def restricted_user(self):
		user = frappe.db.get_value("User", {"name": ["not in", ["Administrator", "Guest"]]}, "name")
		if not user:
			self.skipTest("no non-Administrator user on site")
		return user

	def test_month_labels_are_human_readable(self):
		self.assertEqual(query_utils.format_month_key("2026-03"), "Mar 2026")
		self.assertEqual(query_utils.format_month_key("2026-12"), "Dec 2026")
		# Never crash on unexpected input — a bad key must degrade, not throw.
		self.assertEqual(query_utils.format_month_key("garbage"), "garbage")
		self.assertEqual(query_utils.format_month_key(None), "")

	def test_permitted_branches_distinguishes_none_from_empty(self):
		"""None means unrestricted; a list means restricted. Conflating them is
		how a scoping bug turns into a data leak."""
		self.assertIsNone(get_permitted_branches("Cost Center", "Administrator"))
