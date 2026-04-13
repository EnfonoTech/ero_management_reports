frappe.pages["reports-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Management Reports"),
		single_column: true,
	});

	page.main.addClass("reports-dashboard");
	wrapper.page = page;

	if (frappe.boot.management_reports_access === false) {
		page.main.html(`
			<div style="text-align: center; padding: 80px 20px;">
				<i class="fa fa-lock" style="font-size: 48px; color: var(--text-muted); margin-bottom: 16px;"></i>
				<h3 style="color: var(--text-muted);">${__("Access Restricted")}</h3>
				<p style="color: var(--text-light);">${__("You do not have access to Management Reports.")}</p>
			</div>
		`);
		return;
	}

	// Settings icon
	page.set_secondary_action(__("Settings"), function () {
		frappe.set_route("app", "management-reports-settings");
	}, "fa fa-cog");

	// Company selector
	let company_field = page.add_field({
		fieldname: "company",
		label: __("Company"),
		fieldtype: "Link",
		options: "Company",
		default: frappe.defaults.get_user_default("Company"),
		change: function () {
			load_dashboard(page, company_field.get_value());
		},
	});

	setTimeout(function () {
		load_dashboard(page, company_field.get_value());
	}, 300);
};

// Chat history stored in session
var chat_history = [];

function load_dashboard(page, company) {
	if (!company) {
		page.main.html(`<div style="text-align:center;padding:60px;color:var(--text-muted);">${__("Please select a Company.")}</div>`);
		return;
	}

	let html = `
		<div class="dashboard-header">
			<h2 id="dashboard-title">${__("Management Dashboard")}</h2>
			<p id="dashboard-subtitle">${__("Loading data...")}</p>
		</div>

		<div class="kpi-grid" id="kpi-grid">
			<div class="kpi-card"><div class="kpi-value blue" id="kpi-mtd-revenue"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-label" id="kpi-mtd-revenue-label">${__("MTD Revenue")}</div></div>
			<div class="kpi-card"><div class="kpi-value green" id="kpi-12m-revenue"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-label">${__("Last 12M Revenue")}</div></div>
			<div class="kpi-card"><div class="kpi-value blue" id="kpi-mtd-invoices"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-label" id="kpi-mtd-invoices-label">${__("MTD Invoices")}</div></div>
			<div class="kpi-card"><div class="kpi-value orange" id="kpi-branches"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-label">${__("Active Branches")}</div></div>
			<div class="kpi-card"><div class="kpi-value green" id="kpi-customers"><i class="fa fa-spinner fa-spin"></i></div><div class="kpi-label" id="kpi-customers-label">${__("MTD Customers")}</div></div>
		</div>

		<div class="section-title">${__("Sales Reports")}</div>
		<div class="report-grid">
			<a class="report-card" href="/app/query-report/Branch Sales Dashboard"><div class="card-icon blue"><i class="fa fa-building"></i></div><div class="card-title">${__("Branch Sales Dashboard")}</div><div class="card-desc">${__("Compare revenue, profit, and margins across branches")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
			<a class="report-card" href="/app/query-report/Top Selling Items"><div class="card-icon green"><i class="fa fa-star"></i></div><div class="card-title">${__("Top Selling Items")}</div><div class="card-desc">${__("Ranked list of best-performing products by revenue")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
			<a class="report-card" href="/app/query-report/Monthly Sales Trend"><div class="card-icon orange"><i class="fa fa-line-chart"></i></div><div class="card-title">${__("Monthly Sales Trend")}</div><div class="card-desc">${__("Track revenue growth month-over-month")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
			<a class="report-card" href="/app/query-report/Customer Analysis"><div class="card-icon purple"><i class="fa fa-users"></i></div><div class="card-title">${__("Customer Analysis")}</div><div class="card-desc">${__("Customer revenue distribution and top accounts")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
			<a class="report-card" href="/app/query-report/Daily Summary"><div class="card-icon blue"><i class="fa fa-calendar-check-o"></i></div><div class="card-title">${__("Daily Summary")}</div><div class="card-desc">${__("End-of-day income, expenses, profit")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
			<a class="report-card" href="/app/query-report/Monthly Summary"><div class="card-icon green"><i class="fa fa-calendar"></i></div><div class="card-title">${__("Monthly Summary")}</div><div class="card-desc">${__("Monthly P&L with branch breakdown")}</div><span class="card-arrow"><i class="fa fa-arrow-right"></i></span></a>
		</div>

		<div class="section-title">${__("AI Analytics")}</div>
		<div class="ai-section">
			<div class="ai-tabs">
				<button class="btn btn-primary btn-sm ai-tab active" data-tab="analysis" id="btn-ai-analysis">
					<i class="fa fa-bar-chart"></i> ${__("Visual Analysis")}
				</button>
				<button class="btn btn-default btn-sm ai-tab" data-tab="chat" id="btn-ai-chat-tab">
					<i class="fa fa-comments"></i> ${__("Chat with AI")}
				</button>
			</div>

			<!-- Analysis Tab -->
			<div id="ai-analysis-tab" class="ai-tab-content">
				<div id="ai-analysis-prompt" style="text-align:center; padding:50px 20px;">
					<i class="fa fa-bar-chart" style="font-size:40px; color:var(--primary); margin-bottom:16px;"></i>
					<h4 style="color:var(--text-color); margin-bottom:8px;">${__("AI-Powered Sales Analysis")}</h4>
					<p style="color:var(--text-muted); margin-bottom:20px; font-size:13px;">${__("Analyze your last 3 months of sales data with AI to get insights, charts, and recommendations.")}</p>
					<button class="btn btn-primary" id="btn-run-analysis"><i class="fa fa-play"></i> ${__("Generate Analysis")}</button>
				</div>
				<div id="ai-analysis-loading" style="display:none; text-align:center; padding:40px;">
					<i class="fa fa-spinner fa-spin" style="font-size:24px; color:var(--primary);"></i>
					<p style="margin-top:12px; color:var(--text-muted);">${__("AI is analyzing your data...")}</p>
				</div>
				<div id="ai-analysis-result" style="display:none;"></div>
			</div>

			<!-- Chat Tab -->
			<div id="ai-chat-tab" class="ai-tab-content" style="display:none;">
				<div class="chat-container" id="chat-container">
					<div class="chat-header">
						<span class="chat-header-title"><i class="fa fa-magic"></i> ${__("AI Analytics Assistant")}</span>
						<div class="chat-header-actions">
							<button class="btn btn-xs btn-default" id="btn-chat-clear" title="${__("Clear chat")}"><i class="fa fa-trash"></i></button>
							<button class="btn btn-xs btn-default" id="btn-chat-fullscreen" title="${__("Fullscreen")}"><i class="fa fa-expand"></i></button>
						</div>
					</div>
					<div class="chat-messages" id="chat-messages">
						<div class="chat-message assistant">
							<div class="chat-avatar"><i class="fa fa-magic"></i></div>
							<div class="chat-bubble">${__("Hi! I can analyze your sales data, create charts, compare branches, and give recommendations. What would you like to know?")}</div>
						</div>
					</div>
					<div class="chat-input-area">
						<div class="chat-suggestions" id="chat-suggestions">
							<button class="suggestion-chip">${__("Compare branch performance")}</button>
							<button class="suggestion-chip">${__("Which items have negative margin?")}</button>
							<button class="suggestion-chip">${__("Top 5 customers by revenue")}</button>
							<button class="suggestion-chip">${__("Monthly revenue growth trend")}</button>
						</div>
						<div class="chat-input-row">
							<input type="text" id="chat-input" class="form-control" placeholder="${__("Ask about your sales data...")}" />
							<button class="btn btn-primary" id="btn-chat-send"><i class="fa fa-paper-plane"></i></button>
						</div>
					</div>
				</div>
			</div>
		</div>
	`;

	page.main.html(html);

	// Tab switching
	$(".ai-tab").on("click", function () {
		$(".ai-tab").removeClass("active").addClass("btn-default").removeClass("btn-primary");
		$(this).addClass("active btn-primary").removeClass("btn-default");
		$(".ai-tab-content").hide();
		let tab = $(this).data("tab");
		if (tab === "analysis") {
			$("#ai-analysis-tab").show();
		} else {
			$("#ai-chat-tab").show();
		}
	});

	// Run analysis on button click (not auto-load)
	$("#btn-run-analysis").on("click", function () {
		load_ai_analysis(company);
	});

	// Chat input handlers
	$("#btn-chat-send").on("click", function () { send_chat_message(company); });
	$("#chat-input").on("keypress", function (e) {
		if (e.which === 13) send_chat_message(company);
	});

	// Suggestion chips
	$(".suggestion-chip").on("click", function () {
		$("#chat-input").val($(this).text());
		send_chat_message(company);
	});

	// Fullscreen toggle
	$("#btn-chat-fullscreen").on("click", function () {
		let container = $("#chat-container");
		if (container.hasClass("chat-fullscreen")) {
			container.removeClass("chat-fullscreen");
			$(this).html('<i class="fa fa-expand"></i>');
			$("body").css("overflow", "");
		} else {
			container.addClass("chat-fullscreen");
			$(this).html('<i class="fa fa-compress"></i>');
			$("body").css("overflow", "hidden");
		}
		scroll_chat();
	});

	// Clear chat
	$("#btn-chat-clear").on("click", function () {
		chat_history = [];
		$("#chat-messages").html(`
			<div class="chat-message assistant">
				<div class="chat-avatar"><i class="fa fa-magic"></i></div>
				<div class="chat-bubble">${__("Chat cleared. Ask me anything about your sales data!")}</div>
			</div>
		`);
		$("#chat-suggestions").show();
	});

	// ESC to exit fullscreen
	$(document).on("keydown.chat-fullscreen", function (e) {
		if (e.key === "Escape" && $("#chat-container").hasClass("chat-fullscreen")) {
			$("#btn-chat-fullscreen").click();
		}
	});

	// Load KPIs
	frappe.call({
		method: "management_reports.management_reports.page.reports_dashboard.reports_dashboard.get_dashboard_kpis",
		args: { company: company },
		callback: function (r) { if (r.message) render_kpis(page, r.message); },
		error: function () { $(".kpi-value").text("—"); },
	});
}

