"""Everything that happens when a payment alert reaches the ledger.

1. Store it (first copy wins, so replays are harmless).
2. If a receipt with the same reference was waiting, settle that.
3. Otherwise, if exactly one open centavo-coded order was issued for this amount,
   settle that order straight from the alert. No screenshot needed."""
from .db import get_conn
from .labels import label_for
from .ledger import add_entry, find_entry, set_consumed
from .qrstore import find_open_coded_order, mark_paid
from .verify import add_claim, app_check_warning, get_claim, log_verdict, resolve_pending

def auto_settle(entry: dict):
    row = find_entry(entry["ref"])
    if not row or row["consumed_order"]:
        return None
    order = find_open_coded_order(row["amount"])
    if not order:
        return None
    oid = order["order_id"]
    if entry.get("has_ref") and not get_claim(entry["ref"]):
        add_claim(entry["ref"], oid)
    set_consumed(entry["ref"], oid)
    mark_paid(oid, entry["ref"])
    with get_conn() as conn:  # a receipt may already be waiting on this order
        conn.execute("DELETE FROM pending WHERE order_id = ?", (oid,))
    chk = app_check_warning(row)
    msg = f"Auto-settled: payment of {row['amount']:.2f} matches the amount issued for Order #{oid}"
    if chk:
        msg += f". {chk}"
    log_verdict(oid, "VERIFIED", msg, row["amount"], entry["ref"] if entry.get("has_ref") else None,
                needs_app_check=bool(chk))
    return {"order_id": oid, "status": "VERIFIED", "label": label_for("VERIFIED"),
            "message": msg, "needs_app_check": bool(chk)}

def ingest_alert(entry: dict) -> dict:
    """Store the alert and settle whatever it matches.

    `stored` is whether the ledger gained a row. The first copy of a reference wins
    (`INSERT OR IGNORE`), so re-sending an alert - or screenshotting a transaction that
    an SMS already reported - keeps the original row with its original source. Without
    this, an endpoint that counts answers would count a payment as newly recorded when
    nothing was recorded, and the seller's income total would be a fiction."""
    stored = add_entry(entry)
    resolved = resolve_pending(entry["ref"]) if entry.get("has_ref") else None
    settled = None if resolved else auto_settle(entry)
    return {**{k: entry[k] for k in ("ref", "amount", "sender", "source", "has_ref")},
            "stored": stored, "resolved": resolved, "settled": settled}
