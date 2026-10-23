"""
Deterministic receipt & QR verification engine.

Pivoted AWAY from AI / probabilistic image scoring.

Decision hierarchy (all binary — no scoring):
──────────────────────────────────────────────
1. Image readable?              → No  → SUSPECTED_FAKE
2. Reference number parseable?  → No  → SUSPECTED_FAKE
3. Already claimed (exact ref + same order)?  → VERIFIED (idempotent)
4. Already claimed (ref used by another order)? → DUPLICATE
5. Image fingerprint check (pHash / SHA-256):
   - exact_duplicate or similar_duplicate   → DUPLICATE
   - different_image (same ref, diff image) → SUSPECTED_FAKE
6. Order coded-amount binding:
   amount on receipt ≠ coded amount?        → SUSPECTED_FAKE
7. Ledger match (ref + amount in our payment DB)?
   YES → VERIFIED
   NO  → PENDING_MATCH (receipt looks valid; wait for SMS/notification)
8. No ledger match & no prior fingerprint?  → PENDING_MATCH

QR path (verify_qr)
────────────────────
Uses HMAC-SHA256 signature embedded in the QR at generation time.
Pass/fail — no scoring.
"""

import time

from .db import get_conn
from .config import CONFIRM_ABOVE
from .ledger import find_entry, set_consumed
from .qrstore import find_coded_order_by_amount, get_order, mark_paid
from .parser import load_image, run_ocr, parse_fields
from .fingerprint import check_and_store
from .signer import verify_sig


# ── helpers ──────────────────────────────────────────────────────────────────