function render_kpis(page, d) {
	let cur = d.currency || "SAR";
	let company_name = d.company || "";
	page.set_title(company_name + " — " + __("Management Reports"));
	$("#dashboard-subtitle").text(__("Real-time sales metrics for {0}", [company_name]));

	if (d.mtd_revenue) {
		$("#kpi-mtd-revenue").text(format_currency(d.mtd_revenue, cur));
		$("#kpi-mtd-invoices").text(format_number(d.mtd_invoices));
		$("#kpi-customers").text(d.mtd_customers);
	} else if (d.last_month_revenue) {
		$("#kpi-mtd-revenue").text(format_currency(d.last_month_revenue, cur));
		$("#kpi-mtd-revenue-label").text(d.last_month_label + " Revenue");
		$("#kpi-mtd-invoices").text(format_number(d.last_month_invoices));
		$("#kpi-mtd-invoices-label").text(d.last_month_label + " Invoices");
		$("#kpi-customers").text(d.last_month_customers);
		$("#kpi-customers-label").text(d.last_month_label + " Customers");
	} else {
		$("#kpi-mtd-revenue").text(format_currency(0, cur));
		$("#kpi-mtd-invoices").text("0");
		$("#kpi-customers").text("0");
	}
	$("#kpi-12m-revenue").text(format_currency(d.last_12m_revenue, cur));
	$("#kpi-branches").text(d.active_branches);
}

