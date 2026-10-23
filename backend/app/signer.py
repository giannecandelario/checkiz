"""
Deterministic QR signing — replaces AI/forensic probabilism.

Every order QR payload gets an HMAC-SHA256 signature appended as a
reference label (EMV tag 62/05).  Verification is a constant-time
HMAC comparison — pass or fail, no scoring.

Key derivation
--------------
The signing secret is read from env CHECKIZ_QR_SECRET.  If absent the
app starts but every verify call will return UNSIGNED (warn-only on
existing unsigned QRs, so the old flow keeps working during roll-out).

Signature format (tag 62/05 value)
------------------------------------
  SIG1.<base64url-no-pad of HMAC(secret, canonical_message)>

canonical_message = "<order_id>|<amount_2dp>"
e.g.  "ORD001|150.00"
"""

import hashlib
import hmac
import os
import base64

QR_SECRET = os.getenv("CHECKIZ_QR_SECRET", "")

_SIG_PREFIX = "SIG1."


def _canonical(order_id: str, amount: float) -> bytes:
    return f"{order_id}|{amount:.2f}".encode()


def sign(order_id: str, amount: float) -> str:
    """Return the reference-label value to embed in the generated QR."""
    if not QR_SECRET:
        return order_id  # no secret → fall back to plain order_id (unsigned)
    mac = hmac.new(QR_SECRET.encode(), _canonical(order_id, amount), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(mac).rstrip(b"=").decode()
    return f"{_SIG_PREFIX}{token}"


def verify_sig(order_id: str, amount: float, label: str) -> dict:
    """
    Returns:
        { "signed": bool, "valid": bool, "reason": str }

    - signed=False  → QR was issued before signing was enabled (legacy)
    - signed=True, valid=True  → HMAC matches, QR is authentic
    - signed=True, valid=False → HMAC mismatch, QR was tampered
    """
    if not label or not label.startswith(_SIG_PREFIX):
        return {"signed": False, "valid": False,
                "reason": "QR has no cryptographic signature (pre-signing or unsigned)"}
    if not QR_SECRET:
        return {"signed": True, "valid": False,
                "reason": "Server has no QR secret configured — cannot verify signature"}
    expected = sign(order_id, amount)
    ok = hmac.compare_digest(label, expected)
    return {
        "signed": True,
        "valid": ok,
        "reason": "Signature valid" if ok else "Signature mismatch — QR may have been tampered with",
    }
