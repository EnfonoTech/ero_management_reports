# Architecture & Codebase Guide

This document describes the full architecture of the ERO Management Reports app so any developer or AI agent can continue development.

## Directory Structure

```
management_reports/                          # Frappe app root (pip-installable)
├── pyproject.toml                       # Python package config
├── README.md                            # Project overview
├── docs/                                # Documentation
│   ├── ARCHITECTURE.md                  # This file
│   ├── AGENT_HANDOFF.md                 # Quick-start for AI agents
│   └── API_REFERENCE.md                 # All API endpoints
├── management_reports/                      # Python package
│   ├── __init__.py                      # Version: 0.0.1
│   ├── hooks.py                         # Frappe hooks (boot_session, app metadata)
│   ├── modules.txt                      # Module list: "Management Reports"
│   ├── patches.txt                      # Migration patches (empty)
│   ├── public/                          # Static assets (.gitkeep)
│   └── management_reports/                  # "Management Reports" module
│       ├── boot.py                      # boot_session hook — passes access flag to frontend
│       ├── permissions.py               # Core permission logic (is_allowed_user, check_access)
│       ├── doctype/                     # DocTypes
│       │   ├── management_reports_settings/  # Single DocType — app config
│       │   └── management_reports_user/      # Child Table — allowed users list
│       ├── page/                        # Pages
│       │   └── reports_dashboard/       # Main dashboard page
│       │       ├── reports_dashboard.json    # Page definition
│       │       ├── reports_dashboard.py     # KPI API endpoint
│       │       ├── reports_dashboard.js     # Full dashboard UI
│       │       ├── reports_dashboard.css    # All styles
│       │       └── ai_analysis.py           # AI endpoints (analysis + chat)
│       └── report/                      # Script Reports (6 total)
│           ├── branch_sales_dashboard/
│           ├── top_selling_items/
│           ├── monthly_sales_trend/
│           ├── customer_analysis/
│           ├── daily_summary/
│           └── monthly_summary/
```

## Key Patterns

### 1. Frappe Script Report Pattern
Each report has 3 files:
- **`report_name.json`** — Metadata (ref_doctype, roles, report_type: "Script Report")
- **`report_name.py`** — Backend logic with `execute(filters)` returning `(columns, data, message, chart, report_summary)`
- **`report_name.js`** — Frontend config with `frappe.query_reports["Report Name"] = { filters: [...], formatter: ... }`

### 2. Permission System (Two-Layer)
```
Layer 1: Frappe Role-based (report JSON "roles" array)
  → Management, Accounts Manager, System Manager can see reports in sidebar

Layer 2: App-level whitelist (permissions.py check_access())
  → Only users in Management Reports Settings → allowed_users table
  → Administrator always bypasses
  → Called at start of every report's execute() and every API endpoint
```

**Frontend access gate:**
```javascript
// boot.py sets frappe.boot.management_reports_access
if (frappe.boot.management_reports_access === false) {
    // Show "Access Restricted" message
}
```

### 3. Company Filter Pattern
Every report JS file has Company as the first required filter:
```javascript
{
    fieldname: "company",
    label: __("Company"),
    fieldtype: "Link",
    options: "Company",
    default: frappe.defaults.get_user_default("Company"),
    reqd: 1,
}
```

Branch filter is linked to Company:
```javascript
{
    fieldname: "branch",
    fieldtype: "Link",
    options: "Cost Center",
    get_query: function() {
        return { filters: { company: frappe.query_report.get_filter_value("company") } };
    }
}
```

Python side adds `AND si.company = %(company)s` in all queries.

### 4. Dynamic Currency
Never hardcode "SAR". Every report has:
```python
def get_currency(filters):
    company = filters.get("company")
    if company:
        return frappe.get_cached_value("Company", company, "default_currency") or "SAR"
    return "SAR"
```

Column labels use: `_("Revenue ({0})").format(currency)`

### 5. Dynamic Company Abbreviation
For chart labels, strip company abbreviation from Cost Center names:
```python
abbr = frappe.get_cached_value("Company", company, "abbr") or ""
short_name = branch.replace(f" - {abbr}", "").strip()
```

