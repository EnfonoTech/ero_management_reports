from frappe.model.document import Document


class ManagementReportRunLog(Document):
	"""One row per scheduled-email attempt.

	Exists to make sends idempotent: the worker checks for a Success row before
	doing anything, so a retried or duplicated job cannot email a client's
	management twice. Also the only audit trail for a job nobody watches.
	"""

	pass
