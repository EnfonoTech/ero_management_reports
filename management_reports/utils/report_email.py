"""Build and send the scheduled management report email.

The report content is generated as Administrator, so the email covers the whole
company regardless of any branch User Permissions. That is deliberate — the
recipients are named explicitly in Settings, and a digest that silently omitted
branches would be worse than no digest. Per-recipient branch scoping belongs in
the per-subscription work, not here.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	cstr,
	escape_html,
	flt,
	fmt_money,
	format_date,
	get_first_day,
	get_last_day,
	getdate,
	nowdate,
)

from management_reports.utils.currency import get_currency

# Reports whose date filter is a single day rather than a range. base_query
# prefers `date` over from_date/to_date, so passing both would silently collapse
# a monthly report to one day.
SINGLE_DATE_REPORTS = {"Daily Summary"}

# "Collections by Payment Mode" rides along with every digest: the summary says
# what was earned, this says what was actually taken and in what tender, which is
# the figure the counter is reconciled against.
DEFAULT_REPORTS = {
	"Daily": ("Daily Summary", "Collections by Payment Mode"),
	"Weekly": ("Monthly Summary", "Collections by Payment Mode"),
	"Monthly": ("Monthly Summary", "Collections by Payment Mode"),
}

MAX_ROWS_IN_EMAIL = 50


def get_period(frequency: str, as_on=None) -> frappe._dict:
	"""Reporting window for a frequency, always a completed period.

	A daily digest sent at 07:00 reports yesterday, not the empty morning so far.
	"""
	as_on = getdate(as_on or nowdate())
	yesterday = add_days(as_on, -1)

	if frequency == "Daily":
		return frappe._dict({"from_date": yesterday, "to_date": yesterday, "label": format_date(yesterday)})

	if frequency == "Weekly":
		start = add_days(as_on, -7)
		return frappe._dict(
			{
				"from_date": start,
				"to_date": yesterday,
				"label": format_date(start) + " - " + format_date(yesterday),
			}
		)

	last_month_end = add_days(get_first_day(as_on), -1)
	start = get_first_day(last_month_end)
	return frappe._dict(
		{
			"from_date": start,
			"to_date": get_last_day(last_month_end),
			"label": last_month_end.strftime("%B %Y"),
		}
	)


def build_filters(report_name: str, company: str, period) -> dict:
	filters = {"company": company}

	if report_name in SINGLE_DATE_REPORTS:
		filters["date"] = period.to_date
	else:
		filters["from_date"] = period.from_date
		filters["to_date"] = period.to_date

	return filters


def run_report(report_name: str, filters: dict) -> dict:
	"""Execute a report and return its columns, rows and summary tiles."""
	from frappe.desk.query_report import run

	# are_default_filters=False, or a report carrying custom_filters would
	# silently discard the period just computed.
	result = run(
		report_name,
		filters=filters,
		ignore_prepared_report=True,
		are_default_filters=False,
	)

	return {
		"columns": result.get("columns") or [],
		"rows": result.get("result") or [],
		"summary": result.get("report_summary") or [],
	}


def get_configured_reports(settings, frequency: str) -> list:
	selected = [row.report for row in (settings.email_reports or []) if row.report]

	return selected or list(DEFAULT_REPORTS.get(frequency, ()))


def get_recipients(settings) -> list:
	"""Enabled recipient addresses, de-duplicated, order preserved."""
	seen = {}

	for row in settings.recipients or []:
		if not row.enabled or not row.email_id:
			continue
		email = cstr(row.email_id).strip()
		if email:
			seen.setdefault(email.lower(), email)

	return list(seen.values())


def get_company(settings) -> str | None:
	import erpnext

	return settings.email_company or erpnext.get_default_company()


# --- rendering ------------------------------------------------------------


def format_cell(value, column) -> str:
	fieldtype = (column or {}).get("fieldtype")

	if value is None or value == "":
		return ""

	if fieldtype in ("Currency", "Float"):
		return fmt_money(flt(value), currency=(column or {}).get("currency"))
	if fieldtype == "Percent":
		return cstr(round(flt(value), 1)) + "%"
	if fieldtype == "Int":
		return cstr(cint(value))
	if fieldtype == "Date":
		return format_date(value)

	return cstr(value)


def cell_value(row, column, index):
	"""Report rows are dicts for this app's reports, lists for some others."""
	if isinstance(row, dict):
		return row.get(column.get("fieldname"))

	return row[index] if index < len(row) else None


