"""
Perceptual image fingerprinting — deterministic duplicate detection.

Replaces the probabilistic ELA/Laplacian forensics for receipt image
re-submission detection.

Strategy
--------
1.  Compute a pHash (perceptual hash) of the uploaded image.
2.  Store the hash on first verification of a ref number.
3.  On subsequent uploads for the same ref, compare hashes.
    - Same hash  → exact or near-identical image → DUPLICATE
    - Different hash → different image for same ref → SUSPECTED_FAKE
      (a real payment has one canonical receipt screenshot)

pHash distance threshold: ≤ 8 bit differences out of 64 is "same image".
This tolerates JPEG re-compression / minor crops while catching edits.

No AI involved.  No scoring.  Binary decision.
"""

import hashlib
import struct
import cv2
import numpy as np

from .db import get_conn

HASH_BITS = 64          # 8×8 pHash
SAME_THRESHOLD = 8      # Hamming distance ≤ 8 → duplicate


# ── pHash ──────────────────────────────────────────────────────────────────

def _phash(img) -> int:
    """64-bit perceptual hash of a BGR image."""
    small = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
    gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    dct   = cv2.dct(gray)
    top   = dct[:8, :8].flatten()
    med   = float(np.median(top))
    bits  = (top > med).astype(np.uint8)
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return h


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _phash_to_hex(h: int) -> str:
    return format(h, "016x")


def _hex_to_phash(s: str) -> int:
    return int(s, 16)


# ── SHA-256 of raw bytes (exact duplicate guard) ────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── DB helpers ───────────────────────────────────────────────────────────────

def _get_fingerprint(ref: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT phash, sha256 FROM receipt_fingerprints WHERE ref = ?", (ref,)
        ).fetchone()


def _store_fingerprint(ref: str, phash_hex: str, sha256_hex: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO receipt_fingerprints (ref, phash, sha256) VALUES (?, ?, ?)",
            (ref, phash_hex, sha256_hex),
        )


# ── Public API ───────────────────────────────────────────────────────────────

def check_and_store(image_bytes: bytes, img, ref: str) -> dict:
    """
    Call ONCE per verify attempt, after the ref is known.

    Returns:
        {
          "status":  "new" | "exact_duplicate" | "similar_duplicate" | "different_image",
          "message": str
        }

    - "new"              → first time we see this ref, fingerprint stored
    - "exact_duplicate"  → SHA-256 matches: byte-for-byte same file
    - "similar_duplicate"→ pHash within threshold: same screenshot re-cropped/compressed
    - "different_image"  → same ref, completely different image → suspicious
    """
    sha = _sha256(image_bytes)
    ph  = _phash(img)
    ph_hex = _phash_to_hex(ph)

    existing = _get_fingerprint(ref)

    if existing is None:
        _store_fingerprint(ref, ph_hex, sha)
        return {"status": "new", "message": "First submission — fingerprint stored"}

    # Exact byte match
    if existing["sha256"] == sha:
        return {"status": "exact_duplicate",
                "message": "Identical image file already submitted for this reference"}

    # Perceptual match
    dist = _hamming(ph, _hex_to_phash(existing["phash"]))
    if dist <= SAME_THRESHOLD:
        return {"status": "similar_duplicate",
                "message": f"Near-identical image (pHash distance {dist}) already submitted"}

    # Completely different image
    return {"status": "different_image",
            "message": f"Different image submitted for the same reference (pHash distance {dist})"}
