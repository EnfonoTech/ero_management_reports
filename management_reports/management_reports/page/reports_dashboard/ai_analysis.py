import json

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.utils import add_months, getdate, nowdate

from management_reports.management_reports.permissions import check_access
from management_reports.utils.ai import (
	CHAT_MAX_TOKENS,
	CHAT_TIMEOUT,
	call_ai,
	get_api_key,
	get_model,
	get_provider,
)
from management_reports.utils.currency import get_currency
from management_reports.utils.query import (
	cogs_available,
	ctx_cogs,
	invoice_count,
	month_key_column,
	rounded_sum,
)
from management_reports.utils.sources import collect


@frappe.whitelist()
def get_ai_analysis(company=None):
	"""Generate AI-powered sales analysis with chart data"""
	check_access()
	if not company:
		company = frappe.defaults.get_user_default("Company")

	if not company:
		return {"error": _("No company specified")}

	settings = frappe.get_single("Management Reports Settings")
	if not settings or not settings.enable_ai_analysis:
		return {"error": _("AI Analysis is disabled in Management Reports Settings")}

	provider = get_provider(settings)
	api_key = get_api_key(settings, provider)

	if not api_key:
		return {"error": missing_key_message(provider)}

	model = get_model(settings, provider)
	data = gather_analysis_data(company)
	prompt = build_analysis_prompt(data, company)

	try:
		raw_response = call_ai(provider, api_key, model, prompt=prompt)
		result = parse_ai_response(raw_response, data)
		return result
	except Exception as e:
		frappe.log_error(f"AI Analysis Error: {e!s}", "Management Reports AI")
		return {"error": _("Failed to generate analysis: {0}").format(str(e))}


@frappe.whitelist()
def chat_with_ai(company=None, message="", history="[]"):
	"""Interactive chat with AI about sales data"""
	check_access()
	if not company:
		company = frappe.defaults.get_user_default("Company")

	if not company:
		return {"error": _("No company specified")}

	if not message.strip():
		return {"error": _("Please enter a message")}

	settings = frappe.get_single("Management Reports Settings")
	provider = get_provider(settings)
	api_key = get_api_key(settings, provider)

	if not api_key:
		return {"error": missing_key_message(provider)}

	model = get_model(settings, provider)
	data = gather_analysis_data(company)
	currency = data.get("currency")

	# Build system context
	system_prompt = f"""You are a business analytics assistant for {company}. You have access to the following sales data:

Period: {data['period']}
Currency: {currency}

Monthly Revenue by Branch:
{json.dumps(data['monthly_branch'], indent=2)}

Top 10 Items:
{json.dumps(data['top_items'], indent=2)}

Top 10 Customers:
{json.dumps(data['top_customers'], indent=2)}

Items with Negative Margin:
{json.dumps(data['negative_margin_items'], indent=2)}

IMPORTANT RESPONSE FORMAT:
- Give concise, actionable answers
- Use markdown formatting (bold, bullets, headers)
- When the user asks for comparisons or trends, include a JSON chart block like this:

```chart
{{"type": "bar", "title": "Chart Title", "labels": ["A", "B"], "datasets": [{{"name": "Revenue", "values": [100, 200]}}], "colors": ["#0f3460", "#2d6a4f"]}}
```

- Supported chart types: bar, line, donut, pie, percentage
- Always include relevant numbers and percentages
- Keep responses under 300 words
- Be specific with recommendations"""

	# Parse conversation history
	try:
		chat_history = json.loads(history)
	except Exception:
		chat_history = []

	# Build messages array
	messages = []
	for msg in chat_history[-10:]:  # Keep last 10 messages for context
		messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
	messages.append({"role": "user", "content": message})

	try:
		response = call_ai(
			provider,
			api_key,
			model,
			system_prompt=system_prompt,
			messages=messages,
			max_tokens=CHAT_MAX_TOKENS,
			timeout=CHAT_TIMEOUT,
		)
		return {"response": response}
	except Exception as e:
		frappe.log_error(f"AI Chat Error: {e!s}", "Management Reports AI Chat")
		return {"error": str(e)}


def missing_key_message(provider) -> str:
	return (
		_("No API key configured for this provider: ")
		+ str(provider)
		+ _(". Set one in Management Reports Settings.")
	)


