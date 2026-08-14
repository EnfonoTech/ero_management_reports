"""Scheduled report delivery.

The cron entry runs hourly and does almost nothing; the real work is enqueued so
a slow report cannot block the scheduler. Sends are idempotent through
Management Report Run Log: the worker re-checks for a Success row before doing
anything, because a digest emailed twice to a client's management is not
recoverable and job retries do happen.
"""

import time

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_weekday, now_datetime, nowdate

from management_reports.management_reports.permissions import check_access
from management_reports.utils.report_email import get_recipients, send_digest
from management_reports.utils.settings import SETTINGS_DOCTYPE

RUN_LOG = "Management Report Run Log"
WEEKLY_SEND_DAY = "Monday"
MONTHLY_SEND_DAY = 1


def send_scheduled_reports():
	"""Hourly cron entry. Enqueues the digest when this hour is the configured one."""
	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)

	if not settings.auto_email_enabled:
		return

	frequency = settings.email_frequency
	if not frequency:
		return

	now = now_datetime()
	if now.hour != cint(settings.email_hour):
		return

	if not is_due(frequency, now):
		return

	if already_sent(frequency, nowdate()):
		return

	frappe.enqueue(
		"management_reports.management_reports.tasks.run_digest",
		queue="long",
		timeout=1500,
		enqueue_after_commit=True,
		job_name="mgmt_report_digest_" + frequency + "_" + cstr(nowdate()),
		frequency=frequency,
	)


def is_due(frequency: str, now) -> bool:
	if frequency == "Daily":
		return True
	if frequency == "Weekly":
		return get_weekday(now) == WEEKLY_SEND_DAY
	if frequency == "Monthly":
		return now.day == MONTHLY_SEND_DAY

	return False


def already_sent(frequency: str, run_date) -> bool:
	return bool(
		frappe.db.exists(RUN_LOG, {"frequency": frequency, "run_date": run_date, "status": "Success"})
	)


def run_digest(frequency: str, as_on=None, force: bool = False):
	"""Send one digest and log the outcome. Safe to call twice."""
	run_date = nowdate()

	# Re-checked here, not only in the enqueuer: retries and duplicate jobs both
	# arrive straight at this function.
	if not force and already_sent(frequency, run_date):
		return

	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	recipients = get_recipients(settings)

	if not recipients:
		log_run(frequency, run_date, "Skipped", error=_("No enabled recipients configured."))
		return

	started = time.monotonic()
	try:
		digest = send_digest(settings, frequency, recipients)
	except Exception:
		frappe.db.rollback()
		log_run(frequency, run_date, "Failed", error=frappe.get_traceback(), recipients=len(recipients))
		frappe.log_error(frappe.get_traceback(), "Management Reports: digest send failed")
		return

	log_run(
		frequency,
		run_date,
		"Success",
		company=digest.company,
		recipients=len(recipients),
		duration_ms=cint((time.monotonic() - started) * 1000),
		reports=[section["report"] for section in digest.sections],
		error=describe_partial_failure(digest),
	)


def describe_partial_failure(digest) -> str | None:
	if not digest.failed:
		return None

	return _("These reports failed and were left out: ") + ", ".join(digest.failed)


def log_run(
	frequency,
	run_date,
	status,
	company=None,
	recipients=0,
	duration_ms=0,
	reports=None,
	error=None,
):
	frappe.get_doc(
		{
			"doctype": RUN_LOG,
			"frequency": frequency,
			"run_date": run_date,
			"status": status,
			"company": company,
			"recipient_count": recipients,
			"duration_ms": duration_ms,
			"reports_sent": ", ".join(reports or []),
			"error_message": error,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()


# --- test / manual triggers ----------------------------------------------


@frappe.whitelist()
def send_test_email(recipients=None, frequency=None):
	"""Send the digest right now, to verify configuration end to end.

	Logged as frequency "Test" so it can never satisfy the idempotency check for
	a real scheduled run, and so a test cannot suppress that day's real send.
	"""
	frappe.only_for("System Manager")

	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	frequency = frequency or settings.email_frequency or "Daily"

	targets = parse_recipients(recipients) or get_recipients(settings)
	if not targets:
		frappe.throw(
			_("Add at least one recipient in Settings, or pass an address to test with."),
			title=_("No Recipients"),
		)

	started = time.monotonic()
	digest = send_digest(settings, frequency, targets)

	log_run(
		"Test",
		nowdate(),
		"Success",
		company=digest.company,
		recipients=len(targets),
		duration_ms=cint((time.monotonic() - started) * 1000),
		reports=[section["report"] for section in digest.sections],
		error=describe_partial_failure(digest),
	)

	return {
		"ok": True,
		"recipients": targets,
		"subject": digest.subject,
		"reports": [section["report"] for section in digest.sections],
		"failed": digest.failed,
		"period": cstr(digest.period.label),
	}


def parse_recipients(recipients) -> list:
	"""Accept a list, a JSON array, or a comma/semicolon separated string."""
	if not recipients:
		return []

	if isinstance(recipients, str):
		recipients = frappe.parse_json(recipients) if recipients.strip().startswith("[") else recipients
	if isinstance(recipients, str):
		recipients = recipients.replace(";", ",").split(",")

	return [cstr(value).strip() for value in recipients if cstr(value).strip()]


@frappe.whitelist()
def preview_digest(frequency=None):
	"""Render the digest without sending it — the safe half of the test button."""
	check_access()

	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	frequency = frequency or settings.email_frequency or "Daily"

	from management_reports.utils.report_email import build_digest

	digest = build_digest(settings, frequency)

	return {
		"subject": digest.subject,
		"message": digest.message,
		"period": cstr(digest.period.label),
		"reports": [section["report"] for section in digest.sections],
		"failed": digest.failed,
		"recipients": get_recipients(settings),
	}


@frappe.whitelist()
def run_digest_now(frequency=None):
	"""Force a real scheduled run immediately, bypassing the hour check."""
	frappe.only_for("System Manager")

	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	frequency = frequency or settings.email_frequency or "Daily"

	frappe.enqueue(
		"management_reports.management_reports.tasks.run_digest",
		queue="long",
		timeout=1500,
		job_name="mgmt_report_digest_manual_" + frequency + "_" + cstr(nowdate()),
		frequency=frequency,
		force=True,
	)

	return {"queued": True, "frequency": frequency}
