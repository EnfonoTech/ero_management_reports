// Settings form: provider-aware model options plus the test actions that let an
// implementer verify AI and email delivery before switching automation on.

const MODELS_BY_PROVIDER = {
	Anthropic: ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
	OpenAI: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
	DeepSeek: ["deepseek-chat", "deepseek-reasoner"],
};

frappe.ui.form.on("Management Reports Settings", {
	refresh(frm) {
		apply_model_options(frm);

		frm.add_custom_button(
			__("Test AI Connection"),
			() => test_ai_connection(frm),
			__("Test")
		);
		frm.add_custom_button(
			__("Preview Report Email"),
			() => preview_report_email(frm),
			__("Test")
		);
		frm.add_custom_button(__("Send Test Email"), () => send_test_email(frm), __("Test"));
		frm.add_custom_button(
			__("Run Scheduled Send Now"),
			() => run_scheduled_now(frm),
			__("Test")
		);

		if (frm.doc.email_recipients) {
			frm.dashboard.add_comment(
				__(
					"Legacy comma-separated recipients are still stored. They are migrated into the Recipients table by bench migrate; once the table looks right, the old field can be cleared."
				),
				"orange",
				true
			);
		}
	},

	ai_provider(frm) {
		apply_model_options(frm);

		// A model from the previous provider would just error on the first call.
		const allowed = MODELS_BY_PROVIDER[frm.doc.ai_provider] || [];
		if (frm.doc.ai_model && !allowed.includes(frm.doc.ai_model)) {
			frm.set_value("ai_model", allowed[0] || "");
		}
	},

	email_hour(frm) {
		const hour = cint(frm.doc.email_hour);
		if (hour < 0 || hour > 23) {
			frappe.msgprint({
				title: __("Invalid Hour"),
				message: __("Send At Hour must be between 0 and 23."),
				indicator: "red",
			});
			frm.set_value("email_hour", 7);
		}
	},
});

function apply_model_options(frm) {
	const models = MODELS_BY_PROVIDER[frm.doc.ai_provider] || [];
	frm.set_df_property("ai_model", "options", models.join("\n"));
	frm.refresh_field("ai_model");
}

function test_ai_connection(frm) {
	frappe.dom.freeze(__("Contacting {0}…", [frm.doc.ai_provider || __("provider")]));
	frappe
		.call({
			method: "management_reports.utils.ai.test_connection",
			args: { provider: frm.doc.ai_provider },
		})
		.then((r) => {
			frappe.dom.unfreeze();
			const result = r.message || {};

			if (result.ok) {
				frappe.msgprint({
					title: __("AI Connection OK"),
					indicator: "green",
					message: `
						<p>${__("Provider")}: <b>${frappe.utils.escape_html(result.provider)}</b><br>
						${__("Model")}: <b>${frappe.utils.escape_html(result.model)}</b><br>
						${__("Round trip")}: <b>${result.latency_ms} ms</b></p>
						<p style="color:var(--text-muted)">${__("Reply")}: ${frappe.utils.escape_html(
							result.reply || ""
						)}</p>`,
				});
				return;
			}

			frappe.msgprint({
				title: __("AI Connection Failed"),
				indicator: "red",
				message: `
					<p>${__("Provider")}: <b>${frappe.utils.escape_html(result.provider || "")}</b><br>
					${__("Model")}: <b>${frappe.utils.escape_html(result.model || "")}</b></p>
					<pre style="white-space:pre-wrap">${frappe.utils.escape_html(result.error || "")}</pre>`,
			});
		})
		.catch(() => frappe.dom.unfreeze());
}

function preview_report_email(frm) {
	frappe.dom.freeze(__("Building report…"));
	frappe
		.call({
			method: "management_reports.management_reports.tasks.preview_digest",
			args: { frequency: frm.doc.email_frequency },
		})
		.then((r) => {
			frappe.dom.unfreeze();
			const result = r.message || {};
			const warning = (result.failed || []).length
				? `<div class="alert alert-warning">${__("Reports that failed")}: ${frappe.utils.escape_html(
						result.failed.join(", ")
					)}</div>`
				: "";
			const to = (result.recipients || []).length
				? frappe.utils.escape_html(result.recipients.join(", "))
				: `<i>${__("no recipients configured yet")}</i>`;

			new frappe.ui.Dialog({
				title: __("Report Email Preview"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						options: `
							${warning}
							<p style="margin-bottom:4px"><b>${__("Subject")}:</b> ${frappe.utils.escape_html(
								result.subject || ""
							)}</p>
							<p style="margin-bottom:12px"><b>${__("Would send to")}:</b> ${to}</p>
							<div style="border:1px solid var(--border-color);border-radius:6px;padding:14px;
								max-height:60vh;overflow:auto;background:#fff">${result.message || ""}</div>`,
					},
				],
				primary_action_label: __("Close"),
				primary_action() {
					this.hide();
				},
			}).show();
		})
		.catch(() => frappe.dom.unfreeze());
}

function send_test_email(frm) {
	const configured = (frm.doc.recipients || [])
		.filter((row) => row.enabled && row.email_id)
		.map((row) => row.email_id);

	const dialog = new frappe.ui.Dialog({
		title: __("Send Test Email"),
		fields: [
			{
				fieldtype: "HTML",
				options: configured.length
					? `<p>${__("Leave the field below empty to send to the configured recipients")}:
						<b>${frappe.utils.escape_html(configured.join(", "))}</b></p>`
					: `<div class="alert alert-warning">${__(
							"No enabled recipients are configured. Enter an address below to test with."
						)}</div>`,
			},
			{
				fieldname: "recipients",
				fieldtype: "Small Text",
				label: __("Send Only To (comma separated)"),
				description: __("Overrides the configured recipients for this test only."),
			},
		],
		primary_action_label: __("Send"),
		primary_action(values) {
			dialog.hide();
			frappe.dom.freeze(__("Sending…"));
			frappe
				.call({
					method: "management_reports.management_reports.tasks.send_test_email",
					args: {
						recipients: values.recipients || null,
						frequency: frm.doc.email_frequency,
					},
				})
				.then((r) => {
					frappe.dom.unfreeze();
					const result = r.message || {};
					frappe.msgprint({
						title: __("Test Email Sent"),
						indicator: "green",
						message: `
							<p>${__("Sent to")}: <b>${frappe.utils.escape_html(
								(result.recipients || []).join(", ")
							)}</b><br>
							${__("Period")}: ${frappe.utils.escape_html(result.period || "")}<br>
							${__("Reports")}: ${frappe.utils.escape_html((result.reports || []).join(", "))}</p>
							<p style="color:var(--text-muted)">${__(
								"Logged under Management Report Run Log as a Test run, so it does not affect today's scheduled send."
							)}</p>`,
					});
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});

	dialog.show();
}

function run_scheduled_now(frm) {
	frappe.confirm(
		__(
			"This sends the real {0} report to all configured recipients now, and marks today as sent. Continue?",
			[frm.doc.email_frequency || __("Daily")]
		),
		() => {
			frappe
				.call({
					method: "management_reports.management_reports.tasks.run_digest_now",
					args: { frequency: frm.doc.email_frequency },
				})
				.then(() => {
					frappe.show_alert({
						message: __("Queued. Check Management Report Run Log for the outcome."),
						indicator: "blue",
					});
				});
		}
	);
}
