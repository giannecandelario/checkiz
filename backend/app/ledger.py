import hashlib
import re
from .config import REF_LENGTH
from .db import get_conn

AMOUNT = re.compile(r"(?:PHP|\u20b1|PhP)\s?([\d,]+\.\d{2})", re.I)
REF = re.compile(r"Ref(?:erence)?\.?\s*(?:No\.?|Number|#)?\s*:?\s*(\d[\d\s]{9,18}\d)", re.I)
SENDER = re.compile(r"from\s+(.+?)(?:\s+w/|\s+with|\.|\s+Ref|$)", re.I)
INCOMING = re.compile(r"\b(received|credited|money in|you got)\b", re.I)
OUTGOING = re.compile(r"\b(you(?:'ve| have)? (?:sent|paid)|payment sent|cash ?out|transferred to)\b", re.I)

def parse_alert(text: str, source: str = "sms"):
    """Parse an incoming-payment alert (SMS, app notification or pasted inbox text).

    The reference number is optional: some alerts omit it, and the in-app inbox
    format differs from SMS. Amount plus an incoming-money phrase is the minimum.
    Outgoing alerts are rejected so they never count as payments received."""
    if not text or OUTGOING.search(text) or not INCOMING.search(text):
        return None
    a = AMOUNT.search(text)
    if not a:
        return None
    ref = None
    r = REF.search(text)
    if r:
        digits = re.sub(r"\s", "", r.group(1))
        if len(digits) == REF_LENGTH:
            ref = digits
    if ref is None:  # stable synthetic key so re-sending the same alert is harmless
        ref = "NOREF-" + hashlib.sha1(text.strip().encode()).hexdigest()[:12]
    s = SENDER.search(text)
    return {
        "ref": ref,
        "has_ref": not ref.startswith("NOREF-"),
        "amount": float(a.group(1).replace(",", "")),
        "sender": s.group(1).strip() if s else None,
        "raw": text,
        "source": source,
    }

def parse_sms(text: str):  # kept for older callers and tests
    return parse_alert(text, "sms")

def add_entry(entry: dict):
    """True when this payment was new to the ledger, False when the copy already
    there was kept.

    The two have to stay countable apart: `INSERT OR IGNORE` deliberately keeps the
    first copy, so a replay stores nothing, and a number that counts it as added tells
    a seller they were paid twice."""
    with get_conn() as conn:
        # INSERT OR IGNORE keeps the first copy, so a replayed alert cannot reset
        # which order already consumed it.
        cur = conn.execute(
            "INSERT OR IGNORE INTO ledger (ref, amount, received_at, sender, raw, source, printed_at) "
            "VALUES (?, ?, datetime('now'), ?, ?, ?, ?)",
            (entry["ref"], entry["amount"], entry.get("sender"), entry.get("raw"),
             entry.get("source", "sms"), entry.get("printed_at")),
        )
        return cur.rowcount > 0

def find_entry(ref: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM ledger WHERE ref = ?", (ref,)).fetchone()

def set_consumed(ref: str, order_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE ledger SET consumed_order = ? WHERE ref = ?", (order_id, ref))

def list_entries():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ledger ORDER BY received_at DESC")]