def render_summary(summary) -> str:
	if not summary:
		return ""

	cells = []
	for tile in summary:
		formatted = format_cell(
			tile.get("value"), {"fieldtype": tile.get("datatype"), "currency": tile.get("currency")}
		)
		cells.append(
			'<td style="padding:10px 14px;border:1px solid #e2e5e9;background:#f7f8f9">'
			'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">'
			+ escape_html(cstr(tile.get("label")))
			+ '</div><div style="font-size:17px;font-weight:600;color:#111827;margin-top:2px">'
			+ escape_html(formatted)
			+ "</div></td>"
		)

	return (
		'<table role="presentation" cellspacing="0" cellpadding="0" '
		'style="border-collapse:collapse;margin:0 0 14px"><tr>' + "".join(cells) + "</tr></table>"
	)


def render_table(columns, rows) -> str:
	if not rows:
		return '<p style="color:#6b7280;margin:0 0 18px">' + _("No data for this period.") + "</p>"

	head = "".join(
		'<th style="padding:8px 10px;border:1px solid #e2e5e9;background:#f0f2f4;'
		'text-align:left;font-size:12px;color:#374151;white-space:nowrap">'
		+ escape_html(cstr(column.get("label")))
		+ "</th>"
		for column in columns
	)

	body = []
	for row in rows[:MAX_ROWS_IN_EMAIL]:
		cells = []
		for index, column in enumerate(columns):
			numeric = column.get("fieldtype") in ("Currency", "Float", "Int", "Percent")
			cells.append(
				'<td style="padding:7px 10px;border:1px solid #e2e5e9;font-size:12px;color:#111827;'
				"text-align:"
				+ ("right" if numeric else "left")
				+ '">'
				+ escape_html(format_cell(cell_value(row, column, index), column))
				+ "</td>"
			)
		body.append("<tr>" + "".join(cells) + "</tr>")

	truncated = ""
	if len(rows) > MAX_ROWS_IN_EMAIL:
		truncated = (
			'<p style="color:#6b7280;font-size:12px;margin:6px 0 0">'
			+ cstr(len(rows))
			+ " "
			+ _("rows in total — truncated for email. Full data is in the attachment or on the dashboard.")
			+ "</p>"
		)

	return (
		'<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%;'
		'margin:0 0 8px"><thead><tr>'
		+ head
		+ "</tr></thead><tbody>"
		+ "".join(body)
		+ "</tbody></table>"
		+ truncated
	)


def render_metrics(metrics: list, currency: str) -> str:
	"""Configuration-defined counters, each with an optional breakdown."""
	if not metrics:
		return ""

	cells = []
	for metric in metrics:
		value = (
			fmt_money(flt(metric["value"]), currency=currency)
			if metric.get("is_currency")
			else cstr(cint(metric["value"]))
		)

		breakdown = ""
		if metric.get("breakdown"):
			parts = [
				escape_html(item["group"])
				+ " "
				+ (
					fmt_money(flt(item["value"]), currency=currency)
					if metric.get("is_currency")
					else cstr(cint(item["value"]))
				)
				for item in metric["breakdown"]
			]
			breakdown = (
				'<div style="font-size:11px;color:#6b7280;margin-top:3px">' + " · ".join(parts) + "</div>"
			)

		cells.append(
			'<td style="padding:10px 14px;border:1px solid #e2e5e9;background:#f7f8f9;vertical-align:top">'
			'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">'
			+ escape_html(cstr(metric["label"]))
			+ '</div><div style="font-size:17px;font-weight:600;color:#111827;margin-top:2px">'
			+ escape_html(value)
			+ "</div>"
			+ breakdown
			+ "</td>"
		)

	return (
		'<h3 style="font-size:15px;color:#111827;margin:22px 0 8px">' + _("Other Counters") + "</h3>"
		'<table role="presentation" cellspacing="0" cellpadding="0" '
		'style="border-collapse:collapse;margin:0 0 14px"><tr>' + "".join(cells) + "</tr></table>"
	)


