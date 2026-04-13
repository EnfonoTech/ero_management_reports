frappe.query_reports["Monthly Summary"] = {
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
			default: frappe.datetime.get_today().substring(0, 7) + "-01",
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
			label: __("Branch"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				var company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "profit" && data) {
			if (data.profit >= 0) {
				value = `<span style="color: #2d6a4f; font-weight: 600">${value}</span>`;
			} else {
				value = `<span style="color: #dc3545; font-weight: 600">${value}</span>`;
			}
		}
		if (column.fieldname === "margin" && data) {
			if (data.margin >= 40) {
				value = `<span style="color: #2d6a4f; font-weight: 600">${value}</span>`;
			} else if (data.margin < 20) {
				value = `<span style="color: #dc3545; font-weight: 600">${value}</span>`;
			}
		}
		return value;
	},
};
