// Branch dimension for this site, published by boot.py. Falls back to Cost
// Center so the filter still works if boot data is unavailable.
function management_reports_branch() {
	return (
		(frappe.boot && frappe.boot.management_reports_branch) || {
			fieldname: "cost_center",
			doctype: "Cost Center",
			label: "Branch",
			filter_by_company: true,
		}
	);
}

frappe.query_reports["Loyalty Points Redeemed"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
			on_change: function () {
				frappe.query_report.set_filter_value("branch", "");
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "branch",
			label: __(management_reports_branch().label),
			fieldtype: "Link",
			options: management_reports_branch().doctype,
			get_query: function () {
				// Only company-scoped dimensions accept a company filter.
				if (!management_reports_branch().filter_by_company) return {};
				var company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
	],
};
