"""Checks a receipt can answer about itself, with no payment alert to compare it to.

Every function here is pure: it takes the fields the parser read (plus the raw OCR
text for the layout check) and returns one short reason string, or None when the
check passes or has nothing to work with. The verdict engine collects them into
`signals`, shows them on the verdict, and stores them with it.

They are signals, not proof, and that is the whole design. A genuine receipt can
fail one of these because the photo came in at an odd angle, because a wallet
words its receipt differently, because the phone's clock and the server's do not
agree, or because this shop has not set its own amount range yet. So nothing in
this module can change a status. The hard rules stay where they were: no
reference to match on, a reference already claimed, and an amount that
contradicts the ledger or the order's coded QR.
"""
import math
import re
from datetime import datetime, timedelta, timezone

from .config import (AMOUNT_LABELS, AMOUNT_MAX, AMOUNT_MIN, DATE_FORMATS,
                     LAYOUT_LABEL_WINDOW, REF_LABELS, REF_LENGTH,
                     RECEIPT_MAX_AGE_HOURS, TZ_OFFSET_HOURS)

# A buyer taps "just now" and the seller checks it seconds later; the two clocks
# are never exactly in step, so a slightly future stamp is not worth mentioning.
FUTURE_TOLERANCE = timedelta(minutes=30)
TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p")


def shop_now():
    """The wall clock receipts are stamped against."""
    return datetime.now(timezone(timedelta(hours=TZ_OFFSET_HOURS)))

# The reference pattern in app/parser.py only ever returns REF_LENGTH digits, so
# a short or long number is not a reference at all and the verdict says "missing".
# This is the looser look that lets the check explain itself: "the closest number
# had 12 digits" tells the seller more than "no reference".
REF_RUN_RE = re.compile(r"(?<!\d)(\d(?: ?\d){7,19})(?!\d)")
NEAR_LENGTH = 2


def check_reference(ref, text=None):
    if ref:
        s = str(ref)
        if not s.isdigit():
            return f"Reference {s} is not a plain string of digits"
        if len(set(s)) == 1:
            return f"Reference {s} is the same digit repeated"
        if len(s) != REF_LENGTH:
            return f"Reference {s} has {len(s)} digits, this shop expects {REF_LENGTH}"
        return None
    if not text:
        return None
    runs = [re.sub(" ", "", r) for r in REF_RUN_RE.findall(text)]
    near = [r for r in runs if len(set(r)) > 1 and abs(len(r) - REF_LENGTH) <= NEAR_LENGTH]
    if not near:
        return None
    closest = max(near, key=len)
    return (f"No {REF_LENGTH}-digit reference found; the closest number read was "
            f"{closest}, {len(closest)} digits")

def check_amount(value):
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"Amount {value} is not a number"
    if not math.isfinite(v):
        return f"Amount {value} is not a number"
    if round(v, 2) != v:
        return f"Amount {v} is not pesos and centavos (two decimals)"
    if v < AMOUNT_MIN or v > AMOUNT_MAX:
        return (f"Amount {v:.2f} is outside the {AMOUNT_MIN:.2f}-{AMOUNT_MAX:.2f} "
                "range this shop is set for")
    return None

def parse_date(text):
    """A date in one of the configured formats, or None. None means "cannot tell",
    which is never reported as a problem."""
    if not text:
        return None
    s = re.sub(r"[.,]", " ", str(text).strip())
    s = re.sub(r"\s+", " ", s)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def parse_time(text):
    if not text:
        return None
    s = re.sub(r"\s+", " ", str(text).strip().upper().replace(".", ""))
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None

def check_timestamp(date_str, time_str, now=None):
    """Future-dated and stale receipts. A time with no date is left alone: 20:05
    could be ten minutes ago or last night, and guessing would produce signals a
    seller stops reading."""
    day = parse_date(date_str)
    if day is None:
        return None
    wall = (now or shop_now()).replace(tzinfo=None)
    if day > wall.date():
        return f"Receipt is dated {date_str}, after today on this clock"
    moment = parse_time(time_str)
    if moment is None:
        days = (wall.date() - day).days
        if days * 24 > RECEIPT_MAX_AGE_HOURS:
            return f"Receipt is dated {date_str}, {days} days before this clock"
        return None
    stamp = datetime.combine(day, moment)
    if stamp > wall + FUTURE_TOLERANCE:
        return f"Receipt shows {date_str} {time_str}, later than this clock"
    age_hours = (wall - stamp).total_seconds() / 3600
    if age_hours > RECEIPT_MAX_AGE_HOURS:
        return (f"Receipt shows {date_str} {time_str}, about {age_hours:.0f} hours old - "
                f"this shop treats {RECEIPT_MAX_AGE_HOURS:g} hours as current")
    return None

def _near_label(digits_per_line, label_lines, digits, labels, window):
    """True when a line holding these digits has one of the labels beside it,
    False when it holds the digits with no label, None when the digits are on no
    line at all (nothing to say about a value that is not there)."""
    hits = [i for i, line in enumerate(digits_per_line) if digits in line]
    if not hits:
        return None
    for i in hits:
        around = " ".join(label_lines[max(0, i - window): i + window + 1])
        if any(lbl in around for lbl in labels):
            return True
    return False

def layout_reasons(text, fields):
    """Does each value sit beside the label a receipt template prints next to it?
    A number lifted from an unlabelled line is usually a misread rather than a
    forgery, so this only ever adds a reason. Needs the OCR text; the fields
    alone cannot say where a number came from."""
    if not text:
        return []
    # Only rows with something on them count as a neighbour. Tesseract separates
    # the rows of a screen with blank lines, and a blank inside the window pushed
    # the label out of reach - which made this repo's own sample receipts read as
    # if nothing labelled their amount or reference.
    rows = [line for line in text.splitlines() if line.strip()]
    label_lines = [line.lower() for line in rows]
    digits_per_line = [re.sub(r"[^0-9]", "", line) for line in rows]
    f = fields or {}
    pairs = []
    if f.get("ref"):
        pairs.append((str(f["ref"]), str(f["ref"]), REF_LABELS, "Reference"))
    if f.get("amount") is not None:
        # located without separators, because "PHP 1,250.00" and "PHP 1250.00"
        # are the same amount to a seller reading the screen
        shown = f"{f['amount']:.2f}"
        pairs.append((re.sub(r"\D", "", shown), shown, AMOUNT_LABELS, "Amount"))
    out = []
    for digits, shown, labels, noun in pairs:
        if labels and _near_label(digits_per_line, label_lines, digits, labels,
                                  LAYOUT_LABEL_WINDOW) is False:
            out.append(f"{noun} {shown} was read from a line with no "
                       f"{noun.lower()} label beside it")
    return out

def signals(fields, text=None, now=None):
    """The reasons this receipt raises about itself, or [] when it raises none."""
    f = fields or {}
    reasons = [check_reference(f.get("ref"), text),
               check_amount(f.get("amount")),
               check_timestamp(f.get("date"), f.get("time"), now)]
    reasons += layout_reasons(text, f)
    return [r for r in reasons if r]
