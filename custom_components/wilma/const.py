"""Constants for the Wilma integration."""
from datetime import timedelta

DOMAIN = "wilma"

CONF_BASE_URL = "base_url"
CONF_TOTP_SECRET = "totp_secret"
CONF_STUDENTS = "students"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL_MINUTES = 30
DEFAULT_SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

PLATFORMS = ["sensor"]

# Triage classification buckets, mirrored from the wilma-triage skill's rules.
TRIAGE_ALWAYS = "always_report"
TRIAGE_BRIEF = "report_briefly"
TRIAGE_SKIP = "skip_silently"

ATTR_ITEMS = "items"
ATTR_FETCHED_AT = "fetched_at"
