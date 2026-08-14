app_name = "management_reports"
app_title = "Management Reports"
app_publisher = "Custom Apps"
app_description = "Management sales reports and AI-powered analytics for ERPNext"
app_email = "apps@example.com"
app_license = "mit"

required_apps = ["erpnext"]

# Pass allowed user flag and the site's branch dimension to the frontend
boot_session = "management_reports.management_reports.boot.boot_session"

# Runs hourly and returns immediately unless this is the configured send hour.
# Hourly rather than daily so one app can serve sites across KSA, UAE and India
# timezones with only a Settings change.
scheduler_events = {
	"cron": {
		"0 * * * *": [
			"management_reports.management_reports.tasks.send_scheduled_reports",
		],
	},
}
