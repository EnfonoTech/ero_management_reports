# API Reference

All endpoints are Frappe whitelisted methods called via `frappe.call()`.

## Dashboard APIs

### `get_dashboard_kpis`

**Method:** `management_reports.management_reports.page.reports_dashboard.reports_dashboard.get_dashboard_kpis`

**Args:**
| Param | Type | Required | Default |
|-------|------|----------|---------|
| company | string | No | User's default company |

**Returns:**
```json
{
  "company": "Company Name",
  "currency": "SAR",
  "mtd_revenue": 150000.00,
  "mtd_invoices": 245,
  "mtd_customers": 89,
  "last_12m_revenue": 1800000.00,
  "active_branches": 5,
  "last_month_revenue": 120000.00,
  "last_month_invoices": 200,
  "last_month_customers": 75,
  "last_month_label": "Mar 2026"
}
```

**Notes:**
- If `mtd_revenue` is 0 (no data this month), `last_month_*` fields contain previous month data as fallback
- Frontend should check `mtd_revenue` — if 0, display `last_month_*` values with `last_month_label`

---

## AI APIs

### `get_ai_analysis`

**Method:** `management_reports.management_reports.page.reports_dashboard.ai_analysis.get_ai_analysis`

**Args:**
| Param | Type | Required | Default |
|-------|------|----------|---------|
| company | string | No | User's default company |

**Returns (success):**
```json
{
  "success": true,
  "summary": "Executive summary of sales performance...",
  "kpis": [
    {
      "label": "Total Revenue",
      "value": "1.2M",
      "prefix": "SAR",
      "suffix": "",
      "change": "+5.2%",
      "color": "blue"
    }
  ],
  "charts": [
    {
      "title": "Revenue by Branch (Monthly)",
      "type": "bar",
      "labels": ["Jan 2026", "Feb 2026", "Mar 2026"],
      "datasets": [
        {"name": "Branch1", "values": [100000, 120000, 130000]},
        {"name": "Branch2", "values": [80000, 90000, 95000]}
      ],
      "colors": ["#0f3460", "#2d6a4f", "#e07c24"]
    }
  ],
  "insights": [
    {
      "icon": "trending-up",
      "title": "Strong Growth",
      "text": "Revenue increased 8% month-over-month...",
      "type": "success"
    }
  ],
  "recommendations": [
    "Focus marketing efforts on Branch X which shows 15% growth",
    "Review pricing for items with negative margins"
  ]
}
```

**Returns (error):**
```json
{
  "error": "Please configure your Anthropic API key in Management Reports Settings."
}
```

**Returns (parse failure):**
```json
{
  "success": false,
  "markdown": "Raw AI response text...",
  "error": "Could not parse structured response"
}
```

**Prerequisites:**
- Anthropic API key configured in Management Reports Settings
- `enable_ai_analysis` checked in settings
- Analyzes last 3 months of Sales Invoice data

---

### `chat_with_ai`

**Method:** `management_reports.management_reports.page.reports_dashboard.ai_analysis.chat_with_ai`

**Args:**
| Param | Type | Required | Default |
|-------|------|----------|---------|
| company | string | No | User's default company |
| message | string | Yes | "" |
| history | string (JSON) | No | "[]" |

**History format** (JSON string of array):
```json
[
  {"role": "user", "content": "Compare branch performance"},
  {"role": "assistant", "content": "Here's the comparison..."}
]
```

**Returns (success):**
```json
{
  "response": "Markdown text with optional ```chart blocks..."
}
```

**Returns (error):**
```json
{
  "error": "Error message"
}
```

**Notes:**
- Keeps last 10 messages from history for context
- System prompt includes all sales data (monthly by branch, top items, top customers, negative margin items)
- Response may contain ```` ```chart ``` ```` blocks with JSON chart configs
- Supported chart types: bar, line, donut, pie, percentage

---

## Report Endpoints

All reports follow the Frappe Script Report pattern. They are not called directly — Frappe's report engine calls `execute(filters)` internally.

### Common Filters (all reports)

| Filter | Type | Required | Notes |
|--------|------|----------|-------|
| company | Link → Company | Yes | First filter, pre-filled with default |
| branch | Link → Cost Center | No | Filtered by selected company |

### Report-Specific Filters

| Report | Additional Filters |
|--------|--------------------|
| Branch Sales Dashboard | period (Select), from_date, to_date |
| Top Selling Items | period, from_date, to_date, item_group, limit (Int, default 50) |
| Monthly Sales Trend | period, from_date, to_date |
| Customer Analysis | period, from_date, to_date |
| Daily Summary | date (Date, required — single day) |
| Monthly Summary | from_date, to_date |

### Period Quick Selector
Reports with a `period` filter have preset options:
- Financial Year, Last 10 Days, Last 30 Days, Last 60 Days, Last 90 Days, Last 6 Months, Last 1 Year

When a period is selected, `from_date` and `to_date` are auto-calculated and set.

---

## Internal Python Functions

### `permissions.py`

```python
is_allowed_user(user=None) → bool
# Returns True if user is Administrator or is in allowed_users table
# Returns False if allowed_users table is empty (no users configured beyond admin)

check_access()
# Calls is_allowed_user(); throws frappe.PermissionError if False
# Call at start of every report execute() and API endpoint
```

### `boot.py`

```python
boot_session(bootinfo)
# Sets bootinfo.management_reports_access = is_allowed_user()
# Frontend reads: frappe.boot.management_reports_access
```

### `ai_analysis.py` (internal)

```python
gather_analysis_data(company) → dict
# Returns: {company, currency, period, monthly_branch[], top_items[], top_customers[], negative_margin_items[]}
# Data covers last 3 months

build_analysis_prompt(data, company) → str
# Builds Claude prompt requesting structured JSON response

parse_ai_response(raw_response, data) → dict
# Extracts JSON from ```json blocks in response

call_claude_api(api_key, model, prompt) → str
# Single-message API call to Anthropic

call_claude_api_with_system(api_key, model, system_prompt, messages) → str
# Multi-message API call with system prompt (for chat)
```