function load_ai_analysis(company) {
	$("#ai-analysis-prompt").hide();
	$("#ai-analysis-loading").show();
	$("#ai-analysis-result").hide();

	frappe.call({
		method: "management_reports.management_reports.page.reports_dashboard.ai_analysis.get_ai_analysis",
		args: { company: company },
		callback: function (r) {
			$("#ai-analysis-loading").hide();
			if (r.message && r.message.success) {
				render_visual_analysis(r.message);
			} else if (r.message && r.message.markdown) {
				$("#ai-analysis-result").html(frappe.markdown(r.message.markdown)).show();
			} else if (r.message && r.message.error) {
				$("#ai-analysis-result").html(`<div class="ai-error"><i class="fa fa-exclamation-circle"></i> ${r.message.error}</div>`).show();
			}
		},
		error: function () {
			$("#ai-analysis-loading").hide();
			$("#ai-analysis-result").html(`<div class="ai-error"><i class="fa fa-exclamation-circle"></i> ${__("Failed to load. Check API key in Settings.")}</div>`).show();
		},
	});
}

function render_visual_analysis(data) {
	let html = "";

	// Summary
	if (data.summary) {
		html += `<div class="ai-summary">${data.summary}</div>`;
	}

	// KPI cards
	if (data.kpis && data.kpis.length) {
		html += `<div class="ai-kpi-grid">`;
		data.kpis.forEach(function (kpi) {
			let color_class = kpi.color || "blue";
			html += `
				<div class="ai-kpi-card ${color_class}">
					<div class="ai-kpi-value">${kpi.prefix || ""}${kpi.value}${kpi.suffix || ""}</div>
					<div class="ai-kpi-label">${kpi.label}</div>
					<div class="ai-kpi-change">${kpi.change || ""}</div>
				</div>`;
		});
		html += `</div>`;
	}

	// Charts
	if (data.charts && data.charts.length) {
		data.charts.forEach(function (chart, idx) {
			html += `<div class="ai-chart-card">
				<div class="ai-chart-title">${chart.title || ""}</div>
				<div id="ai-chart-${idx}" class="ai-chart-container"></div>
			</div>`;
		});
	}

	// Insights
	if (data.insights && data.insights.length) {
		html += `<div class="ai-insights">`;
		data.insights.forEach(function (insight) {
			let type_class = insight.type || "info";
			let icon = "fa-info-circle";
			if (type_class === "success") icon = "fa-check-circle";
			else if (type_class === "warning") icon = "fa-exclamation-triangle";
			else if (type_class === "danger") icon = "fa-times-circle";
			html += `
				<div class="ai-insight ${type_class}">
					<i class="fa ${icon}"></i>
					<div><strong>${insight.title}</strong><p>${insight.text}</p></div>
				</div>`;
		});
		html += `</div>`;
	}

	// Recommendations
	if (data.recommendations && data.recommendations.length) {
		html += `<div class="ai-recommendations"><h4><i class="fa fa-lightbulb-o"></i> ${__("Recommendations")}</h4><ul>`;
		data.recommendations.forEach(function (rec) {
			html += `<li>${rec}</li>`;
		});
		html += `</ul></div>`;
	}

	$("#ai-analysis-result").html(html).show();

	// Render charts after DOM is ready
	if (data.charts && data.charts.length) {
		setTimeout(function () {
			data.charts.forEach(function (chart, idx) {
				try {
					new frappe.Chart("#ai-chart-" + idx, {
						data: {
							labels: chart.labels || [],
							datasets: chart.datasets || [],
						},
						type: chart.type || "bar",
						height: 280,
						colors: chart.colors || ["#0f3460", "#2d6a4f", "#e07c24"],
					});
				} catch (e) {
					console.error("Chart render error:", e);
				}
			});
		}, 100);
	}
}

