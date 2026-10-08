"""Pure tests for the multi-schedule logic: no site, no database.

    cd <bench> && env/bin/python -m unittest management_reports.tests.test_schedule
"""

import unittest
from datetime import datetime

import frappe

from management_reports.management_reports import tasks
from management_reports.utils import report_email


def settings(**fields):
	base = {
		"send_daily": 0, "send_weekly": 0, "send_monthly": 0, "email_frequency": "",
		"weekly_send_day": "", "monthly_send_day": 0, "email_reports": [], "daily_reports": [],
		"weekly_reports": [], "monthly_reports": [], "monthly_attach_xlsx": 0, "email_format": "HTML Summary",
	}
	base.update(fields)
	return frappe._dict(base)


def rows(*names):
	return [frappe._dict(report=n) for n in names]


class TestActiveFrequencies(unittest.TestCase):
	def test_ticked_schedules_win_in_a_fixed_order(self):
		s = settings(send_monthly=1, send_daily=1, email_frequency="Weekly")
		self.assertEqual(report_email.active_frequencies(s), ["Daily", "Monthly"])

	def test_nothing_ticked_keeps_the_single_frequency(self):
		self.assertEqual(report_email.active_frequencies(settings(email_frequency="Weekly")), ["Weekly"])
		self.assertEqual(report_email.active_frequencies(settings()), [])


class TestIsDue(unittest.TestCase):
	SATURDAY = datetime(2026, 10, 10, 1, 0)
	MONDAY = datetime(2026, 10, 12, 1, 0)

	def test_weekly_uses_the_configured_day_and_defaults_to_monday(self):
		self.assertTrue(tasks.is_due("Weekly", self.SATURDAY, settings(weekly_send_day="Saturday")))
		self.assertFalse(tasks.is_due("Weekly", self.MONDAY, settings(weekly_send_day="Saturday")))
		self.assertTrue(tasks.is_due("Weekly", self.MONDAY, settings()))
		self.assertTrue(tasks.is_due("Weekly", self.MONDAY))

	def test_monthly_day_defaults_to_the_first_and_is_capped_at_28(self):
		self.assertTrue(tasks.is_due("Monthly", datetime(2026, 11, 1, 1), settings()))
		self.assertFalse(tasks.is_due("Monthly", datetime(2026, 11, 2, 1), settings()))
		self.assertTrue(tasks.is_due("Monthly", datetime(2026, 11, 3, 1), settings(monthly_send_day=3)))
		self.assertEqual(tasks.monthly_send_day(settings(monthly_send_day=31)), 28)

	def test_daily_is_always_due_and_unknown_never(self):
		self.assertTrue(tasks.is_due("Daily", self.MONDAY, settings()))
		self.assertFalse(tasks.is_due("Hourly", self.MONDAY, settings()))


class TestConfiguredReports(unittest.TestCase):
	def test_legacy_mode_uses_the_shared_list_then_the_default(self):
		self.assertEqual(report_email.get_configured_reports(settings(email_reports=rows("A", "B")), "Daily"), ["A", "B"])
		self.assertEqual(report_email.get_configured_reports(settings(), "Weekly"),
						 list(report_email.DEFAULT_REPORTS["Weekly"]))

	def test_schedule_mode_ignores_the_shared_daily_list(self):
		s = settings(send_monthly=1, email_reports=rows("Daily Summary"), monthly_reports=rows("X", "Y"))
		self.assertEqual(report_email.get_configured_reports(s, "Monthly"), ["X", "Y"])

	def test_schedule_with_no_own_list_gets_its_default_not_the_shared_one(self):
		s = settings(send_weekly=1, email_reports=rows("Daily Summary"))
		self.assertEqual(report_email.get_configured_reports(s, "Weekly"), list(report_email.DEFAULT_REPORTS["Weekly"]))
		self.assertNotIn("Daily Summary", report_email.get_configured_reports(s, "Weekly"))


if __name__ == "__main__":
	unittest.main()
