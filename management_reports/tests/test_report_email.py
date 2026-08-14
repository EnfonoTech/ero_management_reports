import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_first_day, get_last_day, getdate

from management_reports.management_reports import tasks
from management_reports.utils import report_email
from management_reports.utils.report_email import (
	SINGLE_DATE_REPORTS,
	build_filters,
	get_configured_reports,
	get_period,
	get_recipients,
)


class TestPeriods(FrappeTestCase):
	"""Every frequency must report a completed period. A daily digest sent at
	07:00 that reported 'today' would show an almost empty day."""

	AS_ON = "2026-03-15"

	def test_daily_covers_yesterday(self):
		period = get_period("Daily", self.AS_ON)

		self.assertEqual(period.from_date, getdate("2026-03-14"))
		self.assertEqual(period.to_date, getdate("2026-03-14"))

	def test_weekly_covers_the_previous_seven_days_ending_yesterday(self):
		period = get_period("Weekly", self.AS_ON)

		self.assertEqual(period.from_date, getdate("2026-03-08"))
		self.assertEqual(period.to_date, getdate("2026-03-14"))

	def test_monthly_covers_the_last_complete_month(self):
		period = get_period("Monthly", self.AS_ON)

		self.assertEqual(period.from_date, getdate("2026-02-01"))
		self.assertEqual(period.to_date, getdate("2026-02-28"))
		self.assertIn("February", period.label)

	def test_monthly_on_the_first_of_a_month_still_looks_back(self):
		period = get_period("Monthly", "2026-01-01")

		self.assertEqual(period.from_date, get_first_day(getdate("2025-12-01")))
		self.assertEqual(period.to_date, get_last_day(getdate("2025-12-01")))

	def test_no_period_ever_includes_today(self):
		for frequency in ("Daily", "Weekly", "Monthly"):
			with self.subTest(frequency=frequency):
				self.assertLess(get_period(frequency, self.AS_ON).to_date, getdate(self.AS_ON))


class TestFilters(FrappeTestCase):
	def test_single_date_report_gets_a_date_not_a_range(self):
		"""base_query prefers `date` over from/to, so sending both would collapse
		a range report to one day."""
		period = get_period("Monthly", "2026-03-15")
		filters = build_filters("Daily Summary", "ACME", period)

		self.assertIn("date", filters)
		self.assertNotIn("from_date", filters)
		self.assertNotIn("to_date", filters)

	def test_range_report_gets_a_range_and_no_date(self):
		period = get_period("Monthly", "2026-03-15")
		filters = build_filters("Monthly Summary", "ACME", period)

		self.assertNotIn("date", filters)
		self.assertEqual(filters["from_date"], period.from_date)
		self.assertEqual(filters["to_date"], period.to_date)

	def test_single_date_reports_are_actually_installed(self):
		"""A name in SINGLE_DATE_REPORTS that no longer exists would silently
		start receiving range filters."""
		self.require_app_reports()

		for report in SINGLE_DATE_REPORTS:
			with self.subTest(report=report):
				self.assertTrue(frappe.db.exists("Report", report))

	def test_default_reports_for_each_frequency_exist(self):
		self.require_app_reports()
		settings = frappe._dict({"email_reports": []})

		for frequency in ("Daily", "Weekly", "Monthly"):
			with self.subTest(frequency=frequency):
				reports = get_configured_reports(settings, frequency)
				self.assertTrue(reports)
				for report in reports:
					self.assertTrue(frappe.db.exists("Report", report), report)

	def require_app_reports(self):
		if not frappe.db.exists("Report", "Daily Summary"):
			self.skipTest("management_reports reports not installed on this site")

	def test_explicit_selection_overrides_the_default(self):
		settings = frappe._dict({"email_reports": [frappe._dict({"report": "Customer Analysis"})]})

		self.assertEqual(get_configured_reports(settings, "Daily"), ["Customer Analysis"])


