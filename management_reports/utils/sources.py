"""Sales sources beyond Sales Invoice.

Some sites record part of their sales in another document, for example a counter
sale that carries no tax and is never invoiced. Management Reports Settings lists
such documents under "Additional Sales Sources"; every report then reads Sales
Invoice *and* each listed source, and adds the two together.

Nothing here changes a site with an empty list: ``get_contexts`` returns the plain
Sales Invoice context, and ``collect`` runs the report's builder once on it.

How a source plugs in: ``base_query`` hands reports a context whose members name
what they aggregate (``amount``, ``cost``, ``qty``, ``doc_total``, ``date_column``
...). A source builds the same members from its own columns, so a report is written
once and run once per context. ``collect`` merges the per-context rows by the
report's group keys. Everything that reaches SQL is a field name validated against
doctype meta, never raw settings text.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.utils import flt

from management_reports.utils.dimensions import get_branch_dimension
from management_reports.utils.query import apply_date_range_on, base_query
from management_reports.utils.scope import apply_branch_scope
from management_reports.utils.settings import SETTINGS_DOCTYPE

SOURCE_DOCTYPE = "Management Reports Extra Source"

CURRENCY_TYPES = ("Currency", "Float")
NAME_TYPES = ("Data", "Small Text", "Text", "Read Only")

DEFAULTS = {
	"date_field": "posting_date",
	"company_field": "company",
	"customer_field": "customer",
	"customer_name_field": "customer_name",
	"return_field": "is_return",
	"item_qty_field": "qty",
	"item_amount_field": "amount",
}


# --- configuration --------------------------------------------------------


def get_source_rows() -> list:
	"""Configured rows, in order; [] before the table exists (install, migrate)."""
	if not frappe.db.table_exists(SOURCE_DOCTYPE):
		return []

	return frappe.get_all(
		SOURCE_DOCTYPE,
		filters={"parent": SETTINGS_DOCTYPE, "parenttype": SETTINGS_DOCTYPE},
		fields=["*"],
		order_by="idx asc",
	)


def problems_with(row) -> list:
	"""Everything wrong with one configured source; [] when it is usable.

	Used by Settings on save (to refuse a bad row) and at report time (to skip one
	rather than break every report on the site).
	"""
	problems = []
	cfg = resolve(row)

	try:
		source_meta = frappe.get_meta(cfg.doctype)
		item_meta = frappe.get_meta(cfg.item_doctype)
	except Exception:
		return [_("%s or %s does not exist.") % (frappe.bold(cfg.doctype), frappe.bold(cfg.item_doctype))]

	if not source_meta.is_submittable:
		problems.append(
			_("%s is not submittable, so there is no way to tell a posted sale from a draft.") % cfg.doctype
		)

	if not any(df.fieldtype == "Table" and df.options == cfg.item_doctype for df in source_meta.fields):
		problems.append(_("%s has no item table of type %s.") % (cfg.doctype, cfg.item_doctype))

	def check(meta, label, fieldname, types, options=None):
		df = meta.get_field(fieldname) if fieldname else None
		if not df or df.fieldtype not in types or (options and df.options != options):
			problems.append(
				_("%s: %s is not a suitable field on %s.") % (label, frappe.bold(fieldname), meta.name)
			)

	dim = get_branch_dimension()
	check(source_meta, _("Net Total"), cfg.total_field, CURRENCY_TYPES)
	check(source_meta, _("Date"), cfg.date_field, ("Date", "Datetime"))
	check(source_meta, _("Company"), cfg.company_field, ("Link",), "Company")
	check(source_meta, _("Branch"), cfg.branch_field, ("Link",), dim.doctype)
	check(source_meta, _("Customer"), cfg.customer_field, ("Link",))
	check(source_meta, _("Customer Name"), cfg.customer_name_field, NAME_TYPES)
	check(source_meta, _("Is Return"), cfg.return_field, ("Check",))
	if cfg.gross_total_field:
		check(source_meta, _("Total Before Discount"), cfg.gross_total_field, CURRENCY_TYPES)

	check(item_meta, _("Item Quantity"), cfg.item_qty_field, CURRENCY_TYPES)
	check(item_meta, _("Item Amount"), cfg.item_amount_field, CURRENCY_TYPES)
	check(item_meta, _("Item Cost"), cfg.item_cost_field, CURRENCY_TYPES)
	check(item_meta, _("Item Code"), "item_code", ("Link",), "Item")
	check(item_meta, _("Item Name"), "item_name", NAME_TYPES)

	return problems


def resolve(row) -> frappe._dict:
	"""A row with every blank field name replaced by its default."""

	def get(key):
		value = row.get(key) if hasattr(row, "get") else getattr(row, key, None)
		return (value or "").strip() if isinstance(value, str) or value is None else value

	cfg = frappe._dict(
		doctype=get("source_doctype"),
		item_doctype=get("item_doctype"),
		total_field=get("total_field"),
		gross_total_field=get("gross_total_field"),
		item_cost_field=get("item_cost_field"),
		branch_field=get("branch_field") or get_branch_dimension().fieldname,
	)
	for key, default in DEFAULTS.items():
		cfg[key] = get(key) or default

	return cfg


def clear_source_cache():
	frappe.local.mr_extra_sources = None


def get_extra_sources() -> list:
	"""Usable configured sources. A broken row is logged and skipped, never raised.

	Remembered for the request: a report asks several times and the checks read doctype meta.
	"""
	cached = getattr(frappe.local, "mr_extra_sources", None)
	if cached is not None:
		return cached

	sources = []

	for row in get_source_rows():
		try:
			problems = problems_with(row)
		except Exception:
			problems = [frappe.get_traceback()]

		if problems:
			frappe.log_error("\n".join(problems), "Management Reports: additional sales source skipped")
			continue

		sources.append(resolve(row))

	frappe.local.mr_extra_sources = sources
	return sources


# --- contexts -------------------------------------------------------------


def has_extra_sources() -> bool:
	return bool(get_extra_sources())


def get_contexts(filters=None, with_items=True, only_returns=False) -> list:
	"""One query context per sales source: Sales Invoice first, then each extra source."""
	contexts = [base_query(filters, with_items=with_items, only_returns=only_returns)]

	for source in get_extra_sources():
		contexts.append(source_context(source, filters, with_items=with_items, only_returns=only_returns))

	if len(contexts) > 1:
		for ctx in contexts:
			ctx["multi"] = True

	return contexts


def source_context(source, filters=None, with_items=True, only_returns=False) -> frappe._dict:
	"""The ``base_query`` context for one extra source."""
	filters = frappe._dict(filters or {})
	dim = get_branch_dimension()

	DOC = frappe.qb.DocType(source.doctype)
	ITEM = frappe.qb.DocType(source.item_doctype) if with_items else None
	MASTER = frappe.qb.DocType("Item") if with_items else None

	if with_items:
		query = (
			frappe.qb.from_(ITEM)
			.inner_join(DOC)
			.on(DOC.name == ITEM.parent)
			.left_join(MASTER)
			.on(MASTER.name == ITEM.item_code)
		)
	else:
		query = frappe.qb.from_(DOC)

	query = query.where(DOC.docstatus == 1)

	date_column = DOC[source.date_field]
	query = apply_date_range_on(query, date_column, filters)

	if filters.get("company"):
		query = query.where(DOC[source.company_field] == filters.company)

	branch_column = DOC[source.branch_field]
	if filters.get("branch"):
		query = query.where(branch_column == filters.branch)

	if only_returns:
		query = query.where(DOC[source.return_field] == 1)

	query = apply_branch_scope(query, branch_column, dim.doctype)

	ctx = frappe._dict(
		{
			"query": query,
			"SI": DOC,
			"SII": ITEM,
			"dim": dim,
			"branch_column": branch_column,
			"source": source.doctype,
			"multi": True,
			"date_column": date_column,
			"doc_total": DOC[source.total_field],
			"customer": DOC[source.customer_field],
			"customer_name": DOC[source.customer_name_field],
		}
	)

	if with_items:
		amount = ITEM[source.item_amount_field]
		if source.gross_total_field:
			# A whole-bill discount sits on the document, not on its rows. Scale each row by
			# net / gross so item reports add up to what the customer was actually charged.
			net, gross = DOC[source.total_field], DOC[source.gross_total_field]
			amount = Case().when(gross != 0, amount * net / gross).else_(amount)

		ctx.update(
			{
				"amount": amount,
				"qty": ITEM[source.item_qty_field],
				"cost": ITEM[source.item_cost_field],
				"item_group": MASTER.item_group,
				"uom": MASTER.stock_uom,
			}
		)

	return ctx


# --- running a report over every source -----------------------------------


def collect(
	filters,
	build,
	*,
	with_items=True,
	only_returns=False,
	keys=(),
	sums=(),
	sort=None,
	reverse=False,
	limit=None,
):
	"""Run ``build(ctx)`` for each sales source and merge the rows.

	``build`` returns a list of dict rows for one context and must not sort or limit when
	``ctx.multi`` is set (those happen here, after merging). Rows with the same ``keys`` are
	combined by adding their ``sums``. With no extra sources this is exactly ``build`` on the
	Sales Invoice context.
	"""
	contexts = get_contexts(filters, with_items=with_items, only_returns=only_returns)

	if len(contexts) == 1:
		return build(contexts[0])

	rows = merge_rows([row for ctx in contexts for row in build(ctx)], keys, sums)

	if sort:
		rows.sort(key=sort, reverse=reverse)

	return rows[:limit] if limit else rows


def merge_rows(rows, keys, sums) -> list:
	"""Combine rows sharing the same ``keys`` by adding ``sums``; other fields keep the first value."""
	merged = {}

	for row in rows:
		key = tuple(row.get(name) for name in keys)
		current = merged.get(key)

		if current is None:
			merged[key] = frappe._dict(row)
			continue

		for name in sums:
			if row.get(name) is not None or current.get(name) is not None:
				current[name] = flt(current.get(name)) + flt(row.get(name))

		for name, value in row.items():
			if current.get(name) in (None, "") and value not in (None, ""):
				current[name] = value

	rows = list(merged.values())

	for row in rows:
		for name in sums:
			if row.get(name) is not None:
				row[name] = flt(row[name], 2)

	return rows


def count_distinct(filters, value, group=None) -> dict:
	"""Distinct ``value`` per ``group``, across every source (``{group: count}``).

	Summing a per-source COUNT(DISTINCT) would count a customer who bought under two sources
	twice, so the distinct pairs are fetched from each source and counted once here.
	``value`` and ``group`` take a context and return a column; without ``group`` the key is None.
	"""
	seen = {}

	for ctx in get_contexts(filters, with_items=False):
		columns = [value(ctx).as_("value")]
		if group:
			columns.append(group(ctx).as_("group"))

		for row in ctx.query.select(*columns).distinct().run(as_dict=True):
			if row.get("value") in (None, ""):
				continue
			seen.setdefault(row.get("group"), set()).add(row["value"])

	return {key: len(values) for key, values in seen.items()}
