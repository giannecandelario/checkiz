"""Verdict-engine tests. OCR is stubbed so no Tesseract or real receipt is needed."""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, verify
from app.ledger import add_entry
from app.main import app

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
                        lambda img, boxes: {"ela": 9.9 if flagged else 1.0, "sharpness": 1.0, "flagged": flagged})

def test_verified_then_duplicate(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": "JUAN D.", "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    assert verify.verify_receipt(png, "101")["status"] == "VERIFIED"
    dup = verify.verify_receipt(png, "102")
    assert dup["status"] == "DUPLICATE" and "#101" in dup["message"]

def test_amount_mismatch(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 9,250.00 Ref No. {REF}")
    assert verify.verify_receipt(png, "103")["status"] == "SUSPECTED_FAKE"

def test_pending_when_not_in_ledger(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    assert verify.verify_receipt(png, "104")["status"] == "PENDING_MATCH"

def test_missing_reference(monkeypatch, png):
    stub_ocr(monkeypatch, "PHP 500.00 no reference here")
    assert verify.verify_receipt(png, "105")["status"] == "SUSPECTED_FAKE"

def test_ledger_match_wins_over_forensic_flag(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "106")
    assert r["status"] == "VERIFIED" and r["warning"]

def test_the_image_score_alone_does_not_call_a_receipt_fake(monkeypatch, png):
    """Rewritten 2026-10-23 (was: test_forensic_flag_without_ledger_is_suspected).

    The old expectation let an uncalibrated score be the only evidence against a
    receipt. The measurement in docs/CALIBRATION.md is 5.78 genuine vs 5.82
    edited on the only pair in this repo, and a photographed copy of a genuine
    receipt scored *lower* than the unsaved page (ELA 2.55 vs 5.78) - so this
    number cannot tell a phone photo from a forgery, and a seller's real
    week-old receipt was called fake by it. The flag is still reported, and the
    receipt still waits for an alert."""
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "107")
    assert r["status"] == "PENDING_MATCH" and r["label"] == "Can't confirm yet"
    assert r["forensics"]["flagged"] is True
    assert "forensic" in r["warning"].lower()


def test_a_flagged_receipt_is_still_resolved_by_a_late_alert(monkeypatch, png):
    """The flagged path used to return before the pending insert, so a genuine
    receipt the score disliked was never settled when its alert arrived - the
    seller had to re-upload it by hand."""
    from app.verify import resolve_pending
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    verify.verify_receipt(png, "107b")
    assert [p["ref"] for p in verify.list_pending()] == [REF]
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    assert resolve_pending(REF)["status"] == "VERIFIED"


def test_the_warning_is_kept_with_the_verdict(monkeypatch, png):
    """The review board is where a seller works through a stream hours later. If
    the flag only lived in the HTTP response, moving it out of the verdict would
    have made it invisible exactly where it is needed."""
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    verify.verify_receipt(png, "107c")
    row = verify.list_history(1)[0]
    assert "forensic" in row["warning"].lower()
    assert row["status"] == "PENDING_MATCH"


def test_a_warning_never_claims_a_ledger_match_that_did_not_happen(monkeypatch, png):
    """The flagged-pending path has no entry to match against, so telling the
    seller "ledger match takes priority" there would invent the strongest
    evidence the receipt could have."""
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "107d")
    assert r["status"] == "PENDING_MATCH"
    assert "ledger match" not in r["warning"]


def test_a_ledger_match_still_outranks_the_image_flag(monkeypatch, png):
    """Keeping the old policy honest: when the alert really did arrive, the
    warning says the match outranked the flag."""
    add_entry({"ref": REF, "amount": 500.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "107e")
    assert r["status"] == "VERIFIED"
    assert "ledger match takes priority" in r["warning"]

def test_history_records_verdicts(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "108")
    assert verify.list_history(1)[0]["order_id"] == "108"

def test_api_key_protects_ledger(monkeypatch):
    monkeypatch.setenv("CHECKIZ_API_KEY", "secret")
    with TestClient(app) as c:
        assert c.get("/ledger").status_code == 401
        assert c.get("/ledger", headers={"X-API-Key": "secret"}).status_code == 200
        assert c.get("/health").status_code == 200

def test_late_sms_resolves_pending_order(monkeypatch, png):
    from app.verify import resolve_pending
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    assert verify.verify_receipt(png, "201")["status"] == "PENDING_MATCH"
    assert len(verify.list_pending()) == 1
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    out = resolve_pending(REF)
    assert out["status"] == "VERIFIED" and out["order_id"] == "201"
    assert verify.list_pending() == []
    assert verify.verify_receipt(png, "202")["status"] == "DUPLICATE"

def test_late_sms_with_wrong_amount_is_flagged(monkeypatch, png):
    from app.verify import resolve_pending
    stub_ocr(monkeypatch, f"PHP 9,999.00 Ref No. {REF}")
    verify.verify_receipt(png, "203")
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    assert resolve_pending(REF)["status"] == "SUSPECTED_FAKE"

def test_sms_endpoint_returns_resolution(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "204")
    sms = f"You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. {REF[:4]} {REF[4:7]} {REF[7:]}."
    with TestClient(app) as c:
        body = c.post("/ledger/sms", json={"text": sms}).json()
    assert body["resolved"]["status"] == "VERIFIED"

def test_upload_limits_and_stats(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    with TestClient(app) as c:
        files = lambda b, t="image/png": {"file": ("r.png", b, t)}
        ok = c.post("/verify", files=files(png), data={"order_id": "301"}).json()
        assert ok["status"] == "PENDING_MATCH" and ok["elapsed_ms"] >= 0
        assert c.post("/verify", files=files(b"x", "text/plain"), data={"order_id": "302"}).status_code == 415
        monkeypatch.setenv("CHECKIZ_MAX_UPLOAD_MB", "0.0001")
        assert c.post("/verify", files=files(png), data={"order_id": "303"}).status_code == 413
        s = c.get("/stats").json()
        assert s["total"] == 1 and s["by_status"]["PENDING_MATCH"] == 1

def test_an_empty_upload_is_an_unreadable_receipt_not_a_crash(monkeypatch):
    """0 bytes used to reach OpenCV, which raises on an empty buffer rather than
    returning None like it does for any other unreadable body, and the seller got a
    500 with nothing to act on."""
    stub_ocr(monkeypatch, "")
    with TestClient(app) as c:
        r = c.post("/verify", files={"file": ("r.png", b"", "image/png")},
                   data={"order_id": "304"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUSPECTED_FAKE" and "readable" in r.json()["message"].lower()
