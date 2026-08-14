"""Evaluate configuration-defined counters for the digest.

These exist so a client-specific number — Kaapqah's complimentary meals, another
site's wastage or voided tickets — can appear in the report email without this
app hardcoding that client's DocTypes.

Every fieldname is re-validated against meta here as well as on save, because a
field can be renamed or removed after the metric was configured, and the values
are interpolated into a query.
"""

import json

import frappe
from frappe.query_builder import Order
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cstr, flt, get_datetime, getdate

from management_reports.utils.config import get_config

NUMERIC_FIELDTYPES = ("Currency", "Float", "Int", "Percent")
DATE_FIELDTYPES = ("Date", "Datetime")
MAX_BREAKDOWN_ROWS = 8


def get_metric_definitions(company: str | None) -> list:
	config = get_config(company)
	if not config:
		return []

	return [row for row in (config.get("metrics") or []) if row.enabled and row.document_type]


def evaluate_metrics(company: str | None, from_date, to_date) -> list:
	"""Return ``[{label, value, is_currency, breakdown}]`` for enabled metrics.

	A metric that cannot be evaluated is skipped and logged rather than taking
	the whole digest down with it — the numbers that do work still go out.
	"""
	results = []

	for definition in get_metric_definitions(company):
		try:
			results.append(evaluate_metric(definition, from_date, to_date))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"Management Reports: metric failed - " + cstr(definition.label),
			)

	return [result for result in results if result]


def evaluate_metric(definition, from_date, to_date) -> dict | None:
	meta = frappe.get_meta(definition.document_type)
	table = frappe.qb.DocType(definition.document_type)

	aggregate = build_aggregate(definition, meta, table)
	if aggregate is None:
		return None

	query = frappe.qb.from_(table).select(aggregate.as_("value"))
	query = apply_period(query, definition, meta, table, from_date, to_date)
	query = apply_filters(query, definition, meta, table)

	rows = query.run(as_dict=True)
	total = flt(rows[0].get("value")) if rows else 0.0

	return {
		"label": definition.label or definition.document_type,
		"value": total,
		"is_currency": definition.function == "Sum",
		"breakdown": build_breakdown(definition, meta, table, from_date, to_date),
	}


def build_aggregate(definition, meta, table):
	if definition.function == "Sum":
		field = meta.get_field(definition.value_field)
		if not field or field.fieldtype not in NUMERIC_FIELDTYPES:
			return None
		return Sum(table[definition.value_field])

	return Count(table.name)


def resolve_date_field(definition, meta) -> str:
	"""Configured date field if it is a real date field, else `creation`."""
	fieldname = cstr(definition.date_field).strip()
	if not fieldname:
		return "creation"

	field = meta.get_field(fieldname)
	if not field or field.fieldtype not in DATE_FIELDTYPES:
		return "creation"

	return fieldname


def is_datetime_field(definition, meta) -> bool:
	fieldname = resolve_date_field(definition, meta)
	if fieldname == "creation":
		return True

	field = meta.get_field(fieldname)

	return bool(field and field.fieldtype == "Datetime")


def apply_period(query, definition, meta, table, from_date, to_date):
	"""Bound the query to the reporting period.

	Datetime fields are compared across the whole day, otherwise a record stamped
	17:54 on the closing day would fall outside a plain date comparison and go
	uncounted.
	"""
	column = table[resolve_date_field(definition, meta)]

	if is_datetime_field(definition, meta):
		start = get_datetime(cstr(getdate(from_date)) + " 00:00:00")
		end = get_datetime(cstr(getdate(to_date)) + " 23:59:59")
		return query.where(column[start:end])

	return query.where(column[getdate(from_date) : getdate(to_date)])


def apply_filters(query, definition, meta, table):
	for fieldname, value in parse_filters(definition, meta).items():
		query = query.where(table[fieldname] == value)

	return query


def parse_filters(definition, meta) -> dict:
	if not definition.filters_json:
		return {}

	try:
		filters = json.loads(definition.filters_json)
	except ValueError:
		return {}

	if not isinstance(filters, dict):
		return {}

	return {
		fieldname: value
		for fieldname, value in filters.items()
		if fieldname in ("name", "owner", "docstatus") or meta.get_field(fieldname)
	}


def build_breakdown(definition, meta, table, from_date, to_date) -> list:
	"""Per-group split, e.g. complimentary meals by reason."""
	fieldname = cstr(definition.group_by_field).strip()
	if not fieldname or not meta.get_field(fieldname):
		return []

	aggregate = build_aggregate(definition, meta, table)
	if aggregate is None:
		return []

	column = table[fieldname]
	query = frappe.qb.from_(table).select(column.as_("group"), aggregate.as_("value"))
	query = apply_period(query, definition, meta, table, from_date, to_date)
	query = apply_filters(query, definition, meta, table)

	rows = (
		query.groupby(column).orderby(aggregate, order=Order.desc).limit(MAX_BREAKDOWN_ROWS).run(as_dict=True)
	)

	return [
		{"group": cstr(row.get("group")) or "-", "value": flt(row.get("value"))}
		for row in rows
		if flt(row.get("value"))
	]
