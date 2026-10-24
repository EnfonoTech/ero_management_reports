# ERO Management Reports

Management sales reports and AI-powered analytics for ERPNext. A generic, multi-company Frappe app that provides an executive dashboard, 6 script reports, and Claude AI integration for automated insights and interactive chat.

## Features

- **Executive Dashboard** (`/app/reports-dashboard`) — KPI cards, report navigation, AI analytics
- **6 Script Reports** — Branch Sales, Top Selling Items, Monthly Sales Trend, Customer Analysis, Daily Summary, Monthly Summary
- **AI Visual Analysis** — Claude API generates charts, KPIs, insights, and recommendations from your sales data
- **AI Chat** — Interactive chat with fullscreen mode; ask questions about your data and get charts inline
- **Permission System** — Administrator configures which users can access reports via Settings
- **Multi-Company** — All reports have a Company filter; dashboard auto-detects default company
- **Dynamic Currency** — Currency symbols pulled from company settings (not hardcoded)

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/EnfonoTech/ero_management_reports.git
bench --site your-site.localhost install-app management_reports
bench --site your-site.localhost migrate
bench build --app management_reports
```

> **Note:** The internal app name is `management_reports` (Frappe app naming). The display name is "Management Reports".

## Additional Sales Sources

Some sites record part of their sales outside Sales Invoice, for example a counter sale that carries no tax.
List such a document under **Management Reports Settings → Additional Sales Sources** and the dashboard, the
sales reports and the AI data count it next to Sales Invoices: revenue, cost, invoices, customers, returns.

| Setting | Meaning |
|---|---|
| Document Type / Item Table Document Type | The submittable sale document and its item table |
| Net Total Field | What the customer was charged, after any discount (also the dashboard revenue) |
| Total Before Discount Field | Optional. When set, item amounts are scaled by net / this total so item reports match the net |
| Item Cost Field | Cost of goods on each item row (this is the COGS for that source) |
| Other field names | Optional: date, company, branch, customer, customer name, is-return, item qty / amount. Blank = the usual names |

Empty by default, so existing sites are unchanged. Fields are checked against doctype meta on save; a row that
later stops being valid is skipped and logged. Not covered: Collections by Payment Mode and Loyalty Points Redeemed
(they read Payment Entries / loyalty data, not sales documents).

## Post-Installation Setup

1. **Go to** `/app/management-reports-settings`
2. **Add users** who should have access (Administrator always has access by default)
3. **Configure AI** (optional): Paste your Anthropic API key and enable AI Analysis
4. **Visit** `/app/reports-dashboard` to see the dashboard

## Requirements

- Frappe Framework v15+
- ERPNext v15+
- Python 3.10+
- Anthropic API key (optional, for AI features)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, Frappe Framework |
| Frontend | Vanilla JS, Frappe UI, frappe.Chart |
| AI | Anthropic Claude API (claude-sonnet-4-20250514) |
| Database | MariaDB (via Frappe ORM + raw SQL) |
| Data Source | Sales Invoice, Sales Invoice Item doctypes |

## License

MIT
