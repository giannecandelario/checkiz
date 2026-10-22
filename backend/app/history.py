"""Reads a screenshot of the seller's OWN wallet Transactions screen into the ledger.

The fallback for when alerts do not arrive at all - GCash moved most confirmations
into the app inbox, and a phone without Termux forwards nothing. The seller opens
the wallet's own transaction list, screenshots it, and uploads that.

It is deliberately a different job from `ledger.parse_alert`. An alert is one
payment described in one sentence; a transactions screen is a *list*, where the
amount, the reference and the time sit on separate lines and the rows alternate
money in and money out. So this works row by row over the OCR text, and anything it
cannot place is reported to the caller rather than guessed at.

Trust is the lowest of the three sources: `history`. The words were read off an
image by OCR, the reference can be attached to the wrong amount when the list is
crooked, and nothing about it is signed. `verify.app_check_warning` already treats
every source that is not `app` as spoofable, so a large payment seen only here is
still sent to the seller as "confirm in the app".

Direction is decided by which word sits *closest* to the amount, not by whether
either word appears near it. A list that reads "Sent via GCash, payment from 0917..."
is money leaving, and importing it would make the seller ship goods nobody paid for;
a payment whose neighbour happens to be an outgoing row is still money in. Missing a
payment is recoverable - the seller can paste the alert or look in the app - so when
the two words are equally close, the row is skipped and reported.
"""
import hashlib
import re

from .parser import DATE_RE, REF_RE, TIME_RE, load_image, run_ocr

# The amount token on a transactions row is the same one a receipt carries, but the
# currency word often appears on its own line ("PHP" above a column of numbers), so
# the row search allows the symbol and the number to be apart.
AMOUNT_ROW = re.compile(r"(?:PHP|₱|PhP)?\s*([\d,]+\.\d{2})", re.IGNORECASE)
INCOMING = re.compile(r"\b(received|credit(?:ed)?|money in|you got|incoming|payment from)\b", re.IGNORECASE)
OUTGOING = re.compile(r"\b(sent|paid|pay(?:ment)? sent|cash ?out|transfer(?:red)?|withdraw(?:al)?"
                      r"|buy|reload|load|giveaway|send money|to)\b", re.IGNORECASE)
# A wallet prints a row label beside the money: "Received", "Sent", "Gcash", a phone
# number. None of them prove a direction on their own, so they only break a tie.
WALLET_ROW = re.compile(r"\b(gcash|maya|coins|paymaya)\b", re.IGNORECASE)


def _amounts(line: str):
    """Every two-decimal money figure on a line, so a balance column that reads
    0.00 can be outranked by the amount that was actually received."""
    out = []
    for m in AMOUNT_ROW.finditer(line):
        digits = m.group(1).replace(",", "")
        try:
            out.append(float(digits))
        except ValueError:
            pass
    return out


def _reference(line: str):
    m = REF_RE.search(line)
    if m:
        return re.sub(r"\s", "", m.group(1))
    return None


def _clean(text: str):
    return [ln.strip() for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]


def _nearest(pattern, lines, lo, hi, i):
    """Lines between the closest word `pattern` recognises in this window and the
    amount line itself, or None when the window holds no such word. 0 means the word
    is on the amount's own line, which is the strongest evidence there is."""
    best = None
    for j in range(lo, hi):
        if pattern.search(lines[j]):
            d = abs(j - i)
            if best is None or d < best:
                best = d
    return best


def scan(text: str, window: int = 1):
    """(rows, skipped) for this OCR text.

    A row is the line carrying the amount plus `window` lines either side, because
    Tesseract returns a transactions table as separate lines: the figure on one, the
    reference on the next. `window` is how far a reference may be from its amount and
    still be believed to belong to it.

    `skipped` is every money figure this parser refused, with the reason. It exists
    because a silent refusal looks identical to "the screen held no payments", and the
    seller needs to know which of the two happened.

    A row with money in but no reference still becomes an entry, with a synthetic key
    and `has_ref: False` - the same trade `parse_alert` makes for an alert that omits
    one. The ledger holds the payment; replay detection is simply weaker for it.
    """
    lines = _clean(text)
    rows, skipped, taken = [], [], set()
    for i, line in enumerate(lines):
        if i in taken:
            continue
        amounts = _amounts(line)
        if not amounts:
            continue
        lo, hi = max(0, i - window), min(len(lines), i + window + 1)
        ctx = " ".join(lines[lo:hi])
        amount = max(amounts)
        ref = _reference(line) or next((r for r in (_reference(l) for l in lines[lo:hi]) if r), None)
        key = ref or "NOREF-" + hashlib.sha1(" ".join(lines[lo:hi]).encode()).hexdigest()[:12]
        in_d, out_d = _nearest(INCOMING, lines, lo, hi, i), _nearest(OUTGOING, lines, lo, hi, i)

        def refuse(reason):
            skipped.append({"ref": key, "amount": amount, "reason": reason,
                            "raw": " | ".join(lines[lo:hi])})

        if out_d is not None and (in_d is None or out_d <= in_d):
            refuse("money out")
            continue
        if in_d is None and not WALLET_ROW.search(ctx):
            # Nothing on this row says money came in: a balance, a fee, or half a
            # row the reader cut in the wrong place. Importing it invents a payment.
            refuse("no direction word")
            continue
        if any(r["ref"] == key for r in rows):
            continue
        stamp = " ".join(lines[lo:hi])
        d, t = DATE_RE.search(stamp), TIME_RE.search(stamp)
        rows.append({
            "ref": key,
            "has_ref": ref is not None,
            "amount": amount,
            "date": d.group(1) if d else None,
            "time": t.group(1).strip() if t else None,
            "source": "history",
            # The row as read, kept for the same reason alerts keep their text: it is
            # what a dispute is settled against. Sender names are not extracted here -
            # a transactions screen shows the other party to every payment the seller
            # has ever made, and only this row is stored.
            "raw": " | ".join(lines[lo:hi]),
            "sender": None,
        })
        taken.update(range(lo, hi))
    return rows, skipped


def parse_history_rows(text: str, window: int = 1) -> list:
    """The accepted rows only - for callers that have nothing to report."""
    return scan(text, window)[0]


def to_entry(row: dict) -> dict:
    """The shape `ingest_alert` and `ledger.add_entry` already accept.

    `printed_at` is carried separately from `received_at`: the first is the time the
    wallet printed, the second is when Checkiz saw it. On a screenshot those can be
    days apart, and collapsing them would make an old payment look like it arrived
    just now.
    """
    return {
        "ref": row["ref"],
        "amount": row["amount"],
        "sender": row.get("sender"),
        "raw": row["raw"],
        "source": "history",
        "has_ref": row["has_ref"],
        "printed_at": " ".join(x for x in (row.get("date"), row.get("time")) if x) or None,
    }


def screenshot(data: bytes):
    """(rows, skipped) read off a transactions screenshot, or None when the bytes are
    not a picture at all.

    None and ([], []) are different answers worth keeping apart: "this upload is not
    an image" is something the seller can fix immediately, "the image held no payment
    I could place" says the screenshot was the wrong screen or read too badly.
    Collapsing them would tell a seller to go and take a screenshot when the file was
    fine.

    Raises TesseractNotFoundError with the engine missing - that is a fact about the
    server, so the caller answers 503 and writes nothing.
    """
    img = load_image(data)
    if img is None:
        return None
    text, _ = run_ocr(img)
    return scan(text)
