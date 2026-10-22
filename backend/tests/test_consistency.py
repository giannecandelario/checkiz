"""Alert-free consistency checks: the pure functions, and how the engine carries them.

The rule these tests exist to hold is the one written down in app/consistency.py:
a signal adds a reason to read, it never changes a verdict. So several tests below
assert that a status stayed exactly where it was while a reason appeared."""
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import consistency, db, verify
from app.consistency import (check_amount, check_reference, check_timestamp,
                             layout_reasons, signals)
from app.ledger import add_entry
from app.main import app
from app.parser import parse_fields

REF = "1002849130490"
NO_BOXES = {"text": [], "left": [], "top": [], "width": [], "height": []}
# a fixed clock, so no test can pass or fail depending on the day it runs
NOW = datetime(2026, 10, 23, 15, 0, tzinfo=timezone(timedelta(hours=8)))
CLEAN = f"Amount\nPHP 1,250.00\nReference No.\n{REF}\n2026-10-23 2:45 PM"


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


def other_png(n):
    """A distinct file each time, so the byte-identity reuse check answers about
    the receipt under test and not about the last one."""
    img = np.full((80, 200, 3), 255, np.uint8)
    img[:, :4 * (n + 1)] = 0
    return cv2.imencode(".png", img)[1].tobytes()


# ---- the reference ---------------------------------------------------------

def test_a_reference_of_the_expected_length_raises_nothing():
    assert check_reference(REF, CLEAN) is None


def test_reference_length_comes_from_config_not_from_a_hardcoded_number(monkeypatch):
    monkeypatch.setattr(consistency, "REF_LENGTH", 12)
    assert check_reference(REF) == ("Reference 1002849130490 has 13 digits, "
                                    "this shop expects 12")


def test_a_short_reference_is_named_with_the_digits_it_saw():
    # the parser only ever returns a 13-digit run, so a 12-digit number arrives
    # here as "no reference" - this is what makes that verdict explainable
    r = check_reference(None, f"Amount PHP 500.00\nRef No. 100284913049")
    assert r == ("No 13-digit reference found; the closest number read was "
                 "100284913049, 12 digits")


def test_a_phone_number_is_offered_as_the_closest_digits():
    r = check_reference(None, "Send to 09171234567, amount PHP 500.00")
    assert "09171234567" in r and "11 digits" in r


def test_no_digits_worth_calling_a_reference_raises_nothing():
    assert check_reference(None, "thank you for your order") is None


def test_a_repeated_digit_reference_is_a_signal():
    assert check_reference("0000000000000") == "Reference 0000000000000 is the same digit repeated"


def test_a_reference_that_is_not_digits_is_a_signal():
    assert "not a plain string of digits" in check_reference("12AB456789012")


# ---- the amount ------------------------------------------------------------

def test_an_amount_inside_the_configured_range_raises_nothing():
    assert check_amount(1250.0) is None


def test_amount_bounds_come_from_config(monkeypatch):
    monkeypatch.setattr(consistency, "AMOUNT_MAX", 1000.0)
    assert "outside the 1.00-1000.00 range" in check_amount(1250.0)


def test_amounts_outside_the_plausible_range_are_signals():
    assert "outside the 1.00-50000.00 range" in check_amount(0.5)
    assert "outside the 1.00-50000.00 range" in check_amount(1_000_000.0)


def test_an_amount_with_more_than_two_decimals_is_a_signal():
    assert "not pesos and centavos" in check_amount(100.005)


def test_junk_amounts_are_answered_without_raising():
    """These same functions validate a second reader's output one day, so a value
    that is not a number at all has to produce a reason, not an exception."""
    for bad in ("abc", float("nan"), float("inf"), {}, []):
        assert check_amount(bad)


def test_no_amount_read_is_not_reported_as_a_problem():
    """The verdict already says the receipt had nothing to match on."""
    assert check_amount(None) is None


# ---- the printed date and time --------------------------------------------

def test_a_fresh_receipt_raises_nothing():
    assert check_timestamp("2026-10-23", "2:45 PM", now=NOW) is None


def test_a_future_dated_receipt_is_a_signal():
    assert "after today on this clock" in check_timestamp("2026-10-25", "09:00", now=NOW)


def test_a_stale_receipt_is_a_signal_and_says_how_stale():
    r = check_timestamp("2026-10-01", "09:00", now=NOW)
    assert r and "hours old" in r and "48 hours" in r


def test_a_clock_a_few_minutes_ahead_is_not_worth_mentioning():
    assert check_timestamp("2026-10-23", "3:20 PM", now=NOW) is None


def test_a_time_with_no_date_is_left_alone():
    """20:05 could be ten minutes ago or last night. Guessing would produce
    signals a seller learns to ignore."""
    assert check_timestamp(None, "20:05", now=NOW) is None


