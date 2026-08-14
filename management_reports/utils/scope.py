"""Row-level branch scoping.

Script reports query the database directly, which bypasses Frappe's permission
layer entirely — so a branch manager would otherwise read every branch in the
company. These helpers translate native User Permission records into an explicit
branch allowlist that every report applies to its WHERE clause.
"""

import frappe
from frappe.permissions import get_allowed_docs_for_doctype, get_user_permissions


def get_permitted_branches(branch_doctype: str, user: str | None = None) -> list[str] | None:
	"""Branches this user may see, or ``None`` when unrestricted.

	``None`` means "no restriction" and is deliberately distinct from ``[]``,
	which means "restricted to nothing". Callers must not treat a falsy return
	as unrestricted: an empty list has to filter everything out, otherwise a
	user permitted on zero branches would silently see all of them.

	Descendants of a permitted node are included for tree doctypes (Cost Center,
	Warehouse) unless the User Permission sets ``hide_descendants`` — matching
	the meaning of that flag elsewhere in Frappe.
	"""
	user = user or frappe.session.user

	if user == "Administrator":
		return None

	permissions = get_user_permissions(user)
	if not permissions or branch_doctype not in permissions:
		return None

	entries = permissions.get(branch_doctype) or []
	allowed = get_allowed_docs_for_doctype(entries, branch_doctype)
	if not allowed:
		# Permissions exist for this doctype but none apply here (applicable_for
		# points elsewhere) — nothing to restrict.
		return None

	hide_descendants = {entry.get("doc"): entry.get("hide_descendants") for entry in entries}
	expandable = [doc for doc in allowed if not hide_descendants.get(doc)]

	return sorted(set(allowed) | set(get_descendants(branch_doctype, expandable)))


def get_descendants(doctype: str, parents: list[str]) -> list[str]:
	"""Descendant names of ``parents`` for a nested-set doctype; [] otherwise."""
	if not parents or not frappe.get_meta(doctype).is_tree:
		return []

	nodes = frappe.get_all(doctype, filters={"name": ["in", parents]}, fields=["lft", "rgt"])
	if not nodes:
		return []

	table = frappe.qb.DocType(doctype)
	query = frappe.qb.from_(table).select(table.name)
	condition = None
	for node in nodes:
		bounds = (table.lft >= node.lft) & (table.rgt <= node.rgt)
		condition = bounds if condition is None else (condition | bounds)

	return [row[0] for row in query.where(condition).run()]


def apply_branch_scope(query, branch_column, branch_doctype: str, user: str | None = None):
	"""Add the user's branch allowlist to ``query``, if they are restricted."""
	permitted = get_permitted_branches(branch_doctype, user)
	if permitted is None:
		return query

	if not permitted:
		# Restricted to nothing — return an intentionally empty result set
		# rather than falling through to unfiltered data.
		return query.where(branch_column.isnull() & branch_column.isnotnull())

	return query.where(branch_column.isin(permitted))
