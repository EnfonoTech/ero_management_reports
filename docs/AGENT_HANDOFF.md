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

### 3. This App Ships to Many Sites
Same code everywhere. Everything that differs between clients lives in
**Management Reports Settings** records — the branch dimension, the branch label,
whether COGS is trustworthy, AI keys. Never fork or branch per client, and never
hardcode a client's field, currency or terminology into the app.

### 4. Bench Commands Need PATH
```bash
export PATH="/opt/homebrew/bin:$HOME/.pyenv/shims:$HOME/.pyenv/bin:$HOME/.local/bin:$PATH"
```
Prepend this if `bench` does not resolve.

### 5. Redis May Need Manual Start
Use the ports from the bench's `sites/common_site_config.json`:
```bash
redis-server --port 13000 --daemonize yes
redis-server --port 11000 --daemonize yes
```

### 6. Build After Changes
```bash
# After JS/CSS changes:
bench build --app management_reports && bench --site your-site.localhost clear-cache

# After Python/JSON schema changes:
bench --site your-site.localhost migrate && bench build --app management_reports && bench --site your-site.localhost clear-cache
```

### 7. Run the Tests
```bash
bench --site your-site.localhost run-tests --app management_reports
```

### 8. Git Remote
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
| Change permissions | `permissions.py` for the allowlist gate; `utils/scope.py` for branch row security; Settings doctype for config |
| Change how a site models "branch" | Management Reports Settings → Data Source. Code change only in `utils/dimensions.py` |
| Add a shared query helper | `utils/query.py` |
| Add a test | `management_reports/tests/` |
| Add app settings | `doctype/management_reports_settings/management_reports_settings.json` |
| Add hooks | `hooks.py` |
| Add migration patch | `patches.txt` + create patch file in `patches/` |

## How Reports Work

Every report follows this exact pattern:

**Python** (`report_name.py`):
```python
from management_reports.management_reports.permissions import check_access
from management_reports.utils.currency import get_currency
from management_reports.utils.query import base_query, cogs_expression, rounded_sum

def execute(filters=None):
    check_access()                     # MUST be first line
    columns = get_columns(filters)
    data = get_data(filters)
    chart = get_chart(data)
    report_summary = get_report_summary(data, filters)
    return columns, data, None, chart, report_summary

def get_data(filters):
    # base_query applies docstatus, date range, company, branch filter AND the
    # user's branch scope. Never hand-roll these — a report that skips
    # base_query leaks other branches' numbers.
    ctx = base_query(filters)
    return (
        ctx.query.select(
            ctx.branch_column.as_("branch"),
            rounded_sum(ctx.SII.amount).as_("revenue"),
        )
        .groupby(ctx.branch_column)
        .run(as_dict=True)
    )
```

Rules for any new report:
- Go through `base_query()`. No raw SQL, no string-built WHERE clauses.
- Get the branch column from `ctx.branch_column`, never `si.cost_center`.
- Get the branch column label and link doctype from `ctx.dim` / `get_branch_dimension()`.
- Get currency from `utils.currency.get_currency(company)`. Never hardcode "SAR".
- Gate COGS / Profit / Margin columns on `cogs_available()`.
- Set `row["currency"]` on every row that has a Currency column.

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

## Query Patterns

All reports query Sales Invoice + Sales Invoice Item through
`utils/query.base_query()`, which emits the equivalent of:

```sql
SELECT ...
FROM `tabSales Invoice Item` sii
INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
WHERE si.docstatus = 1
    AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
    AND si.company = %(company)s
    AND si.<branch_dimension> IN (<user's permitted branches>)
GROUP BY ...
```

Key fields:
- `sii.amount` = revenue per item line
- `sii.qty * sii.incoming_rate` = COGS per item line (gate on `cogs_available()`)
- `si.grand_total` = total invoice amount
- `ctx.branch_column` = branch (resolved per site; `si.cost_center` by default)
- `si.customer` / `si.customer_name` = customer
- `si.is_return = 1` = credit note/return (`base_query(..., only_returns=True)`)

## Known Issues & Gotchas

1. **`frappe.boot.management_reports_access`** — Check with `=== false`, not `!value`, because `undefined` (before boot hook loads) would block access
2. **MTD = 0** — If current month has no invoices, KPIs show 0. The fallback logic displays last completed month instead
3. **AI API timeout** — Claude API calls have 90s timeout for analysis, 60s for chat. Large datasets may take a while
4. **Chart rendering** — `frappe.Chart` needs DOM element to exist before rendering. Use `setTimeout(..., 100)` after inserting HTML
5. **`bench` not in PATH** — Always export PATH before running bench commands
6. **Redis ports** — If bench commands fail with "redis_cache not running", start redis on the ports named in the bench's `sites/common_site_config.json`
7. **Never use `frappe.db.get_single_value` for this app's Settings** — it loads DocType meta and raises `DoesNotExistError` before the DocTypes are synced, which breaks `install-app`. Use `utils.settings.get_setting()`, which reads Singles directly
8. **`get_permitted_branches()` returns `None` for unrestricted** — a list, including an empty one, means restricted. Treating a falsy return as unrestricted turns a scoping bug into a data leak
9. **Returns are counted twice in Daily Summary** — credit notes already reduce `income` through their negative `sii.amount`, and the returns query then adds `abs(...)` to `expenses` again. Behaviour was preserved during the query refactor because clients' historical numbers depend on it. Decide deliberately before changing it

## Pending / Future Work

1. **Auto Email Reports** — Settings fields exist (auto_email_enabled, email_frequency, email_recipients) but no scheduler is wired. Prefer Frappe's built-in **Auto Email Report** for raw report delivery (it already has Daily/Weekdays/Weekly/Monthly, `dynamic_date_period` and `send_if_data`) and a custom `scheduler_events` job only for the AI narrative digest. Any custom sender must be idempotent — `job_name` plus a run-log re-check inside the worker, since a digest emailed twice to a client CFO is not recoverable
2. **GitHub repo cleanup** — The accidental `sayanthns/management_reports` repo should be manually deleted
3. **Frappe Cloud deployment** — App needs to be added to FC via Dashboard → Apps → New App → From GitHub (EnfonoTech/ero_management_reports)
4. **App rename** — The internal Frappe app name is still `management_reports`. A full rename would require renaming the directory, all imports, and module references. Not recommended unless necessary
5. **Additional AI models** — Settings has a model selector; new models can be added to the Select options in the doctype JSON
6. **Purchase/Expense reports** — Currently only Sales Invoice data. Could extend to Purchase Invoice, Journal Entry, etc.
7. **Export to PDF** — Dashboard could have a "Download PDF" button for AI analysis results
8. **Dark mode** — CSS uses Frappe CSS variables which should support dark mode, but not tested

## Testing Checklist

Run the suite first — it covers the dimension resolver, branch scoping and
execution of all six reports:
```bash
bench --site your-site.localhost run-tests --app management_reports
```

Then verify by hand:
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
- [ ] A user with a **User Permission** on one Cost Center sees only that branch in every report, and matching KPI cards
- [ ] Setting COGS Source to `None` hides COGS / Profit / Margin columns and summary tiles
- [ ] Changing Branch Label to e.g. `Outlet` relabels the column and filter across all six reports
