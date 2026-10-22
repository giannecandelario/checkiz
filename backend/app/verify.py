import json
import time

from . import consistency
from .db import get_conn, json_field
from .config import CONFIRM_ABOVE
from .fingerprint import find_exact_repeat, image_sha256
from .labels import FORENSIC, MISMATCH, label_for
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

def result(status, message, fields, forensics, order_id, warning=None, reason=None,
           signals=(), **extra):
    out = {"status": status, "label": label_for(status, reason), "message": message,
           "fields": fields, "forensics": forensics, "order_id": order_id,
           "signals": list(signals), **extra}
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

def _verify(image_bytes: bytes, order_id: str, sha: str) -> dict:
    img = load_image(image_bytes)
    if img is None:
        return result("SUSPECTED_FAKE", "Unreadable image", {}, {}, order_id)

    text, data = run_ocr(img)
    fields = parse_fields(text)
    ref, amount = fields["ref"], fields["amount"]
    # Everything below carries the same alert-free signals: what this receipt says
    # about itself. They are reasons to look, never a status of their own.
    checks = consistency.signals(fields, text)

    def verdict(*args, **kwargs):
        return result(*args, signals=checks, **kwargs)

    # 1. The very same file was already checked for another order. This runs
    # before the reference gate on purpose: a re-sent screenshot is a repeat
    # even when OCR cannot read a single field of it.
    hit = find_exact_repeat(sha, order_id)
    if hit:
        return verdict("DUPLICATE",
                       f"This is the same image file already checked for Order #{hit['order_id']}",
                       fields, {}, order_id)

    # 2. Structure
    if not ref:
        return verdict("SUSPECTED_FAKE", "Missing or invalid reference number",
                       fields, {}, order_id)

    # 3. Duplicate
    claim = get_claim(ref)
    if claim and str(claim["order_id"]) == str(order_id):  # same buyer re-sending: idempotent
        return verdict("VERIFIED", f"Order #{order_id} is already settled with Ref {ref}",
                       fields, {}, order_id)
    if claim:
        return verdict("DUPLICATE",
                       f"Ref {ref} was already claimed on Order #{claim['order_id']}",
                       fields, {}, order_id)

    # Order binding: an order issued with a coded amount can only be paid by that amount,
    # so a genuine receipt from a different order cannot be reused here.
    order = get_order(order_id)
    issued = order["amount"] if order and order["coded"] else None
    if issued is not None and amount is not None and abs(amount - issued) > 0.01:
        return verdict("SUSPECTED_FAKE",
                       f"Receipt shows {amount:.2f} but Order #{order_id} was issued for {issued:.2f}",
                       fields, {}, order_id, reason=MISMATCH)

    # Forensics
    boxes = locate_boxes(data, amount, ref)
    forensics = forensic_report(img, boxes)

    # 4. Ledger checks
    entry = find_entry(ref)
    if entry and entry["consumed_order"] and str(entry["consumed_order"]) != str(order_id):
        return verdict("DUPLICATE",
                       f"Payment {ref} already settled Order #{entry['consumed_order']}",
                       fields, {}, order_id)
    if entry and amount is not None and abs(entry["amount"] - amount) > 0.01:
        return verdict("SUSPECTED_FAKE",
                       f"Amount mismatch: receipt {amount:.2f}, ledger {entry['amount']:.2f}",
                       fields, forensics, order_id, reason=MISMATCH)

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

    # 5. Verified (ledger match)
    if entry:
        chk = app_check_warning(entry)
        if chk:
            warnings.append(chk)
        warning = " ".join(warnings) or None
        add_claim(ref, order_id)
        settle_order(order_id, ref)
        return verdict("VERIFIED",
                       f"Ref {ref} matched incoming payment of {entry['amount']:.2f}",
                       fields, forensics, order_id, warning,
                       trust=entry["source"], needs_app_check=bool(chk))
    warning = " ".join(warnings) or None

    # 6. Forensic flag with no ledger confirmation
    if forensics["flagged"]:
        return verdict("SUSPECTED_FAKE",
                       "Image shows signs of editing on the amount or reference fields",
                       fields, forensics, order_id, reason=FORENSIC)

    # 7. Pending: remember it so a late SMS can resolve it automatically
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO pending (ref, order_id, amount) VALUES (?, ?, ?)",
                     (ref, order_id, amount))
    return verdict("PENDING_MATCH",
                   "Receipt looks valid but no matching payment in the ledger yet",
                   fields, forensics, order_id)


