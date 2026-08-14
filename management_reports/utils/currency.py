"""Currency and company display helpers.

Reports used to fall back to a hardcoded "SAR", which silently mislabels every
figure on a UAE or India site. Fall back to the site's own default instead.
"""

import frappe


def get_currency(company: str | None = None) -> str:
	"""Currency for ``company``, else the site default."""
	if company:
		currency = frappe.get_cached_value("Company", company, "default_currency")
		if currency:
			return currency

	return get_site_default_currency()


def get_site_default_currency() -> str:
	"""Site-wide default currency, resolved without guessing a region."""
	try:
		import erpnext

		currency = erpnext.get_default_currency()
		if currency:
			return currency
	except Exception:
		pass

	return frappe.db.get_default("currency") or "USD"


def get_company_abbr(company: str | None = None) -> str:
	"""Company abbreviation, used to shorten branch names in chart labels."""
	if not company:
		return ""

	return frappe.get_cached_value("Company", company, "abbr") or ""


def strip_abbr(value: str | None, abbr: str) -> str:
	"""Drop the trailing " - ABBR" ERPNext appends to Cost Center names."""
	if not value:
		return ""

	if abbr and value.endswith(" - " + abbr):
		return value[: -(len(abbr) + 3)].strip()

	return value
