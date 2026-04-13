import frappe
import json
from frappe import _
from frappe.utils import nowdate, getdate, add_months
from management_reports.management_reports.permissions import check_access


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

	provider = settings.ai_provider or "Anthropic"
	api_key = get_api_key(settings, provider)

	if not api_key:
		return {"error": _("Please configure your {0} API key in Management Reports Settings. Go to: /app/management-reports-settings").format(provider)}

	model = settings.ai_model or get_default_model(provider)
	data = gather_analysis_data(company)
	prompt = build_analysis_prompt(data, company)

	try:
		raw_response = call_ai_api(provider, api_key, model, prompt)
		result = parse_ai_response(raw_response, data)
		return result
	except Exception as e:
		frappe.log_error(f"AI Analysis Error: {str(e)}", "Management Reports AI")
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
	provider = settings.ai_provider or "Anthropic"
	api_key = get_api_key(settings, provider)

	if not api_key:
		return {"error": _("Please configure your {0} API key in Management Reports Settings.").format(provider)}

	model = settings.ai_model or get_default_model(provider)
	data = gather_analysis_data(company)
	currency = data.get("currency", "SAR")

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
		response = call_ai_api_with_system(provider, api_key, model, system_prompt, messages)
		return {"response": response}
	except Exception as e:
		frappe.log_error(f"AI Chat Error: {str(e)}", "Management Reports AI Chat")
		return {"error": str(e)}


def gather_analysis_data(company):
	"""Gather last 3 months of sales data for analysis"""
	today = getdate(nowdate())
	three_months_ago = add_months(today, -3)
	currency = frappe.get_cached_value("Company", company, "default_currency") or "SAR"

	monthly_branch = frappe.db.sql("""
		SELECT
			DATE_FORMAT(si.posting_date, '%%Y-%%m') AS month,
			si.cost_center AS branch,
			COUNT(DISTINCT si.name) AS invoices,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY DATE_FORMAT(si.posting_date, '%%Y-%%m'), si.cost_center
		ORDER BY month, si.cost_center
	""", {"company": company, "from_date": three_months_ago, "to_date": today}, as_dict=1)

	top_items = frappe.db.sql("""
		SELECT sii.item_name,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty), 2) AS qty,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY sii.item_code, sii.item_name
		ORDER BY SUM(sii.amount) DESC LIMIT 10
	""", {"company": company, "from_date": three_months_ago, "to_date": today}, as_dict=1)

	top_customers = frappe.db.sql("""
		SELECT si.customer_name, COUNT(si.name) AS invoices,
			ROUND(SUM(si.grand_total), 2) AS revenue
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY si.customer, si.customer_name
		ORDER BY SUM(si.grand_total) DESC LIMIT 10
	""", {"company": company, "from_date": three_months_ago, "to_date": today}, as_dict=1)

	negative_margin = frappe.db.sql("""
		SELECT sii.item_name,
			ROUND(SUM(sii.amount), 2) AS revenue,
			ROUND(SUM(sii.qty * sii.incoming_rate), 2) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY sii.item_code, sii.item_name
		HAVING SUM(sii.amount) < SUM(sii.qty * sii.incoming_rate)
		ORDER BY (SUM(sii.amount) - SUM(sii.qty * sii.incoming_rate)) ASC LIMIT 10
	""", {"company": company, "from_date": three_months_ago, "to_date": today}, as_dict=1)

	return {
		"company": company,
		"currency": currency,
		"period": f"{three_months_ago} to {today}",
		"monthly_branch": [dict(r) for r in monthly_branch],
		"top_items": [dict(r) for r in top_items],
		"top_customers": [dict(r) for r in top_customers],
		"negative_margin_items": [dict(r) for r in negative_margin],
	}


def build_analysis_prompt(data, company):
	currency = data.get("currency", "SAR")
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
		return {
			"success": False,
			"markdown": raw_response,
			"error": "Could not parse structured response"
		}


def get_api_key(settings, provider):
	"""Get API key based on selected provider"""
	if provider == "OpenAI":
		return settings.get_password("openai_api_key") if settings else None
	return settings.get_password("anthropic_api_key") if settings else None


def get_default_model(provider):
	"""Get default model for a provider"""
	if provider == "OpenAI":
		return "gpt-4o"
	return "claude-sonnet-4-20250514"


def call_ai_api(provider, api_key, model, prompt):
	"""Route single-prompt call to the correct provider"""
	if provider == "OpenAI":
		return call_openai_api(api_key, model, prompt)
	return call_claude_api(api_key, model, prompt)


def call_ai_api_with_system(provider, api_key, model, system_prompt, messages):
	"""Route system-prompt call to the correct provider"""
	if provider == "OpenAI":
		return call_openai_api_with_system(api_key, model, system_prompt, messages)
	return call_claude_api_with_system(api_key, model, system_prompt, messages)


def call_claude_api(api_key, model, prompt):
	"""Call Claude API with a single prompt"""
	import requests

	response = requests.post(
		"https://api.anthropic.com/v1/messages",
		headers={
			"x-api-key": api_key,
			"anthropic-version": "2023-06-01",
			"content-type": "application/json",
		},
		json={
			"model": model,
			"max_tokens": 4000,
			"messages": [{"role": "user", "content": prompt}],
		},
		timeout=90,
	)

	if response.status_code != 200:
		error_msg = response.json().get("error", {}).get("message", response.text)
		frappe.throw(f"Claude API error: {error_msg}")

	return response.json()["content"][0]["text"]


def call_claude_api_with_system(api_key, model, system_prompt, messages):
	"""Call Claude API with system prompt and message history"""
	import requests

	response = requests.post(
		"https://api.anthropic.com/v1/messages",
		headers={
			"x-api-key": api_key,
			"anthropic-version": "2023-06-01",
			"content-type": "application/json",
		},
		json={
			"model": model,
			"max_tokens": 2000,
			"system": system_prompt,
			"messages": messages,
		},
		timeout=60,
	)

	if response.status_code != 200:
		error_msg = response.json().get("error", {}).get("message", response.text)
		frappe.throw(f"Claude API error: {error_msg}")

	return response.json()["content"][0]["text"]


def call_openai_api(api_key, model, prompt):
	"""Call OpenAI API with a single prompt"""
	import requests

	response = requests.post(
		"https://api.openai.com/v1/chat/completions",
		headers={
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
		},
		json={
			"model": model,
			"max_tokens": 4000,
			"messages": [{"role": "user", "content": prompt}],
		},
		timeout=90,
	)

	if response.status_code != 200:
		error_msg = response.json().get("error", {}).get("message", response.text)
		frappe.throw(f"OpenAI API error: {error_msg}")

	return response.json()["choices"][0]["message"]["content"]


def call_openai_api_with_system(api_key, model, system_prompt, messages):
	"""Call OpenAI API with system prompt and message history"""
	import requests

	openai_messages = [{"role": "system", "content": system_prompt}]
	for msg in messages:
		openai_messages.append({"role": msg["role"], "content": msg["content"]})

	response = requests.post(
		"https://api.openai.com/v1/chat/completions",
		headers={
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
		},
		json={
			"model": model,
			"max_tokens": 2000,
			"messages": openai_messages,
		},
		timeout=60,
	)

	if response.status_code != 200:
		error_msg = response.json().get("error", {}).get("message", response.text)
		frappe.throw(f"OpenAI API error: {error_msg}")

	return response.json()["choices"][0]["message"]["content"]
