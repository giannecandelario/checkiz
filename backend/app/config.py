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

# ---- Alert-free consistency checks (see app/consistency.py) -----------------
# These only add reason strings for the seller to read; none of them can change a
# verdict. The defaults below are placeholders for a typical order, not limits a
# wallet imposes - set them to what this shop actually sells, then re-check.
AMOUNT_MIN = float(os.getenv("CHECKIZ_AMOUNT_MIN", 1.0))
AMOUNT_MAX = float(os.getenv("CHECKIZ_AMOUNT_MAX", 50000.0))

# A receipt stamped in the future, or older than this, is worth a second look.
# Wallet and phone clocks drift and buyers re-send old screenshots, so this is a
# signal rather than proof.
RECEIPT_MAX_AGE_HOURS = float(os.getenv("CHECKIZ_RECEIPT_MAX_AGE_HOURS", 48))

# Hours ahead of UTC for the clock the shop reads receipts against (the
# Philippines is +8). Receipts show wall-clock time, so comparing one with a UTC
# server clock would call almost every receipt hours stale.
TZ_OFFSET_HOURS = float(os.getenv("CHECKIZ_TZ_OFFSET_HOURS", 8))

# Tried left to right, first parse wins, so list the order your wallets print.
# 03/04/2026 is ambiguous no matter how it is read - another reason this is a
# signal.
DATE_FORMATS = [f.strip() for f in os.getenv(
    "CHECKIZ_DATE_FORMATS",
    "%Y-%m-%d,%m/%d/%Y,%d/%m/%Y,%d %b %Y,%d %B %Y,%b %d %Y,%B %d %Y").split(",")]

# Words a receipt prints beside the value it labels. Two lists so another
# wallet's wording can be added without touching code. The currency symbol is
# deliberately not one of them: the amount regex only ever matches a number that
# already carries a symbol, so counting it as a label would make the check pass
# on every receipt and measure nothing.
AMOUNT_LABELS = [s.strip().lower() for s in os.getenv(
    "CHECKIZ_AMOUNT_LABELS", "amount,total,price,fee,balance,charged,paid").split(",")]
REF_LABELS = [s.strip().lower() for s in os.getenv(
    "CHECKIZ_REF_LABELS", "reference,ref,txn,trxn,transaction,control,serial,voucher").split(",")]

# How many lines either side of the value may still count as "beside it".
LAYOUT_LABEL_WINDOW = int(os.getenv("CHECKIZ_LAYOUT_LABEL_WINDOW", 1))

# ---- Photo quality (see parser.ocr_confidence) ------------------------------
# Tesseract's own mean confidence over the words it read, 0-100. Below this the
# seller is told to retake the photo, because a screen photographed at an angle
# or under glare loses digits that no rule can recover. It is advice only: it
# never changes a verdict, and a low number says nothing about whether the
# payment is real. Both samples in samples/ read about 94 under the Docker
# Tesseract, and the edited one a fraction higher than the real one, so this
# floor measures legibility, not tampering. Never measured on a phone photo of a
# real wallet receipt - task 6 owns that.
OCR_CONFIDENCE_MIN = float(os.getenv("CHECKIZ_OCR_CONFIDENCE_MIN", 60.0))
