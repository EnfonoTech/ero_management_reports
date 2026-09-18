"""Turn off the grid total row on the reports that carry a Percent column.

The JSON change alone cannot reach a site that already has these reports.
``frappe/modules/import_file.py`` line 31 lists

    "Report": ["disabled", "prepared_report", "add_total_row"]

as fields PRESERVED from the existing document on re-import — deliberately, because
users toggle them in the UI and an app update should not stomp that choice. So
``import_file_by_path(..., force=True)`` returns True, advances ``modified``, and
still leaves ``add_total_row`` exactly as it was. Verified live on trading-demo:
file 0, DB 1, import returned True.

Only reports whose grid shows a Percent column are touched. Frappe totals such a
column with an unweighted mean, which is not a meaningful aggregate of a margin or
a share — on trading-demo it printed Margin 15.37% and Achieved 391.28% against
real figures of 22.39% and 130.85%.
"""

import frappe

REPORTS = [
	"Branch Sales Dashboard",
	"Customer Analysis",
	"Daily Summary",
	"Monthly Summary",
]


def execute():
	for name in REPORTS:
		if not frappe.db.exists("Report", name):
			continue
		if frappe.db.get_value("Report", name, "add_total_row"):
			frappe.db.set_value("Report", name, "add_total_row", 0, update_modified=False)
