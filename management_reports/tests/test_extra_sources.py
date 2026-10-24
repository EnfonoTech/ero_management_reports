import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from management_reports.management_reports.page.reports_dashboard import reports_dashboard
from management_reports.management_reports.report.branch_sales_dashboard import branch_sales_dashboard
from management_reports.management_reports.report.customer_analysis import customer_analysis
from management_reports.management_reports.report.daily_summary import daily_summary
from management_reports.management_reports.report.monthly_summary import monthly_summary
from management_reports.management_reports.report.top_selling_items import top_selling_items
from management_reports.utils import sources
from management_reports.utils.settings import SETTINGS_DOCTYPE

SALE = "MR Test Sale"
SALE_ITEM = "MR Test Sale Item"
DAY = "2001-02-03"  # no real invoice exists on this day, so only the test sales show up in the reports


def make_sale_doctypes():
	"""A submittable sale document shaped like a counter sale: whole-bill discount, cost per row, returns."""
	if frappe.db.exists("DocType", SALE):
		return

	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": SALE_ITEM,
			"module": "Management Reports",
			"custom": 1,
			"istable": 1,
			"fields": [
				{"fieldname": "item_code", "fieldtype": "Link", "options": "Item", "label": "Item Code"},
				{"fieldname": "item_name", "fieldtype": "Data", "label": "Item Name"},
				{"fieldname": "qty", "fieldtype": "Float", "label": "Qty"},
				{"fieldname": "amount", "fieldtype": "Currency", "label": "Amount"},
				{"fieldname": "cost_amount", "fieldtype": "Currency", "label": "Cost"},
			],
		}
	).insert()

	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": SALE,
			"module": "Management Reports",
			"custom": 1,
			"is_submittable": 1,
			"autoname": "hash",
			"fields": [
				{"fieldname": "company", "fieldtype": "Link", "options": "Company", "label": "Company"},
				{
					"fieldname": "cost_center",
					"fieldtype": "Link",
					"options": "Cost Center",
					"label": "Cost Center",
				},
				{"fieldname": "posting_date", "fieldtype": "Date", "label": "Date"},
				{"fieldname": "customer", "fieldtype": "Link", "options": "Customer", "label": "Customer"},
				{"fieldname": "customer_name", "fieldtype": "Data", "label": "Customer Name"},
				{"fieldname": "is_return", "fieldtype": "Check", "label": "Is Return"},
				{"fieldname": "items", "fieldtype": "Table", "options": SALE_ITEM, "label": "Items"},
				{"fieldname": "total_before_discount", "fieldtype": "Currency", "label": "Before Discount"},
				{"fieldname": "total_selling_value", "fieldtype": "Currency", "label": "Net"},
			],
			"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1}],
		}
	).insert()


