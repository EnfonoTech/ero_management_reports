import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from management_reports.utils import config as config_utils
from management_reports.utils.config import (
	get_branch_display_names,
	get_branch_targets,
	get_company_target,
	get_config,
	get_margin_floor,
)


def app_path(*parts) -> str:
	import management_reports

	root = os.path.dirname(os.path.dirname(os.path.abspath(management_reports.__file__)))
	return os.path.join(root, "management_reports", "management_reports", *parts)


def load_json(*parts) -> dict:
	with open(app_path(*parts)) as handle:
		return json.load(handle)


class TestConfigDegradesWithoutSetup(FrappeTestCase):
	"""A site that never creates a Config must behave exactly as before."""

	def test_no_company_returns_nothing(self):
		self.assertIsNone(get_config(None))
		self.assertEqual(get_branch_targets(None), {})
		self.assertEqual(get_branch_display_names(None), {})
		self.assertEqual(get_company_target(None), 0.0)
		self.assertEqual(get_margin_floor(None), 0.0)

	def test_unknown_company_returns_nothing(self):
		self.assertIsNone(get_config("No Such Company ZZ"))
		self.assertEqual(get_branch_targets("No Such Company ZZ"), {})

	def test_disabled_config_is_ignored(self):
		"""Disabled must mean inert, not partially applied."""
		stub = frappe._dict(
			{
				"monthly_revenue_target": 5000,
				"margin_floor": 20,
				"branch_map": [
					frappe._dict({"branch": "B1", "display_name": "One", "monthly_target": 100, "enabled": 1})
				],
			}
		)
		original = config_utils.get_config
		try:
			config_utils.get_config = lambda company: None
			self.assertEqual(get_branch_targets("ACME"), {})
			config_utils.get_config = lambda company: stub
			self.assertEqual(get_branch_targets("ACME"), {"B1": 100.0})
		finally:
			config_utils.get_config = original


class TestBranchMapReading(FrappeTestCase):
	def stub(self, rows, **doc):
		values = {"monthly_revenue_target": 0, "margin_floor": 0, "branch_map": rows}
		values.update(doc)
		return frappe._dict(values)

	def row(self, branch, **kw):
		values = {"branch": branch, "display_name": None, "manager": None, "monthly_target": 0, "enabled": 1}
		values.update(kw)
		return frappe._dict(values)

	def with_config(self, doc):
		original = config_utils.get_config
		config_utils.get_config = lambda company: doc
		self.addCleanup(lambda: setattr(config_utils, "get_config", original))

	def test_disabled_rows_are_excluded(self):
		self.with_config(
			self.stub([self.row("A", monthly_target=10), self.row("B", monthly_target=20, enabled=0)])
		)
		self.assertEqual(get_branch_targets("ACME"), {"A": 10.0})

	def test_zero_targets_are_excluded_so_no_target_column_appears(self):
		self.with_config(self.stub([self.row("A", monthly_target=0)]))
		self.assertEqual(get_branch_targets("ACME"), {})

	def test_display_name_falls_back_to_branch(self):
		self.with_config(self.stub([self.row("Emar Branch - ACH")]))
		self.assertEqual(get_branch_display_names("ACME"), {"Emar Branch - ACH": "Emar Branch - ACH"})

	def test_display_name_is_used_when_set(self):
		self.with_config(self.stub([self.row("Emar Branch - ACH", display_name="Emar")]))
		self.assertEqual(get_branch_display_names("ACME"), {"Emar Branch - ACH": "Emar"})

	def test_company_target_and_margin_floor(self):
		self.with_config(self.stub([], monthly_revenue_target=25000, margin_floor=35))
		self.assertEqual(get_company_target("ACME"), 25000.0)
		self.assertEqual(get_margin_floor("ACME"), 35.0)


