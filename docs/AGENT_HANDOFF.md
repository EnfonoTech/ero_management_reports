# Agent Handoff Guide

Quick-start guide for any AI agent continuing development on this project.

## What This App Is

A Frappe/ERPNext app called `management_reports` (display name: "Management Reports") that provides:
- An executive dashboard page at `/app/reports-dashboard`
- 6 script reports for sales analytics
- AI-powered analysis and chat using Claude API
- User-level access control via a Settings doctype

## Critical Things to Know

### 1. Internal Name vs Display Name
The Frappe app name is **`management_reports`** but the user-facing name is **"Management Reports"** / **"ERO Management Reports"**. All imports use `management_reports.management_reports.*`.

### 2. Module Name
The Frappe module is `"Management Reports"` (in `modules.txt`). All doctypes and reports belong to this module.

### 3. Bench Commands Need PATH
```bash
export PATH="/opt/homebrew/bin:/Users/sayanthns/.pyenv/shims:/Users/sayanthns/.pyenv/bin:/Users/sayanthns/.local/bin:$PATH"
```
Always prepend this before `bench` commands.

### 4. Redis May Need Manual Start
```bash
redis-server --port 13001 --daemonize yes
redis-server --port 11001 --daemonize yes
```

### 5. Build After Changes
```bash
# After JS/CSS changes:
bench build --app management_reports && bench --site tabiah.localhost clear-cache

# After Python/JSON schema changes:
bench --site tabiah.localhost migrate && bench build --app management_reports && bench --site tabiah.localhost clear-cache
```

### 6. The Site
- **Site:** `tabiah.localhost`
- **Port:** 8002
- **URL:** `http://tabiah.localhost:8002`
- **Bench dir:** `/Users/sayanthns/Tabiah`
- **App dir:** `/Users/sayanthns/Tabiah/apps/management_reports`

### 7. Git Remote
```
origin → https://github.com/EnfonoTech/ero_management_reports.git (main branch)
```

## File Map — Where to Edit What

| Task | File(s) |
|------|---------|
| Add a new report | Create 3 files in `report/new_name/` (.py, .js, .json) + `__init__.py` |
| Change dashboard KPIs | `page/reports_dashboard/reports_dashboard.py` (backend) + `.js` (frontend) |
| Change dashboard UI/layout | `page/reports_dashboard/reports_dashboard.js` |
| Change dashboard styling | `page/reports_dashboard/reports_dashboard.css` |
| Modify AI analysis prompt | `page/reports_dashboard/ai_analysis.py` → `build_analysis_prompt()` |
| Modify AI chat behavior | `page/reports_dashboard/ai_analysis.py` → `chat_with_ai()` system prompt |
| Add a new API endpoint | Add `@frappe.whitelist()` function in appropriate .py file |
| Change permissions | `permissions.py` for logic; Settings doctype for config |
| Add app settings | `doctype/management_reports_settings/management_reports_settings.json` |
| Add hooks | `hooks.py` |
| Add migration patch | `patches.txt` + create patch file in `patches/` |

## How Reports Work

Every report follows this exact pattern:

**Python** (`report_name.py`):
```python
from management_reports.management_reports.permissions import check_access

def execute(filters=None):
    check_access()                     # MUST be first line
    columns = get_columns(filters)
    data = get_data(filters)
    chart = get_chart(data)
    report_summary = get_report_summary(data, filters)
    return columns, data, None, chart, report_summary

def get_conditions(filters):
    conditions = ""
    if filters.get("company"):
        conditions += " AND si.company = %(company)s"     # MUST include
    if filters.get("branch"):
        conditions += " AND si.cost_center = %(branch)s"
    return conditions

def get_currency(filters):
    company = filters.get("company")
    if company:
        return frappe.get_cached_value("Company", company, "default_currency") or "SAR"
    return "SAR"
```

**JavaScript** (`report_name.js`):
```javascript
frappe.query_reports["Report Name"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        // ... more filters
    ],
    formatter: function(value, row, column, data, default_formatter) {
        // Color-code cells
    }
};
```

**JSON** (`report_name.json`):
```json
{
    "name": "Report Name",
    "ref_doctype": "Sales Invoice",
    "report_type": "Script Report",
    "is_standard": "Yes",
    "module": "Management Reports",
    "roles": [
        {"role": "System Manager"},
        {"role": "Accounts Manager"},
        {"role": "Management"}
    ]
}
```

## SQL Patterns

All reports query Sales Invoice + Sales Invoice Item:
```sql
SELECT ...
FROM `tabSales Invoice Item` sii
INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
WHERE si.docstatus = 1
    AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
    AND si.company = %(company)s
GROUP BY ...
```

Key fields:
- `sii.amount` = revenue per item line
- `sii.qty * sii.incoming_rate` = COGS per item line
- `si.grand_total` = total invoice amount
- `si.cost_center` = branch
- `si.customer` / `si.customer_name` = customer
- `si.is_return = 1` = credit note/return

## Known Issues & Gotchas

1. **`frappe.boot.management_reports_access`** — Check with `=== false`, not `!value`, because `undefined` (before boot hook loads) would block access
2. **MTD = 0** — If current month has no invoices, KPIs show 0. The fallback logic displays last completed month instead
3. **AI API timeout** — Claude API calls have 90s timeout for analysis, 60s for chat. Large datasets may take a while
4. **Chart rendering** — `frappe.Chart` needs DOM element to exist before rendering. Use `setTimeout(..., 100)` after inserting HTML
5. **`bench` not in PATH** — Always export PATH before running bench commands
6. **Redis ports** — If bench commands fail with "redis_cache not running", manually start redis on ports 13001 and 11001

## Pending / Future Work

1. **Auto Email Reports** — Settings fields exist (auto_email_enabled, email_frequency, email_recipients) but the email sending logic is NOT implemented yet. Would need a scheduled task via Frappe's hooks (scheduler_events)
2. **GitHub repo cleanup** — The accidental `sayanthns/management_reports` repo should be manually deleted
3. **Frappe Cloud deployment** — App needs to be added to FC via Dashboard → Apps → New App → From GitHub (EnfonoTech/ero_management_reports)
4. **App rename** — The internal Frappe app name is still `management_reports`. A full rename would require renaming the directory, all imports, and module references. Not recommended unless necessary
5. **Additional AI models** — Settings has a model selector; new models can be added to the Select options in the doctype JSON
6. **Purchase/Expense reports** — Currently only Sales Invoice data. Could extend to Purchase Invoice, Journal Entry, etc.
7. **Export to PDF** — Dashboard could have a "Download PDF" button for AI analysis results
8. **Dark mode** — CSS uses Frappe CSS variables which should support dark mode, but not tested

## Testing Checklist

After any changes, verify:
- [ ] Dashboard loads at `/app/reports-dashboard`
- [ ] KPI cards show values (or fallback last month)
- [ ] All 6 report cards navigate correctly
- [ ] Company filter works in each report
- [ ] Branch filter filters by selected company
- [ ] Charts render in reports
- [ ] AI "Generate Analysis" button works (if API key configured)
- [ ] AI Chat sends/receives messages
- [ ] Chat fullscreen toggle works
- [ ] Settings page accessible at `/app/management-reports-settings`
- [ ] Non-allowed user sees "Access Restricted" on dashboard
- [ ] Non-allowed user gets PermissionError on report execution