def test_a_date_with_no_time_is_counted_in_whole_days():
    # two whole days is still inside a 48 hour window; four is not
    assert check_timestamp("2026-10-21", None, now=NOW) is None
    assert "before this clock" in check_timestamp("2026-10-19", None, now=NOW)


@pytest.mark.parametrize("text", ["2026-10-23", "10/23/2026", "23/10/2026",
                                  "23 Oct 2026", "October 23, 2026"])
def test_the_common_date_spellings_are_understood(text):
    assert check_timestamp(text, "2:45 PM", now=NOW) is None


def test_an_unrecognised_date_is_no_claim_at_all():
    assert check_timestamp("sometime last week", "2:45 PM", now=NOW) is None
    assert consistency.parse_date("90 from 0917") is None


def test_the_shop_clock_is_not_utc():
    """A receipt stamped 15:00 in Manila read by a UTC server looks 8 hours old,
    which would flag nearly every genuine payment."""
    assert consistency.shop_now().utcoffset() == timedelta(hours=8)


# ---- layout ----------------------------------------------------------------

def test_values_beside_their_labels_raise_nothing():
    assert layout_reasons(CLEAN, parse_fields(CLEAN)) == []


def test_a_reference_on_an_unlabelled_line_is_a_signal():
    text = f"Payment received\n{REF} this number means nothing here\nPHP 500.00 total"
    r = layout_reasons(text, {"ref": REF})
    assert r == [f"Reference {REF} was read from a line with no reference label beside it"]


def test_both_unlabelled_values_give_two_reasons():
    out = layout_reasons(f"PHP 1,250.00 {REF}", {"ref": REF, "amount": 1250.0})
    assert len(out) == 2
    assert "no reference label beside it" in out[0]
    assert "no amount label beside it" in out[1]


def test_the_label_list_is_config_and_can_be_emptied(monkeypatch):
    monkeypatch.setattr(consistency, "REF_LABELS", [])
    assert layout_reasons(f"PHP 1,250.00 {REF}", {"ref": REF}) == []


def test_a_label_one_line_away_still_counts():
    text = f"Total Amount\nPHP 1,250.00\nReference No.\n{REF}"
    assert layout_reasons(text, {"ref": REF, "amount": 1250.0}) == []


def test_a_value_that_is_not_in_the_text_says_nothing_about_layout():
    assert layout_reasons(f"Amount PHP 500.00 Ref No. {REF}", {"ref": "1111111111111"}) == []


def test_no_text_means_no_layout_claim():
    """The fields alone cannot say where a number came from, so nothing is said."""
    assert layout_reasons("", {"ref": REF, "amount": 1250.0}) == []


# ---- the aggregate ---------------------------------------------------------

def test_a_clean_receipt_raises_no_signals():
    assert signals(parse_fields(CLEAN), CLEAN, now=NOW) == []


def test_signals_arrive_in_a_stable_order():
    text = f"Ref 100284913049\nPHP 60,000.00\n2019-01-01 08:00"
    f = {"ref": None, "amount": 60000.0, "date": "2019-01-01", "time": "08:00"}
    out = signals(f, text, now=NOW)
    assert out[0].startswith("No 13-digit reference")
    assert "outside the 1.00-50000.00 range" in out[1]
    assert "hours old" in out[2]
    assert "no amount label beside it" in out[3]


def test_the_checks_tolerate_a_receipt_that_yielded_nothing():
    assert signals({}, "", now=NOW) == []
    assert signals(None, None, now=NOW) == []
    assert signals({"ref": REF, "amount": None, "date": None, "time": None},
                   f"Ref No. {REF}", now=NOW) == []


# ---- the engine carries them without being changed by them -----------------

def test_a_verified_payment_can_still_carry_a_signal(monkeypatch, png):
    """Nothing here contradicts the payment: the ledger shows the same amount, so
    the verdict stays VERIFIED and the seller simply gets a line to read."""
    add_entry({"ref": REF, "amount": 60000.0, "sender": None, "raw": "t", "source": "app"})
    stub_ocr(monkeypatch, f"Amount PHP 60,000.00\nReference No.\n{REF}")
    r = verify.verify_receipt(png, "501")
    assert r["status"] == "VERIFIED" and r["label"] == "Verified"
    assert r["signals"] == ["Amount 60000.00 is outside the 1.00-50000.00 range "
                            "this shop is set for"]


def test_a_clean_receipt_leaves_the_verdict_exactly_as_it_was(monkeypatch):
    # pinned clock: the receipt in CLEAN is stamped 2:45 PM, which against the
    # machine's real time would be future or past depending on when pytest runs
    monkeypatch.setattr(consistency, "shop_now", lambda: NOW)
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t", "source": "app"})
    stub_ocr(monkeypatch, CLEAN)
    r = verify.verify_receipt(other_png(1), "502")
    assert r["status"] == "VERIFIED" and r["signals"] == []