class TestShippedWorkspace(FrappeTestCase):
	"""The workspace is hand-written JSON, so its references are checked here
	rather than discovered as blank cards on a client's desk."""

	def setUp(self):
		self.ws = load_json("workspace", "management_reports", "management_reports.json")
		self.blocks = json.loads(self.ws["content"])

	def test_identity(self):
		self.assertEqual(self.ws["module"], "Management Reports")
		self.assertEqual(self.ws["public"], 1)
		self.assertEqual(self.ws["is_hidden"], 0)
		self.assertEqual(self.ws["label"], self.ws["title"])

	def test_every_report_link_is_flagged_as_a_query_report(self):
		"""Script Reports route through /app/query-report, so is_query_report must
		be 1 — shipped ERPNext workspaces do the same. A 0 here 404s the link."""
		for link in self.ws["links"]:
			if link.get("link_type") == "Report":
				with self.subTest(link=link["link_to"]):
					self.assertEqual(link["is_query_report"], 1)
					self.assertTrue(link.get("report_ref_doctype"))

	def test_every_card_referenced_in_content_has_a_card_break(self):
		breaks = {l["label"] for l in self.ws["links"] if l["type"] == "Card Break"}
		referenced = {b["data"]["card_name"] for b in self.blocks if b["type"] == "card"}

		self.assertEqual(referenced - breaks, set(), "content references a card with no Card Break")

	def test_every_shortcut_referenced_in_content_exists(self):
		defined = {s["label"] for s in self.ws["shortcuts"]}
		referenced = {b["data"]["shortcut_name"] for b in self.blocks if b["type"] == "shortcut"}

		self.assertEqual(referenced - defined, set())

	def test_every_number_card_and_chart_referenced_exists_in_the_app(self):
		for block in self.blocks:
			if block["type"] == "number_card":
				name = block["data"]["number_card_name"]
				folder = name.lower().replace(" ", "_")
				with self.subTest(card=name):
					card = load_json("number_card", folder, folder + ".json")
					self.assertEqual(card["name"], name)
					self.assertEqual(card["module"], "Management Reports")
					self.assertEqual(card["is_standard"], 1)
			if block["type"] == "chart":
				name = block["data"]["chart_name"]
				folder = name.lower().replace(" ", "_")
				with self.subTest(chart=name):
					chart = load_json("dashboard_chart", folder, folder + ".json")
					self.assertEqual(chart["name"], name)
					self.assertEqual(chart["module"], "Management Reports")
					self.assertEqual(chart["is_standard"], 1)

	def test_workspace_tables_agree_with_content_blocks(self):
		table_cards = {c["number_card_name"] for c in self.ws["number_cards"]}
		block_cards = {b["data"]["number_card_name"] for b in self.blocks if b["type"] == "number_card"}
		self.assertEqual(table_cards, block_cards)

		table_charts = {c["chart_name"] for c in self.ws["charts"]}
		block_charts = {b["data"]["chart_name"] for b in self.blocks if b["type"] == "chart"}
		self.assertEqual(table_charts, block_charts)

	def test_linked_reports_are_the_apps_own(self):
		shipped = set()
		base = app_path("report")
		for entry in os.listdir(base):
			path = os.path.join(base, entry, entry + ".json")
			if os.path.exists(path):
				with open(path) as handle:
					shipped.add(json.load(handle)["name"])

		for link in self.ws["links"]:
			if link.get("link_type") == "Report":
				with self.subTest(report=link["link_to"]):
					self.assertIn(link["link_to"], shipped)

	def test_linked_doctypes_are_the_apps_own(self):
		base = app_path("doctype")
		shipped = set()
		for entry in os.listdir(base):
			path = os.path.join(base, entry, entry + ".json")
			if os.path.exists(path):
				with open(path) as handle:
					shipped.add(json.load(handle)["name"])

		for link in self.ws["links"]:
			if link.get("link_type") == "DocType":
				with self.subTest(doctype=link["link_to"]):
					self.assertIn(link["link_to"], shipped)

	def test_page_shortcut_points_at_the_shipped_page(self):
		pages = {s["link_to"] for s in self.ws["shortcuts"] if s["type"] == "Page"}

		self.assertEqual(pages, {"reports-dashboard"})
		self.assertTrue(os.path.exists(app_path("page", "reports_dashboard", "reports_dashboard.json")))


class TestBranchMapSchema(FrappeTestCase):
	def test_branch_is_a_dynamic_link_driven_by_branch_doctype(self):
		"""Hardcoding Cost Center here would undo the whole dimension design."""
		schema = load_json("doctype", "management_report_branch_map", "management_report_branch_map.json")
		fields = {f["fieldname"]: f for f in schema["fields"]}

		self.assertEqual(fields["branch"]["fieldtype"], "Dynamic Link")
		self.assertEqual(fields["branch"]["options"], "branch_doctype")
		self.assertEqual(fields["branch_doctype"]["fieldtype"], "Data")
		self.assertEqual(schema["istable"], 1)

	def test_config_is_unique_per_company(self):
		schema = load_json("doctype", "management_report_config", "management_report_config.json")
		fields = {f["fieldname"]: f for f in schema["fields"]}

		self.assertEqual(schema["autoname"], "field:company")
		self.assertEqual(fields["company"]["unique"], 1)
		self.assertEqual(fields["company"]["reqd"], 1)