### 6. Data Source: Sales Invoice
All reports query from these two tables:
- **`tabSales Invoice`** (alias `si`) — Header: posting_date, company, cost_center, customer, grand_total, docstatus, is_return
- **`tabSales Invoice Item`** (alias `sii`) — Lines: item_code, item_name, item_group, amount, qty, incoming_rate, stock_uom

Key calculations:
| Metric | Formula |
|--------|---------|
| Revenue (per item line) | `sii.amount` |
| Revenue (per invoice) | `si.grand_total` |
| COGS | `sii.qty * sii.incoming_rate` |
| Profit | `revenue - COGS` |
| Margin % | `profit / revenue * 100` |
| Only submitted | `si.docstatus = 1` |

### 7. MTD Fallback Logic
Dashboard KPIs show Month-to-Date data. If MTD revenue is 0 (e.g., it's early in the month or no data yet), it falls back to last completed month:
```python
if not mtd_revenue:
    prev_month_end = add_months(mtd_start, 0) - timedelta(days=1)
    prev_month_start = get_first_day(prev_month_end)
    # Query previous month data...
    last_month_label = "Mar 2026"  # Dynamic label
```
Frontend relabels KPI cards: "Mar 2026 Revenue" instead of "MTD Revenue".

## AI Integration Architecture

### Visual Analysis Flow
```
User clicks "Generate Analysis"
  → JS calls get_ai_analysis(company)
  → Python gathers 3 months of data (gather_analysis_data)
  → Builds structured prompt requesting JSON response
  → Calls Claude API (call_claude_api)
  → Parses JSON response (parse_ai_response)
  → Returns structured object: {summary, kpis[], charts[], insights[], recommendations[]}
  → JS renders: summary banner, KPI cards, frappe.Chart instances, insight cards, recommendation list
```

### Chat Flow
```
User types message
  → JS sends to chat_with_ai(company, message, history)
  → Python builds system prompt with all sales data context
  → Sends conversation history (last 10 messages) + new message to Claude
  → Returns markdown response (may include ```chart blocks)
  → JS extracts chart blocks → renders with frappe.Chart
  → Converts remaining markdown to HTML (tables get scrollable wrappers)
