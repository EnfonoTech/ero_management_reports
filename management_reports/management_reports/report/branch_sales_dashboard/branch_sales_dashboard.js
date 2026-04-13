frappe.query_reports["Branch Sales Dashboard"] = {
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
			fieldname: "period",
			label: __("Quick Period"),
			fieldtype: "Select",
			options: ["Financial Year", "10 Days", "30 Days", "60 Days", "90 Days", "6 Months", "1 Year"].join("\n"),
			default: "Financial Year",
			on_change: function () {
				const period = frappe.query_report.get_filter_value("period");
				const today = frappe.datetime.get_today();
				let from_date;
				if (period === "Financial Year") {
					from_date = today.substring(0, 4) + "-01-01";
				} else if (period === "10 Days") {
					from_date = frappe.datetime.add_days(today, -10);
				} else if (period === "30 Days") {
					from_date = frappe.datetime.add_days(today, -30);
				} else if (period === "60 Days") {
					from_date = frappe.datetime.add_days(today, -60);
				} else if (period === "90 Days") {
					from_date = frappe.datetime.add_days(today, -90);
				} else if (period === "6 Months") {
					from_date = frappe.datetime.add_months(today, -6);
				} else if (period === "1 Year") {
					from_date = frappe.datetime.add_months(today, -12);
				}
				frappe.query_report.set_filter_value("from_date", from_date);
				frappe.query_report.set_filter_value("to_date", today);
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today().substring(0, 4) + "-01-01",
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
		if (column.fieldname === "margin" && data) {
			if (data.margin >= 40) {
				value = `<span style="color: #2d6a4f; font-weight: 600">${value}</span>`;
			} else if (data.margin < 20) {
				value = `<span style="color: #dc3545; font-weight: 600">${value}</span>`;
			}
		}
		if (column.fieldname === "profit" && data) {
			if (data.profit >= 0) {
				value = `<span style="color: #2d6a4f; font-weight: 600">${value}</span>`;
			} else {
				value = `<span style="color: #dc3545; font-weight: 600">${value}</span>`;
			}
		}
		return value;
	},
};
