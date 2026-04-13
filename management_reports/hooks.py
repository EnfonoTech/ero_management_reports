app_name = "management_reports"
app_title = "Management Reports"
app_publisher = "Custom Apps"
app_description = "Management sales reports and AI-powered analytics for ERPNext"
app_email = "apps@example.com"
app_license = "mit"

required_apps = ["erpnext"]

# Pass allowed user flag to frontend on session boot
boot_session = "management_reports.management_reports.boot.boot_session"