```

### AI Response Formats

**Visual Analysis** returns structured JSON:
```json
{
  "summary": "Executive summary text",
  "kpis": [{"label": "Total Revenue", "value": "1.2M", "prefix": "SAR", "change": "+5%", "color": "blue"}],
  "charts": [{"title": "...", "type": "bar", "labels": [...], "datasets": [...], "colors": [...]}],
  "insights": [{"icon": "trending-up", "title": "...", "text": "...", "type": "success|warning|info|danger"}],
  "recommendations": ["Action item 1", "Action item 2"]
}
```

**Chat** returns markdown with optional chart blocks:
````
Here's the revenue comparison:

```chart
{"type": "bar", "title": "Branch Revenue", "labels": ["A", "B"], "datasets": [{"name": "Revenue", "values": [100, 200]}], "colors": ["#0f3460"]}
```
````

## DocType Schemas

### Management Reports Settings (Single)
| Field | Type | Details |
|-------|------|---------|
| allowed_users | Table (Management Reports User) | Users with access |
| anthropic_api_key | Password | Claude API key |
| ai_model | Select | claude-sonnet-4-20250514, claude-3-5-haiku-20241022 |
| enable_ai_analysis | Check | Default: 1 |
| auto_email_enabled | Check | For future auto email feature |
| email_frequency | Select | Daily/Weekly/Monthly |
| email_recipients | Small Text | Comma-separated emails |

### Management Reports User (Child Table)
| Field | Type | Details |
|-------|------|---------|
| user | Link → User | Required |
| full_name | Data | Read-only, fetch_from: user.full_name |

## Report Details

### 1. Branch Sales Dashboard
- **Purpose:** Compare revenue, profit, margins across branches
- **Filters:** Company (reqd), Period selector, From/To Date, Branch
- **Columns:** Branch, Invoices, Customers, Revenue, COGS, Gross Profit, Margin%
- **Chart:** Monthly revenue by branch (grouped bar)
- **Summary:** Total Revenue, Total Profit, Total Invoices, Avg Margin

### 2. Top Selling Items
- **Purpose:** Ranked list of best-performing products
- **Filters:** Company, Period, From/To Date, Branch, Item Group, Limit (default 50)
- **Columns:** Rank, Item Code, Item Name, Item Group, UOM, Qty, Invoices, Revenue, COGS, Profit, Margin%
- **Chart:** Top 10 items (Revenue vs Profit bar)
- **Summary:** Total Revenue, Total Profit, Total Qty, Avg Margin

### 3. Monthly Sales Trend
- **Purpose:** Track revenue growth month-over-month
- **Filters:** Company (reqd), Period selector, From/To Date, Branch
- **Columns:** Month, Branch, Invoices, Revenue, COGS, Profit, Margin%, Revenue Growth%
- **Chart:** Multi-line showing revenue trend by branch
- **Summary:** Total Revenue, Total Profit, Total Invoices

### 4. Customer Analysis
- **Purpose:** Customer revenue distribution and top accounts
- **Filters:** Company (reqd), Period, From/To Date, Branch
- **Columns:** Customer, Customer Name, Branch, Invoices, Revenue, Share%, Avg Invoice
- **Chart:** Donut chart of top 10 customers
- **Summary:** Total Revenue, Customer Count, Total Invoices, Avg Invoice

### 5. Daily Summary
- **Purpose:** End-of-day P&L snapshot per branch
- **Filters:** Company (reqd), Date (reqd, single day), Branch
- **Columns:** Date, Branch, Invoices, Income, Expenses, Profit, Margin%
- **Special:** Includes credit note returns as additional expenses
- **Chart:** Bar chart per branch (Income vs Expenses vs Profit)
- **Summary:** Day's Income, Expenses, Profit, Margin

### 6. Monthly Summary
- **Purpose:** Monthly P&L with branch breakdown
- **Filters:** Company (reqd), From Date, To Date, Branch
- **Columns:** Month, Branch, Income, Expenses, Gross Profit, Margin%, Invoices, Avg Invoice
- **Chart:** Grouped bar (Income + Expenses + Profit per month)
- **Summary:** Total Income, Expenses, Profit, Avg Monthly Income

## Dashboard Page Components

The dashboard JS (`reports_dashboard.js`) renders:

1. **Header** — Dynamic company name + subtitle
2. **KPI Grid** — 5 cards (MTD Revenue, 12M Revenue, MTD Invoices, Active Branches, MTD Customers)
3. **Report Cards** — 6 clickable cards linking to each report
4. **AI Analytics Section** — Two tabs:
   - **Visual Analysis** — "Generate Analysis" button → renders structured AI response
   - **Chat with AI** — Full chat interface with suggestions, fullscreen, clear

## CSS Architecture

Single file (`reports_dashboard.css`) with sections:
- Dashboard header, KPI grid, report cards
- AI section: tabs, summary banner, KPI cards, chart cards, insights, recommendations
- Chat: container, header, messages (user/assistant), typing animation, input area, suggestions
- Fullscreen: fixed positioning with z-index 1050
- Table wrapper: scrollable tables in chat responses

## Build & Development

```bash
# Development cycle
bench build --app management_reports
bench --site your-site.localhost clear-cache

# After schema changes
bench --site your-site.localhost migrate

# Full rebuild
bench --site your-site.localhost migrate && bench build --app management_reports && bench --site your-site.localhost clear-cache
```

## Environment Notes

- **Bench directory:** `/Users/sayanthns/Tabiah`
- **App directory:** `/Users/sayanthns/Tabiah/apps/management_reports`
- **Site:** `tabiah.localhost` (port 8002)
- **PATH for bench:** `export PATH="/opt/homebrew/bin:/Users/sayanthns/.pyenv/shims:/Users/sayanthns/.pyenv/bin:/Users/sayanthns/.local/bin:$PATH"`
- **Redis ports:** 13001 (cache), 11001 (queue) — may need manual start: `redis-server --port 13001 --daemonize yes`
- **GitHub repo:** https://github.com/EnfonoTech/ero_management_reports
