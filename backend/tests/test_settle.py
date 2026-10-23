"""Alert parsing, trust levels and order-bound settlement. OCR is stubbed."""
import cv2
import numpy as np
import pytest

from app import db, qrstore, verify
from app.ingest import ingest_alert
from app.ledger import parse_alert

REF = "1002849130490"
NO_BOXES = {"text": [], "left": [], "top": [], "width": [], "height": []}

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()

@pytest.fixture
def png():
    ok, enc = cv2.imencode(".png", np.full((80, 200, 3), 255, np.uint8))
    return enc.tobytes()

def stub_ocr(monkeypatch, text):
    monkeypatch.setattr(verify, "run_ocr", lambda img: (text, NO_BOXES))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, boxes: {"ela": 1.0, "sharpness": 1.0, "flagged": False})

def alert(text, source="sms"):
    return ingest_alert(parse_alert(text, source))

def test_parse_without_reference():
    e = parse_alert("You have received PHP 150.37 of GCash from JUAN D.", "app")
    assert e and e["amount"] == 150.37 and not e["has_ref"] and e["ref"].startswith("NOREF-")

def test_outgoing_and_noise_rejected():
    assert parse_alert("You have sent PHP 500.00 to MARIA S. Ref. No. 1002 849 130490.") is None
    assert parse_alert("Your OTP is 123456") is None

def test_auto_settle_without_screenshot():
    qrstore.save_order("A1", 150.37, True)
    out = alert("You have received PHP 150.37 of GCash from JUAN D.", "app")
    assert out["settled"]["order_id"] == "A1"
    assert qrstore.get_order("A1")["status"] == "PAID"

def test_one_payment_settles_one_order_only():
    qrstore.save_order("A1", 150.37, True)
    alert("You have received PHP 150.37 of GCash from JUAN D. Ref. No. 1002 849 130490.", "app")
    qrstore.save_order("A2", 150.37, True)  # same amount reissued after A1 was paid
    again = alert("You have received PHP 150.37 of GCash from JUAN D. Ref. No. 1002 849 130490.", "app")
    assert again["settled"] is None and qrstore.get_order("A2")["status"] == "OPEN"

def test_receipt_amount_must_match_issued_amount(monkeypatch, png):
    qrstore.save_order("B1", 150.37, True)
    stub_ocr(monkeypatch, f"PHP 150.99 Ref No. {REF}")
    r = verify.verify_receipt(png, "B1")
    assert r["status"] == "SUSPECTED_FAKE" and "issued" in r["message"]

def test_real_receipt_cannot_be_reused_on_another_order(monkeypatch, png):
    qrstore.save_order("C1", 150.37, True)
    qrstore.save_order("C2", 250.12, True)
    alert(f"You have received PHP 150.37 of GCash from JUAN D. Ref. No. {REF}.", "app")
    stub_ocr(monkeypatch, f"PHP 150.37 Ref No. {REF}")
    r = verify.verify_receipt(png, "C2")
    assert r["status"] in ("DUPLICATE", "SUSPECTED_FAKE")

def test_resending_receipt_for_settled_order_is_idempotent(monkeypatch, png):
    qrstore.save_order("D1", 150.37, True)
    alert(f"You have received PHP 150.37 of GCash from JUAN D. Ref. No. {REF}.", "app")
    stub_ocr(monkeypatch, f"PHP 150.37 Ref No. {REF}")
    assert verify.verify_receipt(png, "D1")["status"] == "VERIFIED"

def test_sms_only_large_payment_needs_app_check(monkeypatch, png):
    alert(f"You have received PHP 9,000.00 of GCash from JUAN D. Ref. No. {REF}.", "sms")
    stub_ocr(monkeypatch, f"PHP 9,000.00 Ref No. {REF}")
    r = verify.verify_receipt(png, "E1")
    assert r["status"] == "VERIFIED" and r["needs_app_check"]

def test_app_sourced_large_payment_needs_no_extra_check(monkeypatch, png):
    alert(f"You have received PHP 9,000.00 of GCash from JUAN D. Ref. No. {REF}.", "app")
    stub_ocr(monkeypatch, f"PHP 9,000.00 Ref No. {REF}")
    assert not verify.verify_receipt(png, "F1")["needs_app_check"]

def test_late_alert_settles_waiting_receipt_for_coded_order(monkeypatch, png):
    qrstore.save_order("G1", 150.37, True)
    stub_ocr(monkeypatch, f"PHP 150.37 Ref No. {REF}")
    assert verify.verify_receipt(png, "G1")["status"] == "PENDING_MATCH"
    out = alert(f"You have received PHP 150.37 of GCash from JUAN D. Ref. No. {REF}.", "app")
    assert out["resolved"]["status"] == "VERIFIED"
    assert qrstore.get_order("G1")["status"] == "PAID"
