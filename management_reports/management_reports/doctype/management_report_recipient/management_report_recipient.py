import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, validate_email_address


class ManagementReportRecipient(Document):
	def validate(self):
		self.fill_email_from_user()
		self.validate_email()

	def fill_email_from_user(self):
		if self.user and not self.email_id:
			self.email_id = frappe.db.get_value("User", self.user, "email")

	def validate_email(self):
		"""Reject a bad address at entry.

		A malformed recipient makes the whole scheduled send fail, and it fails
		in a background job where nobody is watching — so it has to be caught on
		the form instead.
		"""
		if not self.email_id:
			frappe.throw(
				_("Set a user or an email address on every recipient row."),
				title=_("Recipient Incomplete"),
			)

		self.email_id = cstr(self.email_id).strip()
		validate_email_address(self.email_id, throw=True)