class TestExtraSources(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_sale_doctypes()
		cls.company = frappe.db.get_value("Company", {}, "name")
		cls.cost_center = frappe.db.get_value("Cost Center", {"company": cls.company, "is_group": 0}, "name")
		cls.items = frappe.get_all("Item", filters={"disabled": 0}, pluck="name", limit=2)
		cls.customers = frappe.get_all("Customer", pluck="name", limit=2)
		if not (cls.company and cls.cost_center and len(cls.items) == 2 and len(cls.customers) == 2):
			raise unittest.SkipTest("site has no company, cost center, two items and two customers")
		cls.name_of = {item: frappe.db.get_value("Item", item, "item_name") for item in cls.items}
		cls.customer_name_of = {c: frappe.db.get_value("Customer", c, "customer_name") for c in cls.customers}

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		for doctype in (SALE, SALE_ITEM):
			if frappe.db.exists("DocType", doctype):
				frappe.delete_doc("DocType", doctype, force=1)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		sources.clear_source_cache()

	def tearDown(self):
		# Sales and settings from one test must not leak into the next: they share a single day.
		frappe.db.rollback()
		sources.clear_source_cache()

	# ---- helpers
	def source_row(self, **overrides):
		row = {
			"source_doctype": SALE,
			"item_doctype": SALE_ITEM,
			"total_field": "total_selling_value",
			"gross_total_field": "total_before_discount",
			"item_cost_field": "cost_amount",
		}
		row.update(overrides)
		return row

	def configure(self, *rows):
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		settings.set("extra_sales_sources", list(rows))
		settings.save()
		sources.clear_source_cache()

	def make_sale(self, customer, rows, net, is_return=0):
		"""rows: [(item index, qty, amount, cost)]; ``net`` is what was charged after the discount."""
		doc = frappe.new_doc(SALE)
		doc.update(
			{
				"company": self.company,
				"cost_center": self.cost_center,
				"posting_date": DAY,
				"customer": customer,
				"customer_name": self.customer_name_of[customer],
				"is_return": is_return,
				"total_before_discount": sum(amount for _i, _q, amount, _c in rows),
				"total_selling_value": net,
			}
		)
		for index, qty, amount, cost in rows:
			item = self.items[index]
			doc.append(
				"items",
				{
					"item_code": item,
					"item_name": self.name_of[item],
					"qty": qty,
					"amount": amount,
					"cost_amount": cost,
				},
			)
		doc.insert()
		doc.submit()
		return doc

	def filters(self):
		return {"company": self.company, "from_date": DAY, "to_date": DAY}

	# ---- configuration
	def test_without_an_additional_source_reports_run_on_sales_invoice_only(self):
		self.configure()
		self.assertEqual(len(sources.get_contexts(self.filters())), 1)
		self.assertFalse(sources.has_extra_sources())

		ctx = sources.get_contexts(self.filters())[0]
		self.assertEqual(ctx.source, "Sales Invoice")
		self.assertFalse(ctx.multi)
		self.assertEqual(reports_dashboard.get_period_totals(self.company, DAY, DAY).revenue, 0)

	def test_settings_refuses_a_source_whose_fields_do_not_line_up(self):
		for bad in (
			self.source_row(total_field="no_such_field"),
			self.source_row(item_cost_field="item_name"),  # a text field is not a cost
			self.source_row(item_doctype="Sales Invoice Item"),  # not the item table of this document
			self.source_row(source_doctype="Customer"),  # not submittable
		):
			with self.subTest(bad=bad):
				with self.assertRaises(frappe.ValidationError):
					self.configure(bad)

		settings = frappe.get_single(SETTINGS_DOCTYPE)
		self.assertEqual(len(settings.extra_sales_sources), 0)

	def test_a_row_that_stops_being_valid_is_skipped_not_fatal(self):
		self.configure(self.source_row())
		self.assertEqual(len(sources.get_extra_sources()), 1)

		frappe.db.set_value(
			"Management Reports Extra Source",
			{"parent": SETTINGS_DOCTYPE},
			"total_field",
			"gone_since_saving",
		)
		sources.clear_source_cache()
		self.assertEqual(sources.get_extra_sources(), [])
		reports_dashboard.get_period_totals(self.company, DAY, DAY)  # still runs on Sales Invoice alone

	# ---- numbers
	def test_dashboard_adds_net_sales_invoices_and_distinct_customers(self):
		self.make_sale(self.customers[0], [(0, 2, 600, 200), (1, 1, 400, 150)], net=900)
		self.make_sale(self.customers[0], [(0, 1, 100, 40)], net=100)
		self.configure(self.source_row())

		totals = reports_dashboard.get_period_totals(self.company, DAY, DAY)

		self.assertEqual(
			flt(totals.revenue), 1000
		)  # the 900 charged plus 100, not the 1000 + 100 before discount
		self.assertEqual(totals.invoices, 2)
		self.assertEqual(totals.customers, 1)  # one customer, two sales
		self.assertEqual(reports_dashboard.get_active_branches(self.company, DAY, DAY), 1)

	def test_branch_report_scales_item_revenue_by_the_discount_and_carries_cost(self):
		self.make_sale(self.customers[0], [(0, 2, 600, 200), (1, 1, 400, 150)], net=900)
		self.configure(self.source_row())

		_cols, data, *_ = branch_sales_dashboard.execute(self.filters())

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["branch"], self.cost_center)
		self.assertEqual(flt(data[0]["revenue"]), 900)  # item amounts add to 1000, the customer paid 900
		self.assertEqual(flt(data[0]["cogs"]), 350)
		self.assertEqual(flt(data[0]["profit"]), 550)
		self.assertEqual((data[0]["invoices"], data[0]["customers"]), (1, 1))

	def test_a_return_reduces_the_totals(self):
		self.make_sale(self.customers[0], [(0, 2, 600, 200)], net=600)
		self.make_sale(self.customers[0], [(0, -1, -300, -100)], net=-300, is_return=1)
		self.configure(self.source_row())

		_cols, data, *_ = branch_sales_dashboard.execute(self.filters())
		self.assertEqual((flt(data[0]["revenue"]), flt(data[0]["cogs"])), (300, 100))

		_cols, daily, *_ = daily_summary.execute({"company": self.company, "date": DAY})
		self.assertEqual(len(daily), 1)
		self.assertEqual(flt(daily[0]["income"]), 300)
		# Daily Summary adds the day's returns to expenses, as it does for credit notes.
		self.assertEqual(flt(daily[0]["expenses"]), 100 + 300)

	def test_item_and_customer_reports_merge_across_sources(self):
		self.make_sale(self.customers[0], [(0, 2, 600, 200), (1, 1, 400, 150)], net=900)
		self.make_sale(self.customers[1], [(0, 1, 300, 100)], net=300)
		self.configure(self.source_row())

		_cols, items, *_ = top_selling_items.execute({**self.filters(), "limit": 5})
		by_item = {row["item_code"]: row for row in items}
		first, second = self.items
		self.assertEqual((flt(by_item[first]["qty"]), by_item[first]["invoices"]), (3, 2))
		# 600 scaled by 900/1000 plus the undiscounted 300
		self.assertEqual(flt(by_item[first]["revenue"]), 840)
		self.assertEqual(flt(by_item[first]["cogs"]), 300)
		self.assertEqual(flt(by_item[second]["revenue"]), 360)
		self.assertEqual([row["rank"] for row in items], list(range(1, len(items) + 1)))

		_cols, customers, *_ = customer_analysis.execute(self.filters())
		by_customer = {row["customer"]: row for row in customers}
		self.assertEqual(flt(by_customer[self.customers[0]]["revenue"]), 900)
		self.assertEqual(flt(by_customer[self.customers[1]]["revenue"]), 300)
		self.assertEqual(round(sum(row["share"] for row in customers)), 100)

	def test_monthly_summary_groups_the_source_into_its_month(self):
		self.make_sale(self.customers[0], [(0, 1, 500, 100)], net=500)
		self.configure(self.source_row())

		_cols, data, *_ = monthly_summary.execute(self.filters())

		self.assertEqual([row["month_key"] for row in data], ["2001-02"])
		self.assertEqual(
			(flt(data[0]["income"]), flt(data[0]["expenses"]), flt(data[0]["profit"])), (500, 100, 400)
		)

	def test_without_cogs_the_extra_source_adds_no_cost_columns(self):
		self.make_sale(self.customers[0], [(0, 1, 500, 100)], net=500)
		self.configure(self.source_row())
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "cogs_source", "None")
		try:
			columns, data, *_ = branch_sales_dashboard.execute(self.filters())
			self.assertNotIn("cogs", [column["fieldname"] for column in columns])
			self.assertEqual(flt(data[0]["revenue"]), 500)
			self.assertNotIn("cogs", data[0])
		finally:
			frappe.db.set_single_value(SETTINGS_DOCTYPE, "cogs_source", "Item Valuation")

	def test_merge_rows_adds_sums_and_keeps_the_first_label(self):
		rows = [
			{"branch": "A", "name": "", "revenue": 10.5, "cogs": None},
			{"branch": "A", "name": "Alpha", "revenue": 5, "cogs": 2},
			{"branch": "B", "name": "Beta", "revenue": 1},
		]
		merged = sources.merge_rows(rows, ("branch",), ("revenue", "cogs"))
		by_branch = {row["branch"]: row for row in merged}
		self.assertEqual(
			(by_branch["A"]["revenue"], by_branch["A"]["cogs"], by_branch["A"]["name"]), (15.5, 2, "Alpha")
		)
		self.assertEqual(by_branch["B"]["revenue"], 1)
		self.assertNotIn("cogs", by_branch["B"])
