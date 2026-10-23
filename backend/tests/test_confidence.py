"""How well the photo read, and the one thing the seller is told because of it.

Tesseract scores every word it returns. `parser.ocr_confidence` averages those
scores so the verdict response can say "retake this" when a photo of a screen
came out poorly. The rule these tests hold is the narrow one: the number and the
hint travel beside the verdict and change nothing about it. A blurred photo of a
genuine payment is still a genuine payment; the only honest advice is to take the
picture again."""
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, verify
from app.ledger import add_entry
from app.main import app
from app.parser import ocr_confidence

REF = "1002849130490"
CLEAN = f"Amount\nPHP 1,250.00\nReference No.\n{REF}\n2026-10-23 2:45 PM"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture
def png():
    ok, enc = cv2.imencode(".png", np.full((80, 200, 3), 255, np.uint8))
    return enc.tobytes()


def boxes(text, conf):
    """The shape pytesseract's image_to_data returns: one entry per word."""
    return {"text": text.split(), "conf": conf,
            "left": [0] * len(text.split()), "top": [0] * len(text.split()),
            "width": [10] * len(text.split()), "height": [10] * len(text.split())}


def stub_reader(monkeypatch, text=CLEAN, conf=None, flagged=False):
    conf = [88] * len(text.split()) if conf is None else conf
    monkeypatch.setattr(verify, "run_ocr", lambda img: (text, boxes(text, conf)))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, b: {"ela": 1.0, "sharpness": 1.0, "flagged": flagged})


def other_png(n):
    img = np.full((80, 200, 3), 255, np.uint8)
    img[:, :4 * (n + 1)] = 0
    return cv2.imencode(".png", img)[1].tobytes()


# ---- the number ------------------------------------------------------------

def test_confidence_is_the_mean_over_the_words_read():
    assert ocr_confidence(boxes("payment received today", [90, 70, 80])) == 80.0


def test_the_structural_rows_between_words_are_left_out():
    """The shape real image_to_data returns: samples/real.png gives 44 rows, 20 of
    them structure, no text, conf -1. Averaging all of them gives 51.1 against
    94.5 for the words alone, and 51 is below the floor - an unfiltered mean
    would tell every seller to retake a clean photo."""
    data = {"text": ["Amount", "", "PHP", "", "1,250.00", "", ""],
            "conf": [95, -1, 92, -1, 96, -1, -1]}
    assert ocr_confidence(data) == 94.3


def test_a_row_scored_below_zero_is_left_out_even_if_it_carries_text():
    assert ocr_confidence({"text": ["Amount", "***"], "conf": [90, -1]}) == 90.0


def test_blank_cells_do_not_count_either():
    assert ocr_confidence({"text": ["payment", ""], "conf": [90, 70]}) == 90.0



def test_nothing_readable_is_none_rather_than_zero():
    """A blank page and a page of garbage both score nothing. As 0 they would both
    shout "retake", which is advice about a photo the reader never saw."""
    assert ocr_confidence({"text": [], "conf": []}) is None
    assert ocr_confidence({"text": ["", "  "], "conf": [-1, -1]}) is None


def test_a_reader_that_reports_no_scores_says_nothing_about_quality():
    # the shape the other test files stub in: boxes without a conf column
    assert ocr_confidence({"text": ["Amount"], "left": [0], "top": [0],
                           "width": [1], "height": [1]}) is None


def test_junk_in_the_score_column_is_not_a_number():
    assert ocr_confidence({"text": ["a", "b"], "conf": ["high", "low"]}) is None


def test_the_mean_is_kept_to_one_decimal():
    assert ocr_confidence(boxes("one two three", [90, 91, 92])) == 91.0


# ---- the advice ------------------------------------------------------------

def test_a_good_photo_is_left_alone():
    assert verify.retake_hint(88.0) is None


def test_a_score_at_the_floor_is_not_low():
    assert verify.retake_hint(verify.OCR_CONFIDENCE_MIN) is None


def test_no_score_means_no_advice():
    assert verify.retake_hint(None) is None


def test_a_low_score_asks_for_a_retake_and_says_what_was_read():
    h = verify.retake_hint(41.0)
    assert h and "Retake for a clearer photo" in h and "41/100" in h
    assert "fake" not in h.lower() and "invalid" not in h.lower()


def test_the_floor_is_config_not_a_hardcoded_number(monkeypatch):
    monkeypatch.setattr(verify, "OCR_CONFIDENCE_MIN", 95.0)
    assert verify.retake_hint(88.0) is not None


