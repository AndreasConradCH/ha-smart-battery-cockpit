"""Constants for Smart Battery Cockpit."""

DOMAIN = "smart_battery_cockpit"

DB_FILENAME = "smart_battery_cockpit.db"

CONF_NOTIFY_SERVICE = "notify_service"
CONF_ROUNDTRIP_HOUR = "roundtrip_hour"
CONF_JUMP_THRESHOLD = "jump_threshold"
CONF_EXCLUDE_RECHARGEABLE = "exclude_rechargeable"
CONF_SHOW_SIDEBAR = "show_sidebar"

DEFAULT_NOTIFY_SERVICE = ""
DEFAULT_ROUNDTRIP_HOUR = 3
DEFAULT_JUMP_THRESHOLD = 25
DEFAULT_MIN_NEW_LEVEL = 80
DEFAULT_BASELINE_GLITCH_THRESHOLD = 75
DEFAULT_EXCLUDE_RECHARGEABLE = True
DEFAULT_SHOW_SIDEBAR = True

PANEL_URL_PATH = "smart-battery-cockpit"
PANEL_TITLE = "Battery Cockpit"
PANEL_ICON = "mdi:battery-sync"
STATIC_URL_PATH = "/smart_battery_cockpit_static"

SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"

# Heuristics to exclude non-smart-home rechargeable devices (phones, tablets, laptops, vacuums)
RECHARGEABLE_MODEL_KEYWORDS = (
    "iphone",
    "ipad",
    "macbook",
    "pixel",
    "galaxy",
    "oneplus",
    "cph",
    "sm-g",
    "sm-s",
    "windows nt",
    "matebook",
    "thinkpad",
    "lenovo",
    "tb330",
    "roborock",
    "vacuum",
    "roomba",
    "dreame",
    "watch",
)
