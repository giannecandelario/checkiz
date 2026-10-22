"""Reconciliation queue, packing list and evidence record. OCR is stubbed."""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, qrstore, verify
from app.ingest import ingest_alert
from app.ledger import add_entry, parse_alert
from app.main import app
from app.report import evidence, packing_csv
from app.review import acknowledge, review_list

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

def stub_ocr(monkeypatch, text, flagged=False):
    monkeypatch.setattr(verify, "run_ocr", lambda img: (text, NO_BOXES))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, boxes: {"ela": 9.9 if flagged else 1.0, "sharpness": 1.0,
                                            "flagged": flagged})

def alert(text, source="sms"):
    return ingest_alert(parse_alert(text, source))

def reasons():
    return {r["order_id"]: r["reason"] for r in review_list()}

def test_flagged_image_without_a_ledger_match_is_queued(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}", flagged=True)
    verify.verify_receipt(png, "501")
    assert reasons() == {"501": "SUSPECTED_FAKE"}

def test_clean_receipt_with_no_payment_is_queued_as_pending(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "509")
    assert reasons() == {"509": "PENDING_MATCH"}

def test_duplicate_is_queued(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "502")
    verify.verify_receipt(png, "503")
    assert reasons() == {"503": "DUPLICATE"}          # the clean order is not on the list

def test_spoofable_large_payment_is_queued_for_app_check():
    qrstore.save_order("504", 9000.00, True)
    out = alert(f"You have received PHP 9,000.00 of GCash from JUAN D. Ref. No. {REF}.", "sms")
    assert out["settled"]["needs_app_check"]
    assert reasons() == {"504": "CONFIRM_IN_APP"}

def test_notification_sourced_payment_is_not_queued():
    qrstore.save_order("505", 9000.00, True)
    alert(f"You have received PHP 9,000.00 of GCash from JUAN D. Ref. No. {REF}.", "app")
    assert reasons() == {}

def test_late_sms_match_is_queued_for_app_check(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 9,000.00 Ref No. {REF}")
    verify.verify_receipt(png, "506")
    alert(f"You have received PHP 9,000.00 of GCash from JUAN D. Ref. No. {REF}.", "sms")
    assert reasons()["506"] == "CONFIRM_IN_APP"

def test_acknowledge_clears_a_newer_verdict_reopens(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "507")
    assert reasons()["507"] == "PENDING_MATCH"
    acknowledge("507")
    assert reasons() == {}
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 9,999.00 Ref No. {REF}")
    verify.verify_receipt(png, "507")
    assert reasons()["507"] == "SUSPECTED_FAKE"

def test_unpaid_expired_qr_is_queued():
    qrstore.save_order("508", 300.05, True)
    with db.get_conn() as conn:
        conn.execute("UPDATE qr_orders SET created_at = datetime('now', '-48 hours')")
    assert reasons() == {"508": "UNPAID_EXPIRED"}
    acknowledge("508")
    assert reasons() == {}

def test_packing_csv_flags_confirm_in_app_and_hides_open_orders():
    qrstore.save_order("601", 150.37, True)
    qrstore.save_order("602", 9000.00, True)
    qrstore.save_order("603", 20.00, True)
    alert(f"You have received PHP 150.37 of GCash from ANNA B. Ref. No. {REF}.", "app")
    alert(f"You have received PHP 9,000.00 of GCash from BOB C. Ref. No. 2003951240871.", "sms")
    rows = [l.split(",") for l in packing_csv().strip().splitlines()]
    assert rows[0] == ["order_id", "amount", "paid_at", "ref", "alert_source", "sender",
                       "confirm_in_app"]
    paid = {r[0]: r for r in rows[1:]}
    assert paid["601"][6] == "" and paid["602"][6] == "YES"
    assert "603" not in paid                                   # still OPEN

def test_packing_csv_neutralises_formula_in_sender():
    qrstore.save_order("604", 50.00, True)
    alert('You have received PHP 50.00 of GCash from =cmd|\' /C calc\'. Ref. No. 2003951240871.',
          "app")
    assert "'=" in packing_csv()

def test_evidence_timeline_keeps_alert_text_out():
    qrstore.save_order("701", 150.37, True)
    secret = f"You have received PHP 150.37 of GCash from JUAN D. Ref. No. {REF}. 09171234567"
    out = alert(secret, "app")
    assert out["settled"]["order_id"] == "701"
    ev = evidence("701")
    kinds = [e["kind"] for e in ev["timeline"]]
    assert kinds == ["payment_alert", "claim", "verdict"]      # arrival, lock, decision
    assert ev["issued"]["status"] == "PAID" and ev["latest"]["status"] == "VERIFIED"
    assert secret not in str(ev) and "raw" not in str(ev)

def test_api_exposes_review_packing_and_evidence(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "801")
    with TestClient(app) as c:
        assert c.get("/review").json()[0]["order_id"] == "801"
        assert c.post("/review/801").json()["reviewed"]
        assert c.get("/review").json() == []
        assert "order_id" in c.get("/orders/packing.csv").text
        assert c.get("/orders/801/evidence").json()["latest"]["status"] == "PENDING_MATCH"
