// The Branch column is a Dynamic Link driven by branch_doctype. Frappe validates
// Dynamic Links before any server controller hook runs, so the row must already
// carry the right doctype by the time it is saved — stamp it as soon as the row
// is added rather than relying on the server to fill it in.

function branch_dimension() {
	return (
		(frappe.boot && frappe.boot.management_reports_branch) || {
			fieldname: "cost_center",
			doctype: "Cost Center",
			label: "Branch",
			filter_by_company: true,
		}
	);
}

frappe.ui.form.on("Management Report Config", {
	setup(frm) {
		frm.set_query("branch", "branch_map", function () {
			// Only company-scoped dimensions accept a company filter; the ERPNext
			// Branch doctype, for instance, has no company field.
			if (!branch_dimension().filter_by_company || !frm.doc.company) return {};
			return { filters: { company: frm.doc.company } };
		});
	},

	refresh(frm) {
		const dimension = branch_dimension();
		frm.fields_dict.branch_map.grid.update_docfield_property(
			"branch",
			"label",
			__(dimension.label)
		);
		stamp_rows(frm);
	},

	company(frm) {
		// A branch belonging to another company is rejected on save, so clear the
		// rows rather than let someone hit a wall of errors.
		if (frm.doc.company && (frm.doc.branch_map || []).length) {
			frm.clear_table("branch_map");
			frm.refresh_field("branch_map");
			frappe.show_alert({
				message: __("Branch rows cleared because the company changed."),
				indicator: "orange",
			});
		}
	},
});

frappe.ui.form.on("Management Report Branch Map", {
	branch_map_add(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "branch_doctype", branch_dimension().doctype);
	},
});

function stamp_rows(frm) {
	const target = branch_dimension().doctype;
	(frm.doc.branch_map || []).forEach((row) => {
		if (row.branch_doctype !== target) {
			frappe.model.set_value(row.doctype, row.name, "branch_doctype", target);
		}
	});
}