class TestRecipients(FrappeTestCase):
	def rows(self, *specs):
		return frappe._dict(
			{
				"recipients": [
					frappe._dict({"email_id": email, "enabled": enabled}) for email, enabled in specs
				]
			}
		)

	def test_disabled_rows_are_excluded(self):
		settings = self.rows(("a@example.com", 1), ("b@example.com", 0))

		self.assertEqual(get_recipients(settings), ["a@example.com"])

	def test_duplicates_collapse_case_insensitively(self):
		"""Nobody should get the digest twice because of casing."""
		settings = self.rows(("A@Example.com", 1), ("a@example.com", 1))

		self.assertEqual(get_recipients(settings), ["A@Example.com"])

	def test_blank_rows_are_ignored(self):
		settings = self.rows(("", 1), ("  ", 1), ("c@example.com", 1))

		self.assertEqual(get_recipients(settings), ["c@example.com"])

	def test_no_recipients_returns_empty(self):
		self.assertEqual(get_recipients(frappe._dict({"recipients": []})), [])


class TestParseRecipients(FrappeTestCase):
	def test_comma_and_semicolon_strings(self):
		self.assertEqual(
			tasks.parse_recipients("a@x.com, b@x.com; c@x.com"),
			["a@x.com", "b@x.com", "c@x.com"],
		)

	def test_json_array(self):
		self.assertEqual(tasks.parse_recipients('["a@x.com","b@x.com"]'), ["a@x.com", "b@x.com"])

	def test_list_passthrough_and_blank_handling(self):
		self.assertEqual(tasks.parse_recipients(["a@x.com", " ", ""]), ["a@x.com"])
		self.assertEqual(tasks.parse_recipients(None), [])
		self.assertEqual(tasks.parse_recipients(""), [])


class TestScheduleDueLogic(FrappeTestCase):
	def test_daily_is_always_due(self):
		self.assertTrue(tasks.is_due("Daily", getdate("2026-03-15")))

	def test_weekly_is_due_only_on_monday(self):
		monday = getdate("2026-03-16")
		self.assertTrue(tasks.is_due("Weekly", monday))
		self.assertFalse(tasks.is_due("Weekly", add_days(monday, 1)))

	def test_monthly_is_due_only_on_the_first(self):
		self.assertTrue(tasks.is_due("Monthly", getdate("2026-03-01")))
		self.assertFalse(tasks.is_due("Monthly", getdate("2026-03-02")))

	# An unset or unexpected frequency must not fire a send.
	def test_unknown_frequency_is_never_due(self):
		self.assertFalse(tasks.is_due("", getdate("2026-03-01")))
		self.assertFalse(tasks.is_due("Hourly", getdate("2026-03-01")))


class TestRendering(FrappeTestCase):
	def test_empty_rows_render_a_message_not_an_empty_table(self):
		html = report_email.render_table([{"label": "Branch", "fieldname": "branch"}], [])

		self.assertIn("No data", html)
		self.assertNotIn("<table", html)

	def test_values_are_html_escaped(self):
		"""Branch and customer names come from user data and land in an email."""
		columns = [{"label": "Branch", "fieldname": "branch", "fieldtype": "Data"}]
		html = report_email.render_table(columns, [{"branch": "<script>alert(1)</script>"}])

		self.assertNotIn("<script>", html)
		self.assertIn("&lt;script&gt;", html)

	def test_column_labels_are_escaped_too(self):
		html = report_email.render_table([{"label": "<b>x</b>", "fieldname": "x"}], [{"x": 1}])

		self.assertNotIn("<b>x</b>", html)

	def test_row_cap_is_reported_rather_than_silently_truncating(self):
		columns = [{"label": "N", "fieldname": "n", "fieldtype": "Int"}]
		rows = [{"n": i} for i in range(report_email.MAX_ROWS_IN_EMAIL + 10)]
		html = report_email.render_table(columns, rows)

		self.assertIn(str(len(rows)), html)
		self.assertIn("truncated", html)

	def test_list_rows_are_supported_as_well_as_dicts(self):
		columns = [{"label": "A", "fieldname": "a"}, {"label": "B", "fieldname": "b"}]

		self.assertEqual(report_email.cell_value(["x", "y"], columns[1], 1), "y")
		self.assertEqual(report_email.cell_value({"b": "y"}, columns[1], 1), "y")
		# Short row must not raise IndexError.
		self.assertIsNone(report_email.cell_value(["x"], columns[1], 1))

	def test_percent_and_int_formatting(self):
		self.assertEqual(report_email.format_cell(12.345, {"fieldtype": "Percent"}), "12.3%")
		self.assertEqual(report_email.format_cell(7.0, {"fieldtype": "Int"}), "7")
		self.assertEqual(report_email.format_cell(None, {"fieldtype": "Currency"}), "")
