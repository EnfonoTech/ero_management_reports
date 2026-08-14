import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from management_reports.utils import metrics as metrics_utils
from management_reports.utils.metrics import (
	build_aggregate,
	evaluate_metric,
	is_datetime_field,
	parse_filters,
	resolve_date_field,
)
from management_reports.utils.report_email import render_metrics


def definition(**kw):
	values = {
		"enabled": 1,
		"label": "Counter",
		"document_type": "Sales Invoice",
		"function": "Count",
		"value_field": None,
		"date_field": None,
		"group_by_field": None,
		"filters_json": None,
	}
	values.update(kw)
	return frappe._dict(values)


class TestDateFieldResolution(FrappeTestCase):
	"""A metric pointed at a stale fieldname must fall back, not query a column
	that no longer exists."""

	def meta(self):
		return frappe.get_meta("Sales Invoice")

	def test_blank_falls_back_to_creation(self):
		self.assertEqual(resolve_date_field(definition(), self.meta()), "creation")

	def test_real_date_field_is_used(self):
		self.assertEqual(
			resolve_date_field(definition(date_field="posting_date"), self.meta()), "posting_date"
		)

	def test_nonexistent_field_falls_back(self):
		self.assertEqual(resolve_date_field(definition(date_field="no_such_field"), self.meta()), "creation")

	def test_non_date_field_falls_back(self):
		"""grand_total is real but numeric — using it as a period bound would be
		nonsense, so it must not be honoured."""
		self.assertEqual(resolve_date_field(definition(date_field="grand_total"), self.meta()), "creation")

	def test_datetime_detection(self):
		self.assertTrue(is_datetime_field(definition(), self.meta()))
		self.assertFalse(is_datetime_field(definition(date_field="posting_date"), self.meta()))


class TestAggregate(FrappeTestCase):
	def setUp(self):
		self.meta = frappe.get_meta("Sales Invoice")
		self.table = frappe.qb.DocType("Sales Invoice")

	def test_count_needs_no_value_field(self):
		self.assertIsNotNone(build_aggregate(definition(), self.meta, self.table))

	def test_sum_on_a_numeric_field_builds(self):
		agg = build_aggregate(definition(function="Sum", value_field="grand_total"), self.meta, self.table)
		self.assertIsNotNone(agg)

	def test_sum_on_a_non_numeric_field_is_refused(self):
		self.assertIsNone(
			build_aggregate(definition(function="Sum", value_field="customer"), self.meta, self.table)
		)

	def test_sum_on_a_missing_field_is_refused(self):
		self.assertIsNone(
			build_aggregate(definition(function="Sum", value_field="nope"), self.meta, self.table)
		)


class TestFilterParsing(FrappeTestCase):
	def meta(self):
		return frappe.get_meta("Sales Invoice")

	def test_valid_object(self):
		self.assertEqual(
			parse_filters(definition(filters_json='{"status": "Paid"}'), self.meta()), {"status": "Paid"}
		)

	def test_unknown_fields_are_dropped_rather_than_reaching_sql(self):
		parsed = parse_filters(definition(filters_json='{"status": "Paid", "made_up_field": 1}'), self.meta())
		self.assertEqual(parsed, {"status": "Paid"})

	def test_docstatus_is_allowed_even_though_it_is_not_a_docfield(self):
		self.assertEqual(
			parse_filters(definition(filters_json='{"docstatus": 1}'), self.meta()), {"docstatus": 1}
		)

	def test_malformed_json_yields_no_filters(self):
		self.assertEqual(parse_filters(definition(filters_json="{not json"), self.meta()), {})

	def test_json_array_is_rejected(self):
		self.assertEqual(parse_filters(definition(filters_json='["status", "Paid"]'), self.meta()), {})

	def test_blank_yields_no_filters(self):
		self.assertEqual(parse_filters(definition(), self.meta()), {})


class TestEvaluateAgainstRealData(FrappeTestCase):
	"""Runs the real query path against Sales Invoice, which exists everywhere."""

	def test_count_returns_a_number(self):
		result = evaluate_metric(
			definition(label="Invoices", date_field="posting_date", filters_json='{"docstatus": 1}'),
			getdate("2000-01-01"),
			getdate("2100-01-01"),
		)

		self.assertEqual(result["label"], "Invoices")
		self.assertFalse(result["is_currency"])
		self.assertEqual(result["value"], frappe.db.count("Sales Invoice", {"docstatus": 1}))

	def test_sum_is_flagged_as_currency(self):
		result = evaluate_metric(
			definition(function="Sum", value_field="grand_total", date_field="posting_date"),
			getdate("2000-01-01"),
			getdate("2100-01-01"),
		)

		self.assertTrue(result["is_currency"])

	def test_breakdown_groups_and_totals_match_the_headline(self):
		result = evaluate_metric(
			definition(
				label="By Status",
				group_by_field="status",
				date_field="posting_date",
				filters_json='{"docstatus": 1}',
			),
			getdate("2000-01-01"),
			getdate("2100-01-01"),
		)

		if not result["breakdown"]:
			self.skipTest("no submitted invoices on this site")

		self.assertLessEqual(sum(item["value"] for item in result["breakdown"]), result["value"])

	def test_empty_period_returns_zero_not_an_error(self):
		result = evaluate_metric(
			definition(date_field="posting_date"), getdate("1990-01-01"), getdate("1990-01-02")
		)

		self.assertEqual(result["value"], 0)

	def test_a_broken_metric_is_skipped_not_fatal(self):
		"""One bad counter must not stop the digest from going out."""
		original = metrics_utils.get_metric_definitions
		metrics_utils.get_metric_definitions = lambda company: [
			definition(label="Bad", document_type="No Such DocType ZZ"),
			definition(label="Good", date_field="posting_date"),
		]
		try:
			results = metrics_utils.evaluate_metrics("ACME", getdate("2000-01-01"), getdate("2100-01-01"))
		finally:
			metrics_utils.get_metric_definitions = original

		self.assertEqual([r["label"] for r in results], ["Good"])


class TestMetricRendering(FrappeTestCase):
	def test_no_metrics_renders_nothing(self):
		self.assertEqual(render_metrics([], "SAR"), "")

	def test_count_renders_as_a_plain_integer(self):
		html = render_metrics([{"label": "Complimentary Meals", "value": 6, "is_currency": False}], "SAR")

		self.assertIn("Complimentary Meals", html)
		self.assertIn(">6<", html)

	def test_breakdown_is_rendered_and_escaped(self):
		html = render_metrics(
			[
				{
					"label": "Complimentary",
					"value": 2,
					"is_currency": False,
					"breakdown": [{"group": "<b>Staff Meal</b>", "value": 2}],
				}
			],
			"SAR",
		)

		self.assertNotIn("<b>Staff Meal</b>", html)
		self.assertIn("&lt;b&gt;", html)

	def test_currency_metric_is_formatted_as_money(self):
		html = render_metrics([{"label": "Given Away", "value": 121, "is_currency": True}], "SAR")

		self.assertIn("Given Away", html)
		self.assertIn("121", html)
