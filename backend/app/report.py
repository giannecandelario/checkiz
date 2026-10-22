"""Read-only seller reports: the packing list and the per-order evidence record.

Both are answers to questions asked after the stream has ended, when nobody is
willing to scroll through verdict history line by line."""
import csv
import io

from .config import CONFIRM_ABOVE
from .db import get_conn, json_field
from .labels import label_for

# Alert text can carry the buyer's phone number, and a dispute record only needs
# to prove a payment existed and where the alert came from, so `raw` is left out.
_PAYMENT_FIELDS = ("ref", "amount", "received_at", "sender", "source", "consumed_order")
_PAYMENT_COLUMNS = ", ".join(_PAYMENT_FIELDS)
_KIND_ORDER = {"payment_alert": 0, "claim": 1, "verdict": 2}

def _cell(value):
    """Neutralise spreadsheet formula injection: sender names arrive from SMS text."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

def packing_rows():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT o.order_id, o.amount, o.paid_at, o.paid_ref, l.source, l.sender
               FROM qr_orders o LEFT JOIN ledger l ON l.ref = o.paid_ref
               WHERE o.status = 'PAID' ORDER BY o.paid_at, o.order_id""")]

def packing_csv() -> str:
    """Paid orders only. Anything still waiting on an in-app confirmation is
    printed as such, so a packing list can never hide the exceptions."""
    buf = io.StringIO()
    write = csv.writer(buf)
    write.writerow(["order_id", "amount", "paid_at", "ref", "alert_source", "sender",
                    "confirm_in_app"])
    for r in packing_rows():
        source = r["source"] or "unknown"
        write.writerow([_cell(r["order_id"]), f"{r['amount']:.2f}", _cell(r["paid_at"]),
                        _cell(r["paid_ref"]), _cell(source), _cell(r["sender"]),
                        "YES" if source != "app" and r["amount"] >= CONFIRM_ABOVE else ""])
    return buf.getvalue()

def evidence(order_id: str) -> dict:
    """Everything Checkiz observed about one order, oldest first."""
    with get_conn() as conn:
        order = conn.execute("SELECT * FROM qr_orders WHERE order_id = ?", (order_id,)).fetchone()
        verdicts = [dict(r) for r in conn.execute(
            """SELECT id, status, label, message, amount, ref, needs_app_check, elapsed_ms,
                      sha256, signals, printed_at, created_at
               FROM verifications WHERE order_id = ? ORDER BY id""", (order_id,))]
        for v in verdicts:
            v["label"] = v["label"] or label_for(v["status"])
            v["signals"] = json_field(v.get("signals"), [])
            v["printed_at"] = json_field(v.get("printed_at"), {})
        claims = [dict(r) for r in conn.execute(
            "SELECT ref, order_id, claimed_at FROM claims WHERE order_id = ?", (order_id,))]
        ack = conn.execute("SELECT acked_at FROM review_ack WHERE order_id = ?", (order_id,)).fetchone()
        refs = {v["ref"] for v in verdicts if v["ref"]} | {c["ref"] for c in claims}
        if order and order["paid_ref"]:
            refs.add(order["paid_ref"])
        placeholders = ", ".join("?" * len(refs))
        payments = [dict(r) for r in conn.execute(
            f"SELECT {_PAYMENT_COLUMNS} FROM ledger WHERE ref IN ({placeholders})",
            tuple(refs))] if refs else []

    events = ([{"at": v["created_at"], "kind": "verdict", "status": v["status"],
                "label": v["label"], "detail": v["message"], "ref": v["ref"],
                "amount": v["amount"], "sha256": v["sha256"],
                "signals": v["signals"], "printed_at": v["printed_at"],
                "needs_app_check": bool(v["needs_app_check"])} for v in verdicts]
              + [{"at": p["received_at"], "kind": "payment_alert", "status": "RECEIVED",
                  "detail": f"{p['amount']:.2f} seen by {p['source'] or 'unknown'}"
                            + (f" from {p['sender']}" if p["sender"] else ""),
                  "ref": p["ref"], "amount": p["amount"],
                  "needs_app_check": p["source"] != "app" and p["amount"] >= CONFIRM_ABOVE}
                 for p in payments]
              + [{"at": c["claimed_at"], "kind": "claim", "status": "CLAIMED",
                  "detail": f"Receipt {c['ref']} claimed for this order", "ref": c["ref"],
                  "amount": None, "needs_app_check": False} for c in claims])
    return {
        "order_id": order_id,
        "issued": None if not order else {
            "amount": order["amount"], "coded": bool(order["coded"]), "status": order["status"],
            "paid_ref": order["paid_ref"], "created_at": order["created_at"],
            "paid_at": order["paid_at"]},
        "payments": payments,
        "latest": verdicts[-1] if verdicts else None,
        "reviewed_at": ack["acked_at"] if ack else None,
        # ties inside one second break in cause-then-effect order
        "timeline": sorted(events, key=lambda e: (e["at"] or "", _KIND_ORDER[e["kind"]])),
    }