function send_chat_message(company) {
	let input = $("#chat-input");
	let message = input.val().trim();
	if (!message) return;

	input.val("");
	$("#chat-suggestions").hide();

	// Add user message
	append_chat_message("user", message);
	chat_history.push({ role: "user", content: message });

	// Show typing indicator
	let typing_id = "typing-" + Date.now();
	$("#chat-messages").append(`
		<div class="chat-message assistant" id="${typing_id}">
			<div class="chat-avatar"><i class="fa fa-magic"></i></div>
			<div class="chat-bubble typing"><span></span><span></span><span></span></div>
		</div>
	`);
	scroll_chat();

	frappe.call({
		method: "management_reports.management_reports.page.reports_dashboard.ai_analysis.chat_with_ai",
		args: {
			company: company,
			message: message,
			history: JSON.stringify(chat_history.slice(-10)),
		},
		callback: function (r) {
			$(`#${typing_id}`).remove();
			if (r.message && r.message.response) {
				let response = r.message.response;
				chat_history.push({ role: "assistant", content: response });
				render_chat_response(response);
			} else if (r.message && r.message.error) {
				append_chat_message("assistant", `<span style="color:var(--red);">${r.message.error}</span>`);
			}
		},
		error: function () {
			$(`#${typing_id}`).remove();
			append_chat_message("assistant", `<span style="color:var(--red);">${__("Failed to get response. Please try again.")}</span>`);
		},
	});
}