def gather_analysis_data(company):
	"""Gather the last 3 months of sales data for analysis.

	Goes through base_query like every report, so the branch scope applies here
	too — otherwise a branch manager could ask the chat for numbers the reports
	deliberately hide from them.
	"""
	today = getdate(nowdate())
	three_months_ago = add_months(today, -3)
	filters = {"company": company, "from_date": three_months_ago, "to_date": today}

	return {
		"company": company,
		"currency": get_currency(company),
		"period": f"{three_months_ago} to {today}",
		"monthly_branch": get_monthly_branch(filters),
		"top_items": get_top_items(filters),
		"top_customers": get_top_customers(filters),
		"negative_margin_items": get_negative_margin_items(filters),
	}


def get_monthly_branch(filters) -> list:
	def build(ctx):
		month_key = month_key_column(ctx)
		selects = [
			month_key.as_("month"),
			ctx.branch_column.as_("branch"),
			invoice_count(ctx.SI).as_("invoices"),
			rounded_sum(ctx.amount).as_("revenue"),
		]

		if cogs_available():
			selects.append(ctx_cogs(ctx).as_("cogs"))

		return (
			ctx.query.select(*selects)
			.groupby(month_key, ctx.branch_column)
			.orderby(month_key, ctx.branch_column)
			.run(as_dict=True)
		)

	return collect(
		filters,
		build,
		keys=("month", "branch"),
		sums=("invoices", "revenue", "cogs"),
		sort=lambda row: (row.get("month") or "", row.get("branch") or ""),
	)


def get_top_items(filters, limit: int = 10) -> list:
	def build(ctx):
		selects = [
			ctx.SII.item_code,
			ctx.SII.item_name,
			rounded_sum(ctx.amount).as_("revenue"),
			rounded_sum(ctx.qty).as_("qty"),
		]

		if cogs_available():
			selects.append(ctx_cogs(ctx).as_("cogs"))

		query = (
			ctx.query.select(*selects)
			.groupby(ctx.SII.item_code, ctx.SII.item_name)
			.orderby(rounded_sum(ctx.amount), order=Order.desc)
		)

		return (query if ctx.multi else query.limit(limit)).run(as_dict=True)

	rows = collect(
		filters,
		build,
		keys=("item_code", "item_name"),
		sums=("revenue", "qty", "cogs"),
		sort=lambda row: row.get("revenue") or 0,
		reverse=True,
		limit=limit,
	)

	return [{key: value for key, value in row.items() if key != "item_code"} for row in rows]


def get_top_customers(filters, limit: int = 10) -> list:
	def build(ctx):
		query = (
			ctx.query.select(
				ctx.customer.as_("customer"),
				ctx.customer_name.as_("customer_name"),
				invoice_count(ctx.SI).as_("invoices"),
				rounded_sum(ctx.doc_total).as_("revenue"),
			)
			.groupby(ctx.customer, ctx.customer_name)
			.orderby(rounded_sum(ctx.doc_total), order=Order.desc)
		)

		return (query if ctx.multi else query.limit(limit)).run(as_dict=True)

	rows = collect(
		filters,
		build,
		with_items=False,
		keys=("customer", "customer_name"),
		sums=("invoices", "revenue"),
		sort=lambda row: row.get("revenue") or 0,
		reverse=True,
		limit=limit,
	)

	return [{key: value for key, value in row.items() if key != "customer"} for row in rows]


def get_negative_margin_items(filters, limit: int = 10) -> list:
	"""Items sold below cost. Empty when the site has no trustworthy COGS."""
	if not cogs_available():
		return []

	def build(ctx):
		revenue = rounded_sum(ctx.amount)
		cogs = ctx_cogs(ctx)
		query = ctx.query.select(
			ctx.SII.item_code, ctx.SII.item_name, revenue.as_("revenue"), cogs.as_("cogs")
		).groupby(ctx.SII.item_code, ctx.SII.item_name)

		if ctx.multi:
			return query.run(as_dict=True)

		return query.having(revenue < cogs).orderby(revenue - cogs).limit(limit).run(as_dict=True)

	rows = collect(filters, build, keys=("item_code", "item_name"), sums=("revenue", "cogs"))
	# Sold below cost is judged on an item's total across every source, so with more than one the
	# rows were merged first and the test is applied here.
	losing = [row for row in rows if (row.get("revenue") or 0) < (row.get("cogs") or 0)]
	losing.sort(key=lambda row: (row.get("revenue") or 0) - (row.get("cogs") or 0))

	return [{key: value for key, value in row.items() if key != "item_code"} for row in losing[:limit]]


