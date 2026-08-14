import inspect
import json
import os
from typing import ClassVar

import frappe
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase


def doctype_dirs():
	import management_reports

	root = os.path.dirname(os.path.dirname(os.path.abspath(management_reports.__file__)))
	base = os.path.join(root, "management_reports", "management_reports", "doctype")

	for entry in sorted(os.listdir(base)):
		path = os.path.join(base, entry)
		if os.path.isdir(path) and os.path.exists(os.path.join(path, entry + ".json")):
			yield entry, path


class TestControllersDoNotShadowDocument(FrappeTestCase):
	"""A controller method that shadows a Document attribute breaks every save.

	`meta` is the trap: BaseDocument.__init__ calls `self.meta.get_table_fields()`,
	so defining `def meta(self)` on a controller raises
	AttributeError: 'function' object has no attribute 'get_table_fields'
	the moment a row is appended — long after the code looks fine.
	"""

	RESERVED: ClassVar[set] = {
		"meta",
		"flags",
		"name",
		"doctype",
		"parent",
		"parenttype",
		"parentfield",
		"idx",
		"get",
		"set",
		"save",
		"insert",
		"delete",
		"reload",
		"db_set",
		"db_insert",
		"db_update",
		"run_method",
		"get_doc_before_save",
		"as_dict",
		"append",
		"precision",
		"get_valid_dict",
	}

	def test_no_controller_shadows_a_document_attribute(self):
		for entry, path in doctype_dirs():
			controller_path = os.path.join(path, entry + ".py")
			if not os.path.exists(controller_path):
				continue

			module = frappe.get_module("management_reports.management_reports.doctype." + entry + "." + entry)
			classes = [
				obj
				for _, obj in inspect.getmembers(module, inspect.isclass)
				if issubclass(obj, Document) and obj is not Document and obj.__module__ == module.__name__
			]

			for klass in classes:
				own = {
					name
					for name, value in vars(klass).items()
					if not name.startswith("__") and callable(value)
				}
				clash = own & self.RESERVED
				with self.subTest(doctype=entry, klass=klass.__name__):
					self.assertEqual(
						clash, set(), klass.__name__ + " shadows Document attribute(s): " + str(clash)
					)


class TestControllersAreWired(FrappeTestCase):
	def test_every_doctype_json_has_a_controller_module(self):
		"""A missing controller file makes the DocType unusable at runtime."""
		for entry, path in doctype_dirs():
			with self.subTest(doctype=entry):
				self.assertTrue(
					os.path.exists(os.path.join(path, entry + ".py")),
					entry + " has no controller",
				)
				self.assertTrue(
					os.path.exists(os.path.join(path, "__init__.py")),
					entry + " is not a package",
				)

	def test_every_doctype_declares_our_module(self):
		for entry, path in doctype_dirs():
			with open(os.path.join(path, entry + ".json")) as handle:
				schema = json.load(handle)
			with self.subTest(doctype=entry):
				self.assertEqual(schema["module"], "Management Reports")

	def test_child_tables_are_marked_istable_and_carry_no_permissions(self):
		for entry, path in doctype_dirs():
			with open(os.path.join(path, entry + ".json")) as handle:
				schema = json.load(handle)

			if not schema.get("istable"):
				continue

			with self.subTest(doctype=entry):
				self.assertEqual(schema.get("permissions", []), [])

	def test_controllers_import_cleanly(self):
		for entry, _path in doctype_dirs():
			with self.subTest(doctype=entry):
				frappe.get_module("management_reports.management_reports.doctype." + entry + "." + entry)
