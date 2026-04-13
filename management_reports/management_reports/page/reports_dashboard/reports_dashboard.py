import frappe
from frappe import _
from frappe.utils import nowdate, getdate, add_months, get_first_day, get_last_day
from management_reports.management_reports.permissions import check_access


@frappe.whitelist()
def get_dashboard_kpis(company=None):
	check_access()
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

	if not company:
		return {"error": "No default company found. Please set a default company."}

	currency = frappe.get_cached_value("Company", company, "default_currency") or "SAR"
	today = getdate(nowdate())
	mtd_start = get_first_day(today)
	last_12m_start = add_months(today, -12)

	# MTD Revenue
	mtd_revenue = frappe.db.sql("""
		SELECT ROUND(IFNULL(SUM(grand_total), 0), 2)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company = %s
			AND posting_date BETWEEN %s AND %s
	""", (company, mtd_start, today))[0][0]

	# MTD Invoices
	mtd_invoices = frappe.db.sql("""
		SELECT COUNT(name)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company = %s
			AND posting_date BETWEEN %s AND %s
	""", (company, mtd_start, today))[0][0]

	# MTD Customers
	mtd_customers = frappe.db.sql("""
		SELECT COUNT(DISTINCT customer)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company = %s
			AND posting_date BETWEEN %s AND %s
	""", (company, mtd_start, today))[0][0]

	# Fallback: if MTD is 0, compute last completed month
	last_month_revenue = 0
	last_month_invoices = 0
	last_month_customers = 0
	last_month_label = ""

	if not mtd_revenue:
		prev_month_end = add_months(mtd_start, 0) - __import__("datetime").timedelta(days=1)
		prev_month_start = get_first_day(prev_month_end)
		month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
			"Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
		last_month_label = f"{month_names[prev_month_end.month]} {prev_month_end.year}"

		last_month_revenue = frappe.db.sql("""
			SELECT ROUND(IFNULL(SUM(grand_total), 0), 2)
			FROM `tabSales Invoice`
			WHERE docstatus = 1 AND company = %s
				AND posting_date BETWEEN %s AND %s
		""", (company, prev_month_start, prev_month_end))[0][0]

		last_month_invoices = frappe.db.sql("""
			SELECT COUNT(name)
			FROM `tabSales Invoice`
			WHERE docstatus = 1 AND company = %s
				AND posting_date BETWEEN %s AND %s
		""", (company, prev_month_start, prev_month_end))[0][0]

		last_month_customers = frappe.db.sql("""
			SELECT COUNT(DISTINCT customer)
			FROM `tabSales Invoice`
			WHERE docstatus = 1 AND company = %s
				AND posting_date BETWEEN %s AND %s
		""", (company, prev_month_start, prev_month_end))[0][0]

	# Last 12M Revenue
	last_12m_revenue = frappe.db.sql("""
		SELECT ROUND(IFNULL(SUM(grand_total), 0), 2)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company = %s
			AND posting_date BETWEEN %s AND %s
	""", (company, last_12m_start, today))[0][0]

	# Active Branches
	active_branches = frappe.db.sql("""
		SELECT COUNT(DISTINCT cost_center)
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND company = %s
			AND posting_date BETWEEN %s AND %s
	""", (company, last_12m_start, today))[0][0]

	return {
		"company": company,
		"currency": currency,
		"mtd_revenue": mtd_revenue,
		"mtd_invoices": mtd_invoices,
		"mtd_customers": mtd_customers,
		"last_12m_revenue": last_12m_revenue,
		"active_branches": active_branches,
		# Fallback data
		"last_month_revenue": last_month_revenue,
		"last_month_invoices": last_month_invoices,
		"last_month_customers": last_month_customers,
		"last_month_label": last_month_label,
	}
