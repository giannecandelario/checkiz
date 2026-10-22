"""Image reuse: exact file identity.

A perceptual hash (dHash) was measured for this first and rejected: receipts
share a template and differ only in digits, so two *different* payments hash
closer together than a re-saved copy of one receipt does to its original. The
measurements and what they mean are recorded in docs/STATUS.md; nothing here
changes a verdict on similarity.

What is kept is the one comparison with no false positives: the same image file,
byte for byte, turning up again for a different order. It works even when OCR
cannot read the reference, which was the point of the feature. Only the SHA-256
of the uploaded bytes is stored - the image is not, and cannot be recovered from
the hash. A file re-encoded on the way (a messenger copy) does not match, so the
reference number stays the primary reuse signal.
"""
import hashlib

from .db import get_conn


def image_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_exact_repeat(sha: str, order_id: str):
    """An earlier verdict for a DIFFERENT order that was made from this exact file."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT order_id, status FROM verifications "
            "WHERE sha256 = ? AND order_id <> ? ORDER BY id DESC LIMIT 1",
            (sha, str(order_id))).fetchone()
    return dict(row) if row else None
