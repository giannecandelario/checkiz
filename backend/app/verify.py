import time

from .db import get_conn
from .config import CONFIRM_ABOVE
from .ledger import find_entry, set_consumed
from .qrstore import find_coded_order_by_amount, get_order, mark_paid
from .parser import load_image, run_ocr, parse_fields, locate_boxes
from .forensics import forensic_report

def get_claim(ref: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM claims WHERE ref = ?", (ref,)).fetchone()

def add_claim(ref: str, order_id: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO claims (ref, order_id) VALUES (?, ?)", (ref, order_id))

def result(status, message, fields, forensics, order_id, warning=None, **extra):
    out = {"status": status, "message": message, "fields": fields,
           "forensics": forensics, "order_id": order_id, **extra}
    if warning:
        out["warning"] = warning
    return out

def app_check_warning(entry):
    """SMS sender IDs can be spoofed, so a large payment seen only by SMS (or typed
    in by hand) should be confirmed in the wallet app. Notifications read from the
    wallet app itself (source 'app') are not subject to this."""
    if entry["source"] != "app" and entry["amount"] >= CONFIRM_ABOVE:
        return (f"Large payment seen only by {entry['source'] or 'sms'}, which can be spoofed. "
                "Confirm it in the wallet app before shipping.")
    return None

def settle_order(order_id: str, ref: str):
    """A payment has been accepted for this order: lock the ledger row to it and,
    if the order was issued with a coded amount, mark it paid."""
    set_consumed(ref, order_id)
    if get_order(order_id):
        mark_paid(order_id, ref)

def _verify(image_bytes: bytes, order_id: str) -> dict:
    img = load_image(image_bytes)
    if img is None:
        return result("SUSPECTED_FAKE", "Unreadable image", {}, {}, order_id)

    text, data = run_ocr(img)
    fields = parse_fields(text)
    ref, amount = fields["ref"], fields["amount"]

    # 1. Structure
    if not ref:
        return result("SUSPECTED_FAKE", "Missing or invalid reference number",
                      fields, {}, order_id)

    # 2. Duplicate
    claim = get_claim(ref)
    if claim and str(claim["order_id"]) == str(order_id):  # same buyer re-sending: idempotent
        return result("VERIFIED", f"Order #{order_id} is already settled with Ref {ref}",
                      fields, {}, order_id)
    if claim:
        return result("DUPLICATE",
                      f"Ref {ref} was already claimed on Order #{claim['order_id']}",
                      fields, {}, order_id)

    # Order binding: an order issued with a coded amount can only be paid by that amount,
    # so a genuine receipt from a different order cannot be reused here.
    order = get_order(order_id)
    issued = order["amount"] if order and order["coded"] else None
    if issued is not None and amount is not None and abs(amount - issued) > 0.01:
        return result("SUSPECTED_FAKE",
                      f"Receipt shows {amount:.2f} but Order #{order_id} was issued for {issued:.2f}",
                      fields, {}, order_id)

    # Forensics
    boxes = locate_boxes(data, amount, ref)
    forensics = forensic_report(img, boxes)

    # 3. Ledger checks
    entry = find_entry(ref)
    if entry and entry["consumed_order"] and str(entry["consumed_order"]) != str(order_id):
        return result("DUPLICATE",
                      f"Payment {ref} already settled Order #{entry['consumed_order']}",
                      fields, {}, order_id)
    if entry and amount is not None and abs(entry["amount"] - amount) > 0.01:
        return result("SUSPECTED_FAKE",
                      f"Amount mismatch: receipt {amount:.2f}, ledger {entry['amount']:.2f}",
                      fields, forensics, order_id)

    # Policy: a ledger match (ref + amount) is the strongest signal, so it is
    # never overridden by the probabilistic image check. The flag is returned
    # as a warning instead (see docs/BLUEPRINT.md, section 7).
    warnings = []
    if forensics["flagged"]:
        warnings.append("Image forensics flagged the amount/reference fields; "
                        "ledger match takes priority. Review manually if unsure.")
    other = find_coded_order_by_amount(amount) if amount is not None else None
    if other and other["order_id"] != order_id and issued is None:
        warnings.append(f"This amount was issued in the QR for Order #{other['order_id']}.")

    # 4. Verified (ledger match)
    if entry:
        chk = app_check_warning(entry)
        if chk:
            warnings.append(chk)
        warning = " ".join(warnings) or None
        add_claim(ref, order_id)
        settle_order(order_id, ref)
        return result("VERIFIED",
                      f"Ref {ref} matched incoming payment of {entry['amount']:.2f}",
                      fields, forensics, order_id, warning,
                      trust=entry["source"], needs_app_check=bool(chk))
    warning = " ".join(warnings) or None

    # 5. Forensic flag with no ledger confirmation
    if forensics["flagged"]:
        return result("SUSPECTED_FAKE",
                      "Image shows signs of editing on the amount or reference fields",
                      fields, forensics, order_id)

    # 6. Pending: remember it so a late SMS can resolve it automatically
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO pending (ref, order_id, amount) VALUES (?, ?, ?)",
                     (ref, order_id, amount))
    return result("PENDING_MATCH",
                  "Receipt looks valid but no matching payment in the ledger yet",
                  fields, forensics, order_id)


def verify_receipt(image_bytes: bytes, order_id: str) -> dict:
    """Run the verdict engine and record the outcome for the dashboard/overlay.
    Receipt images are never stored, only the extracted fields and the verdict."""
    t0 = time.perf_counter()
    res = _verify(image_bytes, order_id)
    res["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    f = res.get("fields") or {}
    log_verdict(order_id, res["status"], res["message"], f.get("amount"), f.get("ref"),
                res["elapsed_ms"])
    return res

def log_verdict(order_id, status, message, amount, ref, elapsed_ms=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO verifications (order_id, status, message, amount, ref, elapsed_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, status, message, amount, ref, elapsed_ms),
        )

def get_stats():
    """Counts per verdict plus timing, for the dashboard and the demo's success metrics."""
    with get_conn() as conn:
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, COUNT(*) AS n FROM verifications GROUP BY status")}
        t = conn.execute("SELECT AVG(elapsed_ms) AS avg, MAX(elapsed_ms) AS max "
                         "FROM verifications WHERE elapsed_ms IS NOT NULL").fetchone()
    return {"total": sum(counts.values()), "by_status": counts,
            "avg_elapsed_ms": round(t["avg"]) if t["avg"] is not None else None,
            "max_elapsed_ms": t["max"]}

def list_pending():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM pending ORDER BY created_at DESC")]

def resolve_pending(ref: str):
    """Called when a new SMS lands in the ledger. If a receipt for this ref was
    waiting as PENDING_MATCH, settle it now. Returns the new verdict or None."""
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM pending WHERE ref = ?", (ref,)).fetchone()
        if not p:
            return None
        conn.execute("DELETE FROM pending WHERE ref = ?", (ref,))
    entry = find_entry(ref)
    if p["amount"] is not None and abs(entry["amount"] - p["amount"]) > 0.01:
        status = "SUSPECTED_FAKE"
        msg = f"Amount mismatch: receipt {p['amount']:.2f}, ledger {entry['amount']:.2f}"
    elif get_claim(ref):
        status, msg = "DUPLICATE", f"Ref {ref} was already claimed"
    else:
        add_claim(ref, p["order_id"])
        settle_order(p["order_id"], ref)
        status, msg = "VERIFIED", f"Ref {ref} matched incoming payment of {entry['amount']:.2f} (late SMS)"
    log_verdict(p["order_id"], status, msg, p["amount"], ref)
    return {"order_id": p["order_id"], "status": status, "message": msg}

def list_history(limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM verifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
