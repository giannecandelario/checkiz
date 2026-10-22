"""Verdict labels: the words a seller reads. Status codes must not change.

OCR is stubbed, so no Tesseract and no real receipt is needed."""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, qrstore, verify
from app.labels import label_for
from app.ledger import add_entry, parse_alert
from app.main import app
from app.ingest import ingest_alert

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


def test_label_mapping_is_the_five_seller_words():
    assert label_for("VERIFIED") == "Verified"
    assert label_for("DUPLICATE") == "Reused"
    assert label_for("PENDING_MATCH") == "Can't confirm yet"
    assert label_for("SUSPECTED_FAKE", "mismatch") == "Doesn't match"
    assert label_for("SUSPECTED_FAKE", "forensic") == "Likely edited"
    # unreadable image or no reference: nothing was contradicted, so it is unconfirmed
    assert label_for("SUSPECTED_FAKE") == "Can't confirm yet"
    assert label_for("SOMETHING_NEW") == "Can't confirm yet"


def test_verified_upload_is_labelled_verified(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    r = verify.verify_receipt(png, "401")
    assert r["status"] == "VERIFIED" and r["label"] == "Verified"


def test_reused_reference_is_labelled_reused(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "402")
    r = verify.verify_receipt(png, "403")
    assert r["status"] == "DUPLICATE" and r["label"] == "Reused"


def test_ledger_amount_mismatch_is_labelled_does_not_match(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 9,250.00 Ref No. {REF}")
    r = verify.verify_receipt(png, "404")
    assert r["status"] == "SUSPECTED_FAKE" and r["label"] == "Doesn't match"


def test_wrong_order_amount_is_labelled_does_not_match(monkeypatch, png):
    qrstore.save_order("405", 150.37, True)
    stub_ocr(monkeypatch, f"PHP 9,250.00 Ref No. {REF}")
    r = verify.verify_receipt(png, "405")
    assert r["status"] == "SUSPECTED_FAKE" and r["label"] == "Doesn't match"
    assert "150.37" in r["message"]


def test_forensic_flag_without_a_ledger_match_is_likely_edited(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "406")
    assert r["status"] == "SUSPECTED_FAKE" and r["label"] == "Likely edited"


def test_ledger_match_outranks_the_forensic_flag(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}", flagged=True)
    r = verify.verify_receipt(png, "407")
    assert r["status"] == "VERIFIED" and r["label"] == "Verified"


def test_unconfirmed_cases_are_labelled_cant_confirm_yet(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    assert verify.verify_receipt(png, "408")["label"] == "Can't confirm yet"
    stub_ocr(monkeypatch, "PHP 500.00 no reference here")
    assert verify.verify_receipt(png, "409")["label"] == "Can't confirm yet"
    assert verify.verify_receipt(b"not an image", "410")["label"] == "Can't confirm yet"


def test_history_rows_carry_the_label(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "411")
    assert verify.list_history(1)[0]["label"] == "Can't confirm yet"
    with TestClient(app) as c:
        assert c.get("/history").json()[0]["label"] == "Can't confirm yet"


def test_old_rows_without_a_label_are_labelled_from_their_status():
    """A database created before the label column keeps working after the migration."""
    with db.get_conn() as conn:
        conn.execute("ALTER TABLE verifications DROP COLUMN label")
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("INSERT INTO verifications (order_id, status, message) "
                     "VALUES ('412', 'SUSPECTED_FAKE', 'old row')")
    assert verify.list_history(1)[0]["label"] == "Can't confirm yet"


def test_late_alert_resolution_is_labelled(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "413")
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    out = verify.resolve_pending(REF)
    assert out["status"] == "VERIFIED" and out["label"] == "Verified"
    assert verify.list_history(1)[0]["label"] == "Verified"


def test_late_alert_with_the_wrong_amount_is_labelled_does_not_match(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 9,999.00 Ref No. {REF}")
    verify.verify_receipt(png, "414")
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    assert verify.resolve_pending(REF)["label"] == "Doesn't match"


def test_auto_settled_order_is_labelled_verified():
    qrstore.save_order("415", 150.37, True)
    out = ingest_alert(parse_alert("You have received PHP 150.37 of GCash from JUAN D.", "app"))
    assert out["settled"]["label"] == "Verified"
    assert verify.list_history(1)[0]["label"] == "Verified"


def test_paste_endpoint_returns_labels(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "416")
    sms = f"You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. {REF}"
    with TestClient(app) as c:
        body = c.post("/ledger/paste", json={"text": sms}).json()
    assert body["entries"][0]["resolved"]["label"] == "Verified"


def test_review_queue_shows_the_same_word(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 9,250.00 Ref No. {REF}")
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    verify.verify_receipt(png, "417")
    with TestClient(app) as c:
        item = c.get("/review").json()[0]
    assert item["reason"] == "SUSPECTED_FAKE" and item["label"] == "Doesn't match"


def test_needs_app_check_row_has_no_label_collision(monkeypatch, png):
    """A VERIFIED row parked in the queue for an in-app confirmation is not relabelled."""
    big = f"PHP 5,000.00 Ref No. {REF}"
    stub_ocr(monkeypatch, big)
    add_entry({"ref": REF, "amount": 5000.0, "sender": None, "raw": "t", "source": "sms"})
    verify.verify_receipt(png, "418")
    with TestClient(app) as c:
        item = c.get("/review").json()[0]
    assert item["reason"] == "CONFIRM_IN_APP" and item["label"] is None


def test_evidence_timeline_carries_the_label(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    verify.verify_receipt(png, "419")
    with TestClient(app) as c:
        ev = c.get("/orders/419/evidence").json()
    verdicts = [e for e in ev["timeline"] if e["kind"] == "verdict"]
    assert verdicts and verdicts[-1]["label"] == "Can't confirm yet"
    assert ev["latest"]["label"] == "Can't confirm yet"


def test_stats_count_by_label_as_well_as_by_status(monkeypatch, png):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    stub_ocr(monkeypatch, f"PHP 9,250.00 Ref No. {REF}")
    verify.verify_receipt(png, "420")
    other = "1002849130491"  # no ledger entry, so the flag has nothing to override it
    stub_ocr(monkeypatch, f"PHP 1,250.00 Ref No. {other}", flagged=True)
    verify.verify_receipt(png, "421")
    s = verify.get_stats()
    assert s["by_status"]["SUSPECTED_FAKE"] == 2
    assert s["by_label"] == {"Doesn't match": 1, "Likely edited": 1}


def test_status_codes_are_untouched_by_the_label_field(monkeypatch, png):
    stub_ocr(monkeypatch, f"PHP 500.00 Ref No. {REF}")
    r = verify.verify_receipt(png, "422")
    assert set(r) >= {"status", "label", "message", "fields", "forensics", "order_id", "elapsed_ms"}
