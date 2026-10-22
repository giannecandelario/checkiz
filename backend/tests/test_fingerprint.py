"""Image reuse detection: the same file, byte for byte, on another order.

The brief asked for a perceptual hash (dHash). It was measured and rejected - the
numbers are in app/fingerprint.py and docs/STATUS.md - because on receipts, which
share a template, a different payment hashes closer to another payment than a
re-saved copy does to its own original. These tests therefore pin down what the
shipped check does and what it deliberately does not do."""
import sqlite3

import cv2
import numpy as np
import pytest

from app import db, verify
from app.fingerprint import image_sha256
from app.ledger import add_entry

REF = "1002849130490"
NO_BOXES = {"text": [], "left": [], "top": [], "width": [], "height": []}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


def receipt_file(n=1):
    img = np.full((120, 300, 3), 255, np.uint8)
    img[10:40, 10:10 + 20 * n] = 0
    ok, enc = cv2.imencode(".png", img)
    assert ok
    return enc.tobytes()


def stub_ocr(monkeypatch, text=f"PHP 1,250.00 Ref No. {REF}"):
    monkeypatch.setattr(verify, "run_ocr", lambda img: (text, NO_BOXES))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, boxes: {"ela": 1.0, "sharpness": 1.0, "flagged": False})


def test_same_file_on_another_order_is_reused(monkeypatch):
    stub_ocr(monkeypatch)
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    f = receipt_file()
    first = verify.verify_receipt(f, "501")
    second = verify.verify_receipt(f, "502")
    assert first["status"] == "VERIFIED"
    assert second["status"] == "DUPLICATE" and second["label"] == "Reused"
    assert "#501" in second["message"] and "same image file" in second["message"]


def test_same_file_is_still_reused_when_ocr_reads_nothing(monkeypatch):
    """The point of the check: a re-sent screenshot, unreadable reference."""
    stub_ocr(monkeypatch, "no usable text at all here")
    f = receipt_file(2)
    first = verify.verify_receipt(f, "503")
    second = verify.verify_receipt(f, "504")
    assert first["label"] == "Can't confirm yet"       # missing reference
    assert second["label"] == "Reused" and second["status"] == "DUPLICATE"


def test_uploading_the_same_file_to_the_same_order_is_not_a_repeat(monkeypatch, tmp_path):
    stub_ocr(monkeypatch)
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    f = receipt_file(3)
    verify.verify_receipt(f, "505")
    again = verify.verify_receipt(f, "505")
    assert again["status"] == "VERIFIED" and "already settled" in again["message"]


def test_a_re_encoded_copy_of_the_same_picture_is_not_caught(monkeypatch):
    """Known limit, pinned: a messenger app re-compresses the screenshot and the
    bytes change, so the file check cannot fire. The reference number is what
    catches that repeat - which is why OCR readability still matters."""
    stub_ocr(monkeypatch, "no usable text at all here")
    original = cv2.imdecode(np.frombuffer(receipt_file(4), np.uint8), cv2.IMREAD_COLOR)
    first = verify.verify_receipt(receipt_file(4), "506")
    ok, recompressed = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, 60])
    second = verify.verify_receipt(recompressed.tobytes(), "507")
    assert first["status"] == "SUSPECTED_FAKE"
    assert second["status"] == "SUSPECTED_FAKE" and "same image file" not in second["message"]


def test_an_unrelated_image_is_not_a_repeat(monkeypatch):
    stub_ocr(monkeypatch, "PHP 1,250.00 Ref No. 1002849130491")
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    verify.verify_receipt(receipt_file(5), "508")
    r = verify.verify_receipt(receipt_file(6), "509")
    assert r["status"] == "PENDING_MATCH"


def test_only_a_hash_is_stored_never_the_image(monkeypatch):
    stub_ocr(monkeypatch)
    f = receipt_file(7)
    res = verify.verify_receipt(f, "510")
    assert len(res["sha256"]) == 64 and res["sha256"] == image_sha256(f)
    with db.get_conn() as conn:
        row = conn.execute("SELECT sha256 FROM verifications WHERE order_id = '510'").fetchone()
    assert row["sha256"] == image_sha256(f)
    raw = sqlite3.connect(str(db.DB_PATH)).execute(
        "SELECT COUNT(*) FROM verifications WHERE sha256 IS NOT NULL").fetchone()[0]
    assert raw == 1
    # the file's own bytes appear nowhere in the database
    with open(db.DB_PATH, "rb") as fh:
        assert f[8:40] not in fh.read()


def test_hash_is_stable_and_content_dependent():
    a, b = receipt_file(1), receipt_file(2)
    assert image_sha256(a) == image_sha256(a)
    assert image_sha256(a) != image_sha256(b)