def get_claim(ref: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM claims WHERE ref = ?", (ref,)).fetchone()

def add_claim(ref: str, order_id: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO claims (ref, order_id) VALUES (?, ?)", (ref, order_id))

def result(status, message, fields, fingerprint, order_id, warning=None, **extra):
    out = {"status": status, "message": message, "fields": fields,
           "fingerprint": fingerprint, "order_id": order_id, **extra}
    if warning:
        out["warning"] = warning
    return out

def app_check_warning(entry):
    """SMS sender IDs can be spoofed; large payments via SMS need app confirmation."""
    if entry["source"] != "app" and entry["amount"] >= CONFIRM_ABOVE:
        return (f"Large payment seen only by {entry['source'] or 'sms'}, which can be spoofed. "
                "Confirm it in the wallet app before shipping.")
    return None

def settle_order(order_id: str, ref: str):
    set_consumed(ref, order_id)
    if get_order(order_id):
        mark_paid(order_id, ref)


# ── receipt verify ───────────────────────────────────────────────────────────

def _verify(image_bytes: bytes, order_id: str) -> dict:
    # 1. Load image
    img = load_image(image_bytes)
    if img is None:
        return result("SUSPECTED_FAKE", "Unreadable image", {}, {}, order_id)

    # 2. OCR + parse
    text, _ = run_ocr(img)
    fields = parse_fields(text)
    ref, amount = fields["ref"], fields["amount"]

    if not ref:
        return result("SUSPECTED_FAKE", "Missing or invalid reference number",
                      fields, {}, order_id)

    # 3. Already claimed by THIS order (idempotent)
    claim = get_claim(ref)
    if claim and str(claim["order_id"]) == str(order_id):
        return result("VERIFIED", f"Order #{order_id} is already settled with Ref {ref}",
                      fields, {}, order_id)

    # 4. Already claimed by a DIFFERENT order
    if claim:
        return result("DUPLICATE",
                      f"Ref {ref} was already claimed on Order #{claim['order_id']}",
                      fields, {}, order_id)

    # 5. Deterministic image fingerprint check
    fp = check_and_store(image_bytes, img, ref)
    if fp["status"] == "exact_duplicate":
        return result("DUPLICATE", fp["message"], fields, fp, order_id)
    if fp["status"] == "similar_duplicate":
        return result("DUPLICATE", fp["message"], fields, fp, order_id)
    if fp["status"] == "different_image":
        # Same reference but completely different image → tampered / recycled ref
        return result("SUSPECTED_FAKE", fp["message"], fields, fp, order_id)

    # 6. Order coded-amount binding
    order = get_order(order_id)
    issued = order["amount"] if order and order["coded"] else None
    if issued is not None and amount is not None and abs(amount - issued) > 0.01:
        return result("SUSPECTED_FAKE",
                      f"Receipt shows {amount:.2f} but Order #{order_id} was issued for {issued:.2f}",
                      fields, fp, order_id)

    # 7. Ledger match (the primary truth source)
    entry = find_entry(ref)
    if entry and entry["consumed_order"] and str(entry["consumed_order"]) != str(order_id):
        return result("DUPLICATE",
                      f"Payment {ref} already settled Order #{entry['consumed_order']}",
                      fields, fp, order_id)

    if entry and amount is not None and abs(entry["amount"] - amount) > 0.01:
        return result("SUSPECTED_FAKE",
                      f"Amount mismatch: receipt {amount:.2f}, ledger {entry['amount']:.2f}",
                      fields, fp, order_id)

    warnings = []
    other = find_coded_order_by_amount(amount) if amount is not None else None
    if other and other["order_id"] != order_id and issued is None:
        warnings.append(f"This amount was issued in the QR for Order #{other['order_id']}.")

    if entry:
        chk = app_check_warning(entry)
        if chk:
            warnings.append(chk)
        add_claim(ref, order_id)
        settle_order(order_id, ref)
        return result("VERIFIED",
                      f"Ref {ref} matched incoming payment of {entry['amount']:.2f}",
                      fields, fp, order_id, " ".join(warnings) or None,
                      trust=entry["source"], needs_app_check=bool(chk))

    # 8. No ledger entry yet — park it as pending
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO pending (ref, order_id, amount) VALUES (?, ?, ?)",
                     (ref, order_id, amount))
    return result("PENDING_MATCH",
                  "Receipt looks valid but no matching payment in the ledger yet",
                  fields, fp, order_id, " ".join(warnings) or None)


def verify_receipt(image_bytes: bytes, order_id: str) -> dict:
    """Public entry point: run the deterministic engine and log the verdict."""
    t0 = time.perf_counter()
    res = _verify(image_bytes, order_id)
    res["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    f = res.get("fields") or {}
    log_verdict(order_id, res["status"], res["message"],
                f.get("amount"), f.get("ref"), res["elapsed_ms"])
    return res


# ── QR verify ────────────────────────────────────────────────────────────────

def verify_qr(order_id: str, amount: float, label: str) -> dict:
    """
    Deterministic QR authenticity check via HMAC-SHA256.

    Parameters
    ----------
    order_id : from the QR's additional-data bill-number field
    amount   : from the QR's amount field (tag 54)
    label    : from the QR's reference-label field (tag 62/05)

    Returns
    -------
    { "status": "VERIFIED" | "SUSPECTED_FAKE" | "UNSIGNED",
      "message": str,
      "signed": bool,
      "valid": bool }
    """
    sig = verify_sig(order_id, amount, label)

    if not sig["signed"]:
        # Pre-signing QR or no secret configured — downgrade to UNSIGNED (warn only)
        return {"status": "UNSIGNED", "message": sig["reason"],
                "signed": False, "valid": False}

    if sig["valid"]:
        return {"status": "VERIFIED", "message": sig["reason"],
                "signed": True, "valid": True}

    return {"status": "SUSPECTED_FAKE", "message": sig["reason"],
            "signed": True, "valid": False}


# ── ledger / stats helpers (unchanged) ───────────────────────────────────────

def log_verdict(order_id, status, message, amount, ref, elapsed_ms=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO verifications (order_id, status, message, amount, ref, elapsed_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, status, message, amount, ref, elapsed_ms),
        )

def get_stats():
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
    """Called when a new ledger entry arrives. Settle any parked receipt."""
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
        status, msg = "VERIFIED", f"Ref {ref} matched payment of {entry['amount']:.2f} (late SMS)"
    log_verdict(p["order_id"], status, msg, p["amount"], ref)
    return {"order_id": p["order_id"], "status": status, "message": msg}

def list_history(limit: int = 20):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM verifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
