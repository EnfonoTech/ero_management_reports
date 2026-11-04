import os
import re
import unittest

# Frappe globals a page script must never redefine: page scripts run in the global scope, so a top-level
# `function format_currency` replaces Frappe's for the whole desk session (SAR 10.0K on every form and report).
FRAPPE_GLOBALS = ("format_currency", "format_number", "format_value", "flt", "cint", "cstr", "__", "fmt_money")


class TestPageScripts(unittest.TestCase):
	def test_page_scripts_do_not_redefine_frappe_globals(self):
		root = os.path.join(os.path.dirname(__file__), "..", "management_reports", "page")
		offenders = []
		for folder, _dirs, files in os.walk(root):
			for name in files:
				if not name.endswith(".js"):
					continue
				path = os.path.join(folder, name)
				source = open(path, encoding="utf-8").read()
				for fn in FRAPPE_GLOBALS:
					if re.search(rf"^(function\s+{re.escape(fn)}\s*\(|(var|let|const)\s+{re.escape(fn)}\b)", source, re.M):
						offenders.append(f"{os.path.relpath(path, root)}: {fn}")
		self.assertEqual(offenders, [])
