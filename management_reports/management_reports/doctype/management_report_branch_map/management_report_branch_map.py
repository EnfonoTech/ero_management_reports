from frappe.model.document import Document


class ManagementReportBranchMap(Document):
	"""One row per branch: who owns it, what it is called, what it must hit.

	`branch` is a Dynamic Link so the same schema works whether a site models
	branches as Cost Center, Warehouse or something else — `branch_doctype` is
	filled from Settings by the parent's validate.
	"""

	pass