def render_email(company: str, frequency: str, period, sections: list, metrics: list | None = None) -> str:
	blocks = []
	for section in sections:
		blocks.append(
			'<h3 style="font-size:15px;color:#111827;margin:22px 0 8px">'
			+ escape_html(section["report"])
			+ "</h3>"
			+ render_summary(section["summary"])
			+ render_table(section["columns"], section["rows"])
		)

	return (
		'<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
		'max-width:760px">'
		'<h2 style="font-size:18px;color:#0f3460;margin:0 0 2px">'
		+ escape_html(company or "")
		+ " - "
		+ _(frequency)
		+ " "
		+ _("Report")
		+ "</h2>"
		'<p style="color:#6b7280;margin:0 0 4px;font-size:13px">'
		+ escape_html(cstr(period.label))
		+ "</p>"
		+ "".join(blocks)
		+ render_metrics(metrics or [], get_currency(company))
		+ '<p style="color:#9ca3af;font-size:11px;margin:24px 0 0;border-top:1px solid #e2e5e9;'
		'padding-top:10px">' + _("Sent automatically by Management Reports.") + "</p></div>"
	)


def build_xlsx(sections: list) -> bytes | None:
	"""All reports concatenated into one sheet, each under its own heading."""
	from frappe.utils.xlsxutils import make_xlsx

	data = []
	for section in sections:
		data.append([section["report"]])
		data.append([cstr(column.get("label")) for column in section["columns"]])
		for row in section["rows"]:
			data.append(
				[
					format_cell(cell_value(row, column, index), column)
					for index, column in enumerate(section["columns"])
				]
			)
		data.append([])

	if not data:
		return None

	return make_xlsx(data, "Management Reports").getvalue()


# --- orchestration --------------------------------------------------------


def build_digest(settings, frequency: str, as_on=None) -> frappe._dict:
	"""Assemble everything needed to send, without sending."""
	company = get_company(settings)
	if not company:
		frappe.throw(_("No company configured. Set one in Management Reports Settings."))

	period = get_period(frequency, as_on)
	reports = get_configured_reports(settings, frequency)

	if not reports:
		frappe.throw(_("No reports selected to send."))

	sections = []
	failed = []
	for report_name in reports:
		try:
			result = run_report(report_name, build_filters(report_name, company, period))
		except Exception:
			# One broken report must not sink the whole digest.
			frappe.log_error(
				frappe.get_traceback(), "Management Reports: digest report failed - " + report_name
			)
			failed.append(report_name)
			continue

		sections.append(
			{
				"report": report_name,
				"columns": result["columns"],
				"rows": result["rows"],
				"summary": result["summary"],
			}
		)

	if not sections:
		frappe.throw(_("Every selected report failed to run. See the Error Log."))

	from management_reports.utils.metrics import evaluate_metrics

	metrics = evaluate_metrics(company, period.from_date, period.to_date)

	return frappe._dict(
		{
			"company": company,
			"currency": get_currency(company),
			"period": period,
			"sections": sections,
			"metrics": metrics,
			"failed": failed,
			"subject": company + " - " + _(frequency) + " " + _("Report") + " - " + cstr(period.label),
			"message": render_email(company, frequency, period, sections, metrics),
		}
	)


def send_digest(settings, frequency: str, recipients: list, as_on=None) -> frappe._dict:
	digest = build_digest(settings, frequency, as_on)
	fmt = settings.email_format or "HTML Summary"
	attachments = []

	if fmt in ("XLSX Attachment", "Both"):
		content = build_xlsx(digest.sections)
		if content:
			attachments.append(
				{
					"fname": "management-report-" + cstr(digest.period.to_date) + ".xlsx",
					"fcontent": content,
				}
			)

	message = digest.message
	if fmt == "XLSX Attachment":
		message = '<p style="font-family:sans-serif">' + _("Your report is attached.") + "</p>"

	frappe.sendmail(
		recipients=recipients,
		subject=digest.subject,
		message=message,
		attachments=attachments,
		reference_doctype=settings.doctype,
		reference_name=settings.name,
		now=True,
	)

	return digest
