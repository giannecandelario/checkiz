import os

# Reference number length. GCash receipts commonly show 13 digits; the original
# concept example had 12. Check real receipts, then set CHECKIZ_REF_LENGTH.
REF_LENGTH = int(os.getenv("CHECKIZ_REF_LENGTH", 13))

# Orders issued with a centavo code stay matchable for this many hours.
ORDER_TTL_HOURS = float(os.getenv("CHECKIZ_ORDER_TTL_HOURS", 24))

# Payments at or above this amount that were NOT read from the wallet app's own
# notification (SMS can be spoofed) are flagged "confirm in the app".
CONFIRM_ABOVE = float(os.getenv("CHECKIZ_CONFIRM_ABOVE", 2000))

# Android package names whose notifications count as app-sourced (trusted) alerts.
APP_PACKAGES = set(os.getenv("CHECKIZ_APP_PACKAGES",
                             "com.globe.gcash.android,com.paymaya").split(","))