def verify_receipt(image_bytes: bytes, order_id: str) -> dict:
    """Run the verdict engine and record the outcome for the dashboard/overlay.
    Receipt images are never stored, only the extracted fields and the verdict."""
    t0 = time.perf_counter()
    sha = image_sha256(image_bytes)
    res = _verify(image_bytes, order_id, sha)
    res["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    res["sha256"] = sha
    f = res.get("fields") or {}
    log_verdict(order_id, res["status"], res["message"], f.get("amount"), f.get("ref"),
                res["elapsed_ms"], res.get("needs_app_check"), res["label"], sha,
                res["signals"], {k: f.get(k) for k in ("date", "time") if f.get(k)})
    return res

def log_verdict(order_id, status, message, amount, ref, elapsed_ms=None, needs_app_check=False,
                label=None, sha256=None, signals=None, printed_at=None):
    """`signals` and `printed_at` are stored as they were read: a receipt whose
    own date said nothing, or that contradicted itself, has to look the same way
    when the seller reads the evidence record days later."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO verifications (order_id, status, message, amount, ref, elapsed_ms, "
            "needs_app_check, label, sha256, signals, printed_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, status, message, amount, ref, elapsed_ms, int(bool(needs_app_check)),
             label or label_for(status), sha256,
             json.dumps(signals) if signals else None,
             json.dumps(printed_at) if printed_at else None),
        )

def get_stats():
    """Counts per verdict plus timing, for the dashboard and the demo's success metrics."""
    with get_conn() as conn:
        rows = conn.execute("SELECT status, label, COUNT(*) AS n FROM verifications "
                            "GROUP BY status, label").fetchall()
        t = conn.execute("SELECT AVG(elapsed_ms) AS avg, MAX(elapsed_ms) AS max "
                         "FROM verifications WHERE elapsed_ms IS NOT NULL").fetchone()
    counts, labels = {}, {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + r["n"]
        word = r["label"] or label_for(r["status"])
        labels[word] = labels.get(word, 0) + r["n"]
    return {"total": sum(counts.values()), "by_status": counts, "by_label": labels,
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
    chk = None
    reason = None
    if p["amount"] is not None and abs(entry["amount"] - p["amount"]) > 0.01:
        status = "SUSPECTED_FAKE"
        reason = MISMATCH
        msg = f"Amount mismatch: receipt {p['amount']:.2f}, ledger {entry['amount']:.2f}"
    elif get_claim(ref):
        status, msg = "DUPLICATE", f"Ref {ref} was already claimed"
    else:
        add_claim(ref, p["order_id"])
        settle_order(p["order_id"], ref)
        status, msg = "VERIFIED", f"Ref {ref} matched incoming payment of {entry['amount']:.2f} (late SMS)"
        chk = app_check_warning(entry)
        if chk:
            msg += f". {chk}"
    app_check = bool(chk)
    label = label_for(status, reason)
    log_verdict(p["order_id"], status, msg, p["amount"], ref, needs_app_check=app_check, label=label)
    return {"order_id": p["order_id"], "status": status, "label": label, "message": msg,
            "needs_app_check": app_check}

def list_history(limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM verifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            row = dict(r)
            # rows written before the label existed are labelled from their status
            row["label"] = row.get("label") or label_for(row["status"])
            row["signals"] = json_field(row.get("signals"), [])
            row["printed_at"] = json_field(row.get("printed_at"), {})
            out.append(row)
        return out