def build_analysis_prompt(data, company):
	currency = data.get("currency")
	return f"""Analyze this sales data for {company} and respond with EXACTLY this JSON format (no other text):

```json
{{
  "summary": "2-3 sentence executive summary",
  "kpis": [
    {{"label": "Total Revenue", "value": "<number>", "prefix": "{currency}", "change": "+X%", "color": "blue"}},
    {{"label": "Gross Margin", "value": "<percent>", "suffix": "%", "change": "+X%", "color": "green"}},
    {{"label": "Top Branch", "value": "<name>", "change": "X% share", "color": "orange"}},
    {{"label": "Risk Items", "value": "<count>", "suffix": " items", "change": "negative margin", "color": "red"}}
  ],
  "charts": [
    {{
      "title": "Revenue by Branch (Monthly)",
      "type": "bar",
      "labels": ["Jan 2026", "Feb 2026", "Mar 2026"],
      "datasets": [
        {{"name": "Branch1", "values": [100, 200, 300]}},
        {{"name": "Branch2", "values": [150, 250, 350]}}
      ],
      "colors": ["#0f3460", "#2d6a4f", "#e07c24"]
    }},
    {{
      "title": "Top 5 Items by Revenue",
      "type": "bar",
      "labels": ["Item1", "Item2", "Item3", "Item4", "Item5"],
      "datasets": [
        {{"name": "Revenue", "values": [1000, 900, 800, 700, 600]}},
        {{"name": "Profit", "values": [500, 400, 300, 200, 100]}}
      ],
      "colors": ["#0f3460", "#2d6a4f"]
    }},
    {{
      "title": "Customer Revenue Share",
      "type": "donut",
      "labels": ["Cust1", "Cust2", "Others"],
      "datasets": [{{"name": "Revenue", "values": [500, 300, 200]}}],
      "colors": ["#0f3460", "#2d6a4f", "#e07c24", "#7b2cbf", "#dc3545"]
    }}
  ],
  "insights": [
    {{"icon": "trending-up", "title": "Strong Growth", "text": "Description here", "type": "success"}},
    {{"icon": "alert-triangle", "title": "Warning Title", "text": "Description here", "type": "warning"}},
    {{"icon": "info", "title": "Opportunity", "text": "Description here", "type": "info"}}
  ],
  "recommendations": [
    "Specific recommendation 1",
    "Specific recommendation 2",
    "Specific recommendation 3"
  ]
}}
```

Use REAL numbers from this data:

Monthly Revenue by Branch:
{json.dumps(data['monthly_branch'], indent=2)}

Top 10 Items (with revenue and COGS):
{json.dumps(data['top_items'], indent=2)}

Top 10 Customers:
{json.dumps(data['top_customers'], indent=2)}

Items with Negative Margin:
{json.dumps(data['negative_margin_items'], indent=2)}

RULES:
- Use actual data values, not placeholders
- Truncate item/branch names to max 15 chars for chart labels
- Calculate profit as revenue - cogs
- Include 3-4 charts with real data
- Include 3-5 insights with types: success, warning, info, danger
- Include 3-5 specific recommendations
- Return ONLY the JSON block, no other text"""


def parse_ai_response(raw_response, data):
	"""Parse the structured JSON response from Claude"""
	try:
		# Extract JSON from response
		json_str = raw_response
		if "```json" in json_str:
			json_str = json_str.split("```json")[1].split("```")[0]
		elif "```" in json_str:
			json_str = json_str.split("```")[1].split("```")[0]

		result = json.loads(json_str.strip())
		result["success"] = True
		return result
	except (json.JSONDecodeError, IndexError):
		# Fallback: return as markdown
		return {"success": False, "markdown": raw_response, "error": "Could not parse structured response"}