function render_chat_response(response) {
	// Extract chart blocks
	let chart_configs = [];
	let processed = response;

	// Replace ```chart blocks with placeholders
	let chart_regex = /```chart\s*\n?([\s\S]*?)```/g;
	let match;
	let chart_idx = 0;

	processed = processed.replace(chart_regex, function (full_match, json_str) {
		try {
			let config = JSON.parse(json_str.trim());
			let chart_id = "chat-chart-" + Date.now() + "-" + chart_idx;
			chart_configs.push({ id: chart_id, config: config });
			chart_idx++;
			return `<div class="chat-chart-wrapper"><div class="chat-chart-title">${config.title || ""}</div><div class="chat-chart-render" id="${chart_id}"></div></div>`;
		} catch (e) {
			return ""; // Remove unparseable chart blocks
		}
	});

	// Convert markdown to HTML
	let bubble_html = markdown_to_html(processed);

	let msg_el = $(`
		<div class="chat-message assistant">
			<div class="chat-avatar"><i class="fa fa-magic"></i></div>
			<div class="chat-bubble">${bubble_html}</div>
		</div>
	`);
	$("#chat-messages").append(msg_el);
	scroll_chat();

	// Render charts after DOM insert
	if (chart_configs.length) {
		setTimeout(function () {
			chart_configs.forEach(function (c) {
				try {
					new frappe.Chart("#" + c.id, {
						data: { labels: c.config.labels || [], datasets: c.config.datasets || [] },
						type: c.config.type || "bar",
						height: 250,
						colors: c.config.colors || ["#0f3460", "#2d6a4f", "#e07c24"],
					});
				} catch (e) { console.error("Chart error:", e); }
			});
		}, 150);
	}
}

function markdown_to_html(text) {
	// Use frappe's built-in markdown if available
	try {
		let html = frappe.markdown(text);
		// Wrap tables for proper scrolling
		html = html.replace(/<table/g, '<div class="table-wrapper"><table class="table table-bordered table-sm"');
		html = html.replace(/<\/table>/g, '</table></div>');
		return html;
	} catch (e) {
		// Fallback: basic conversion
		return text
			.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.*?)\*/g, '<em>$1</em>')
			.replace(/^### (.*$)/gm, '<h4>$1</h4>')
			.replace(/^## (.*$)/gm, '<h3>$1</h3>')
			.replace(/^# (.*$)/gm, '<h2>$1</h2>')
			.replace(/^\- (.*$)/gm, '<li>$1</li>')
			.replace(/^\* (.*$)/gm, '<li>$1</li>')
			.replace(/\n/g, '<br>');
	}
}

function append_chat_message(role, content) {
	let icon = role === "user" ? "fa-user" : "fa-magic";
	let rendered = role === "user" ? frappe.utils.escape_html(content) : content;
	$("#chat-messages").append(`
		<div class="chat-message ${role}">
			<div class="chat-avatar"><i class="fa ${icon}"></i></div>
			<div class="chat-bubble">${rendered}</div>
		</div>
	`);
	scroll_chat();
}

function scroll_chat() {
	let el = document.getElementById("chat-messages");
	if (el) el.scrollTop = el.scrollHeight;
}

function format_currency(val, cur) {
	cur = cur || "SAR";
	if (!val) return cur + " 0";
	if (val >= 1000000) return cur + " " + (val / 1000000).toFixed(1) + "M";
	if (val >= 1000) return cur + " " + (val / 1000).toFixed(1) + "K";
	return cur + " " + val.toFixed(0);
}

function format_number(val) {
	return val ? val.toLocaleString() : "0";
}