# ---- the engine carries them without being changed by them -----------------

def test_a_verified_payment_can_ask_for_a_retake(png, monkeypatch):
    """Nothing about the payment is in doubt: the ledger matches. The photo is
    simply poor, and the seller is told so next to a verdict that stayed VERIFIED."""
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t", "source": "app"})
    stub_reader(monkeypatch, conf=[52] * 5)
    r = verify.verify_receipt(png, "601")
    assert r["status"] == "VERIFIED" and r["label"] == "Verified"
    assert r["confidence"] == 52.0
    assert "Retake" in r["hint"]


def test_a_clear_photo_carries_no_hint(png, monkeypatch):
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t", "source": "app"})
    stub_reader(monkeypatch)
    r = verify.verify_receipt(other_png(1), "602")
    assert r["status"] == "VERIFIED"
    assert r["confidence"] >= verify.OCR_CONFIDENCE_MIN
    assert "hint" not in r


def test_a_bad_photo_of_an_unmatched_receipt_does_not_become_fake(png, monkeypatch):
    stub_reader(monkeypatch, conf=[30] * 5)
    r = verify.verify_receipt(other_png(2), "603")
    assert r["status"] == "PENDING_MATCH" and r["label"] == "Can't confirm yet"
    assert "hint" in r


def test_the_score_never_replaces_a_forensic_flag(png, monkeypatch):
    """The image check and the reader's confidence are two different doubts about
    the same picture; neither is allowed to become the other. Since 2026-10-23
    neither of them becomes a verdict either: the photo advice and the flag both
    come back as words, and the status stays "Can't confirm yet"."""
    stub_reader(monkeypatch, conf=[30] * 5, flagged=True)
    r = verify.verify_receipt(other_png(3), "604")
    assert r["status"] == "PENDING_MATCH" and r["label"] == "Can't confirm yet"
    assert "Retake" in r["hint"] and r["confidence"] == 30.0
    assert "forensic" in r["warning"].lower() and r["forensics"]["flagged"] is True


def test_signals_and_the_hint_stay_two_separate_things(png, monkeypatch):
    # an amount outside the shop's range is a signal about the receipt; the low
    # score is advice about the photo. Both appear, neither becomes a status.
    stub_reader(monkeypatch, text=f"Amount\nPHP 60,000.00\nReference No.\n{REF}",
                conf=[35] * 4)
    r = verify.verify_receipt(other_png(4), "605")
    assert r["status"] == "PENDING_MATCH"
    assert any("outside the 1.00-50000.00 range" in s for s in r["signals"])
    assert "Retake" in r["hint"]


def test_an_unreadable_file_has_no_score_and_no_retake_advice(png):
    r = verify.verify_receipt(b"not an image at all", "606")
    assert r["status"] == "SUSPECTED_FAKE" and r["confidence"] is None
    assert "hint" not in r


def test_a_stubbed_reader_says_nothing_about_quality(png, monkeypatch):
    """The other test files stub OCR without a score column. Those verdicts must
    not grow an advice line out of a number that was never read."""
    monkeypatch.setattr(verify, "run_ocr",
                        lambda img: (CLEAN, {"text": [], "left": [], "top": [],
                                             "width": [], "height": []}))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, b: {"ela": 1.0, "sharpness": 1.0, "flagged": False})
    r = verify.verify_receipt(other_png(5), "607")
    assert r["confidence"] is None and "hint" not in r


def test_the_endpoint_answers_with_both_keys(png, monkeypatch):
    stub_reader(monkeypatch, conf=[40] * 5)
    with TestClient(app) as c:
        res = c.post("/verify", files={"file": ("r.png", png, "image/png")},
                     data={"order_id": "608"})
    body = res.json()
    assert res.status_code == 200
    assert body["confidence"] == 40.0 and "Retake" in body["hint"]
    assert body["status"] == "PENDING_MATCH"


def test_the_score_is_not_written_into_the_database(png, monkeypatch):
    """Receipt images are not stored, and neither is a number that only describes
    one attempt at reading one. The advice is for the moment the cashier is
    still holding the phone."""
    stub_reader(monkeypatch, conf=[40] * 5)
    verify.verify_receipt(other_png(6), "609")
    raw = db.DB_PATH.read_bytes()
    assert b"Retake for a clearer photo" not in raw
