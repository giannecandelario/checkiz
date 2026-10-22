"""The reconciliation queue: the orders Checkiz could not decide on its own.

The post-stream workflow depends on this list being short and complete, so it
merges two sources the seller would otherwise have to cross-read by hand: the
verdict log (which covers any order ID a receipt mentioned) and the order board
(which knows about QRs that were issued but never paid)."""
from .config import ORDER_TTL_HOURS
from .db import get_conn
from .labels import label_for

# A latest verdict of these still needs a person. VERIFIED only appears when the
# payment was confirmed by a source a texter could spoof.
_UNRESOLVED = ("SUSPECTED_FAKE", "DUPLICATE", "PENDING_MATCH")
_TTL = f"-{int(ORDER_TTL_HOURS * 60)} minutes"

def review_list():
    with get_conn() as conn:
        verdicts = [dict(r) for r in conn.execute(
            f"""SELECT v.id, v.order_id, v.status, v.label, v.message, v.amount, v.ref,
                       v.created_at, v.needs_app_check
                FROM verifications v
                WHERE (v.status IN {_UNRESOLVED} OR v.needs_app_check = 1)
                  AND v.id = (SELECT MAX(id) FROM verifications WHERE order_id = v.order_id)
                  AND v.id > COALESCE((SELECT acked_id FROM review_ack a
                                       WHERE a.order_id = v.order_id), 0)
                ORDER BY v.id DESC""")]
        unpaid = [dict(r) for r in conn.execute(
            """SELECT o.order_id, o.amount, o.created_at
               FROM qr_orders o
               WHERE o.status = 'OPEN' AND o.created_at <= datetime('now', ?)
                 AND o.order_id NOT IN (SELECT order_id FROM review_ack)""", (_TTL,))]

    out = {}
    for v in verdicts:
        reason = v["status"] if v["status"] in _UNRESOLVED else "CONFIRM_IN_APP"
        # The seller already saw this wording when the receipt was checked. A
        # VERIFIED row is here only for the in-app confirmation, so it gets no label.
        label = (v["label"] or label_for(v["status"])) if reason in _UNRESOLVED else None
        out[str(v["order_id"])] = {"order_id": v["order_id"], "reason": reason, "label": label,
                                   "detail": v["message"], "amount": v["amount"],
                                   "ref": v["ref"], "seen_at": v["created_at"]}
    for o in unpaid:
        out.setdefault(str(o["order_id"]), {
            "order_id": o["order_id"], "reason": "UNPAID_EXPIRED", "amount": o["amount"],
            "ref": None, "seen_at": o["created_at"],
            "detail": f"QR issued for {o['amount']:.2f}, no matching payment within "
                      f"{ORDER_TTL_HOURS:g} hours"})
    return sorted(out.values(), key=lambda i: i["seen_at"] or "", reverse=True)

def acknowledge(order_id: str):
    """Mark the current state of this order as reviewed. A newer verdict for the
    same order reopens it, so acknowledging is never a way to hide a problem."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO review_ack (order_id, acked_id, acked_at)
               VALUES (?, (SELECT COALESCE(MAX(id), 0) FROM verifications WHERE order_id = ?),
                       datetime('now'))
               ON CONFLICT(order_id) DO UPDATE SET acked_id = excluded.acked_id,
                                                   acked_at = excluded.acked_at""",
            (order_id, order_id))
    return {"order_id": order_id, "reviewed": True}