def test_a_missing_reference_explains_the_closest_number(monkeypatch):
    stub_ocr(monkeypatch, f"Amount PHP 500.00\nRef No. 100284913049")
    r = verify.verify_receipt(other_png(2), "503")
    assert r["status"] == "SUSPECTED_FAKE" and r["label"] == "Can't confirm yet"
    assert r["message"] == "Missing or invalid reference number"
    assert r["signals"][0].startswith("No 13-digit reference found")


def test_the_receipts_own_clock_is_checked_against_the_shops(monkeypatch, png):
    monkeypatch.setattr(consistency, "shop_now", lambda: NOW)
    stub_ocr(monkeypatch, f"Amount PHP 500.00\nReference No.\n{REF}\n2026-09-30 08:00")
    r = verify.verify_receipt(png, "504")
    assert r["status"] == "PENDING_MATCH"          # no ledger entry, same as before
    assert any("hours old" in s for s in r["signals"])


def test_a_stamp_from_later_today_does_not_change_the_verdict(monkeypatch, png):
    """The other direction: a clock ahead of the server's. The verdict engine has
    no rule about time at all, so this must stay PENDING_MATCH with one reason."""
    monkeypatch.setattr(consistency, "shop_now", lambda: NOW)
    stub_ocr(monkeypatch, f"Amount PHP 500.00\nReference No.\n{REF}\n2026-10-23 11:30 PM")
    r = verify.verify_receipt(png, "515")
    assert r["status"] == "PENDING_MATCH"
    assert r["signals"] == [f"Receipt shows 2026-10-23 11:30 PM, later than this clock"]


def test_the_printed_date_and_time_are_read_into_the_fields(monkeypatch, png):
    stub_ocr(monkeypatch, CLEAN)
    f = verify.verify_receipt(png, "505")["fields"]
    assert f["date"] == "2026-10-23" and f["time"] == "2:45 PM"


# ---- stored, and readable after the fact -----------------------------------

def test_signals_are_stored_with_the_verdict(monkeypatch):
    stub_ocr(monkeypatch, f"PHP 1,250.00 {REF}")
    verify.verify_receipt(other_png(3), "506")
    row = verify.list_history(1)[0]
    assert len(row["signals"]) == 2
    assert row["printed_at"] == {}


def test_the_receipts_own_stamp_is_stored_for_the_dispute_record(monkeypatch):
    stub_ocr(monkeypatch, CLEAN)
    verify.verify_receipt(other_png(4), "507")
    assert verify.list_history(1)[0]["printed_at"] == {"date": "2026-10-23", "time": "2:45 PM"}


def test_history_endpoint_returns_signals_as_a_list(monkeypatch):
    stub_ocr(monkeypatch, f"PHP 1,250.00 {REF}")
    verify.verify_receipt(other_png(5), "508")
    with TestClient(app) as c:
        row = c.get("/history").json()[0]
    assert isinstance(row["signals"], list) and len(row["signals"]) == 2


def test_the_evidence_timeline_keeps_the_reasons(monkeypatch):
    stub_ocr(monkeypatch, f"PHP 1,250.00 {REF}")
    verify.verify_receipt(other_png(6), "509")
    with TestClient(app) as c:
        ev = c.get("/orders/509/evidence").json()
    verdicts = [e for e in ev["timeline"] if e["kind"] == "verdict"]
    assert len(verdicts[-1]["signals"]) == 2


def test_the_review_queue_shows_what_to_look_at(monkeypatch):
    stub_ocr(monkeypatch, f"PHP 1,250.00 {REF}")
    verify.verify_receipt(other_png(7), "510")
    with TestClient(app) as c:
        item = c.get("/review").json()[0]
    assert item["reason"] == "PENDING_MATCH" and len(item["signals"]) == 2


def test_an_unreadable_image_carries_no_signals(png):
    r = verify.verify_receipt(b"not an image", "511")
    assert r["status"] == "SUSPECTED_FAKE" and r["signals"] == []


def test_rows_written_before_the_checks_existed_still_read(monkeypatch):
    """An old database has no signals column. After the migration the API has to
    answer with an empty list, not null and not a crash."""
    with db.get_conn() as conn:
        conn.execute("ALTER TABLE verifications DROP COLUMN signals")
        conn.execute("INSERT INTO verifications (order_id, status, message) "
                     "VALUES ('512', 'PENDING_MATCH', 'old row')")
    db.init_db()
    stub_ocr(monkeypatch, CLEAN)
    verify.verify_receipt(other_png(8), "513")
    row = [r for r in verify.list_history(5) if r["order_id"] == "512"][0]
    assert row["signals"] == [] and row["label"] == "Can't confirm yet"


def test_the_receipts_own_words_are_never_stored(monkeypatch):
    stub_ocr(monkeypatch, CLEAN)
    verify.verify_receipt(other_png(9), "514")
    assert b"Reference No." not in db.DB_PATH.read_bytes()
