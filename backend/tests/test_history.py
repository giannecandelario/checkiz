"""Reading the seller's OWN wallet transaction list off a screenshot. OCR is stubbed.

The fallback for when nothing arrives at all. GCash has moved most confirmations into
the app's own inbox, and a phone without Termux forwards none of them, so the last
thing the seller can still do is screenshot the Transactions screen. The rows on that
screen are a table, not a sentence, which is why this does not reuse
`ledger.parse_alert`.

Everything here is asserted against synthetic screens - no real wallet screenshot has
been run through it. See docs/DEVICE_TEST.md.
"""
import cv2
import numpy as np
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from pytesseract import TesseractNotFoundError

from app import db, history, qrstore
from app.history import parse_history_rows, scan, screenshot, to_entry
from app.ledger import list_entries
from app.main import FRONTEND, app

REF = "1002849130490"
OTHER = "1002849130491"
NO_BOXES = {"text": [], "left": [], "top": [], "width": [], "height": []}

# The shape Tesseract actually gives back for a transactions list: the stamp, the
# direction word, the figure and the reference on separate lines.
SCREEN = "\n".join([
    "Transactions",
    "2026-10-22 10:14 AM",
    "Received PHP 1,250.00",
    f"Ref No. {REF}",
    "2026-10-22 11:02 AM",
    "Sent PHP 500.00",
    f"Ref No. {OTHER}",
])


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture
def png():
    ok, enc = cv2.imencode(".png", np.full((80, 200, 3), 255, np.uint8))
    return enc.tobytes()


@pytest.fixture
def client():
    return TestClient(app)


def stub_reader(monkeypatch, text):
    monkeypatch.setattr(history, "run_ocr", lambda img: (text, NO_BOXES))


def upload(client, png, name="s.png"):
    return client.post("/ledger/history-screenshot",
                       files={"file": (name, png, "image/png")})


# ---- the row parser ---------------------------------------------------------

def test_a_table_row_is_read_across_separate_lines():
    rows = parse_history_rows(SCREEN)
    assert len(rows) == 1, rows
    r = rows[0]
    assert r["amount"] == 1250.0 and r["ref"] == REF and r["has_ref"]
    assert r["source"] == "history"
    assert r["date"] == "2026-10-22" and r["time"] == "10:14 AM"


def test_money_out_is_never_imported_as_money_in():
    """The dangerous error is inventing income, so this row is the one worth pinning:
    it carries a wallet word, so only the direction guard can keep it out."""
    rows, skipped = scan(f"2026-10-22 11:02 AM\nSent via GCash PHP 500.00\nRef No. {OTHER}")
    assert rows == []
    assert [(s["reason"], s["amount"]) for s in skipped] == [("money out", 500.0)]


def test_a_payment_listed_next_to_an_outgoing_row_is_still_a_payment():
    """Direction is decided by the *closest* word, not by any word in the window.
    Refusing a row because its neighbour said "Sent" would drop real payments, and a
    list alternates in and out on adjacent lines."""
    rows = parse_history_rows(f"Sent via GCash PHP 500.00\nReceived PHP 1,250.00\nRef No. {REF}")
    assert [r["amount"] for r in rows] == [1250.0]


def test_equally_close_direction_words_refuse_the_row():
    """"Sent via GCash, payment from 0917..." is money leaving with an incidental
    "from". A tie goes to not importing, and the reason is reported instead of the
    row quietly vanishing."""
    rows, skipped = scan("PHP 500.00\nSent via GCash, payment from 0917 123 4567")
    assert rows == [] and skipped[0]["reason"] == "money out"


def test_an_unlabelled_figure_is_reported_not_guessed_at():
    """A number with no direction word and no wallet word beside it is a balance,
    a fee, or half of a split row. Importing it invents a payment."""
    assert parse_history_rows("Balance\nPHP 3,000.00") == []
    assert scan("Balance\nPHP 3,000.00")[1][0]["reason"] == "no direction word"


def test_a_balance_column_does_not_beat_the_amount():
    rows = parse_history_rows(f"Received PHP 1,250.00 Balance PHP 0.00\nRef No. {REF}")
    assert [r["amount"] for r in rows] == [1250.0]


def test_a_row_without_a_reference_still_becomes_one_entry():
    """Weaker replay detection, not a lost payment - the same trade `parse_alert`
    makes for an alert that omits one."""
    rows = parse_history_rows("You have received\nPHP 150.37")
    assert len(rows) == 1 and rows[0]["has_ref"] is False
    assert rows[0]["ref"].startswith("NOREF-")
    assert rows[0]["ref"] == parse_history_rows("You have received\nPHP 150.37")[0]["ref"]


def test_one_screenshot_does_not_list_the_same_row_twice():
    rows = parse_history_rows(f"Received PHP 150.37 Ref No. {REF}\nReceived PHP 150.37 Ref No. {REF}")
    assert len(rows) == 1


def test_no_sender_names_are_taken_off_the_screen():
    """A transactions list shows the other party to every payment the seller has
    ever made. Only this row's own text is kept, and no name is pulled out of it."""
    rows = parse_history_rows(f"Received from MARIA S. PHP 1,250.00\nRef No. {REF}")
    assert rows and rows[0]["sender"] is None


def test_the_entry_keeps_the_printed_time_apart_from_the_server_time():
    e = to_entry(parse_history_rows(SCREEN)[0])
    assert e["printed_at"] == "2026-10-22 10:14 AM"
    assert e["source"] == "history"


# ---- what reaches the ledger -----------------------------------------------

def test_the_stored_row_keeps_both_times(client, monkeypatch, png):
    stub_reader(monkeypatch, SCREEN)
    assert upload(client, png).status_code == 200
    row = list_entries()[0]
    assert row["source"] == "history"
    assert row["printed_at"] == "2026-10-22 10:14 AM"
    assert row["received_at"] is not None and row["received_at"] != row["printed_at"]


def test_the_same_screenshot_twice_adds_one_payment(client, monkeypatch, png):
    """Found by running this against the Docker server, not by a test: the first
    version counted `added` from the rows it read, so uploading the screen twice told
    the seller they had been paid twice. The ledger took one row; the answer must say so."""
    stub_reader(monkeypatch, SCREEN)
    assert upload(client, png).json()["added"] == 1
    again = upload(client, png).json()
    assert again["added"] == 0 and again["already_in_ledger"] == [REF]
    assert len(list_entries()) == 1


def test_a_payment_an_sms_already_reported_is_not_counted_again(client, monkeypatch, png):
    """The normal case at a counter: the alert arrived, and the seller screenshots the
    same payment anyway. Two income lines from one payment is how a shop ends up
    shipping twice."""
    from app.ledger import parse_alert
    from app.ingest import ingest_alert
    ingest_alert(parse_alert(f"You have received PHP 1,250.00 of GCash from JUAN D. "
                             f"Ref. No. {REF}.", "sms"))
    stub_reader(monkeypatch, SCREEN)
    body = upload(client, png).json()
    assert body["added"] == 0 and body["already_in_ledger"] == [REF]
    assert [r["source"] for r in list_entries()] == ["sms"]


# ---- the endpoint ----------------------------------------------------------

def test_the_screenshot_reports_what_it_added_and_what_it_refused(client, monkeypatch, png):
    stub_reader(monkeypatch, SCREEN)
    body = upload(client, png).json()
    assert body["added"] == 1 and body["source"] == "history"
    assert body["entries"][0]["ref"] == REF
    assert body["unmatched"] == [REF]
    assert [(s["reason"], s["amount"]) for s in body["skipped"]] == [("money out", 500.0)]


def test_a_history_payment_settles_a_coded_order_but_is_still_not_the_app(
        client, monkeypatch, png):
    """Trust tier, end to end: the amount matches an order so it settles, but the
    words came off a screenshot, so a large payment still says "confirm in the app"."""
    qrstore.save_order("H1", 9000.37, True)
    stub_reader(monkeypatch, f"2026-10-22 10:14 AM\nReceived PHP 9,000.37\nRef No. {REF}")
    body = upload(client, png).json()
    settled = body["entries"][0]["settled"]
    assert settled["order_id"] == "H1" and settled["needs_app_check"] is True
    assert qrstore.get_order("H1")["status"] == "PAID"


def test_a_screen_with_nothing_on_it_adds_nothing(client, monkeypatch, png):
    stub_reader(monkeypatch, "Transactions\nNo transactions yet")
    res = upload(client, png)
    assert res.status_code == 400
    assert list_entries() == []


def test_a_file_that_is_not_a_picture_is_refused_before_ocr(client, monkeypatch):
    calls = []
    monkeypatch.setattr(history, "run_ocr",
                        lambda img: calls.append(1) or ("", NO_BOXES))
    res = client.post("/ledger/history-screenshot",
                      files={"file": ("notes.txt", b"Received PHP 1.00", "text/plain")})
    assert res.status_code == 415 and calls == []


def test_bytes_that_do_not_decode_are_said_to_be_the_problem(client):
    res = client.post("/ledger/history-screenshot",
                      files={"file": ("s.png", b"definitely not a png", "image/png")})
    assert res.status_code == 415
    assert "decode" in res.json()["detail"]


def test_an_oversized_screen_is_refused(client, monkeypatch, png):
    monkeypatch.setenv("CHECKIZ_MAX_UPLOAD_MB", "0.000001")
    assert upload(client, png).status_code == 413


def test_no_engine_adds_nothing_and_says_which_machine_is_broken(client, monkeypatch, png):
    def boom(img):
        raise TesseractNotFoundError()
    monkeypatch.setattr(history, "run_ocr", boom)
    res = upload(client, png)
    assert res.status_code == 503, res.text
    assert "Tesseract" in res.json()["detail"]
    assert list_entries() == []


def test_the_screenshot_endpoint_is_key_protected_like_the_ledger(client, monkeypatch, png):
    """It writes payments into the ledger, so whoever can reach the server must not
    be able to invent income with an uploaded image."""
    monkeypatch.setenv("CHECKIZ_API_KEY", "secret")
    assert upload(client, png).status_code == 401
    stub_reader(monkeypatch, SCREEN)
    res = client.post("/ledger/history-screenshot",
                      files={"file": ("s.png", png, "image/png")},
                      headers={"X-API-Key": "secret"})
    assert res.status_code == 200


def test_the_two_kinds_of_nothing_stay_apart(client, png):
    """`screenshot` answers None for "those bytes are not a picture" and ([], []) for
    "a picture with no payment I could place". Merging them would tell a seller to go
    and take another screenshot when the file was fine."""
    assert screenshot(b"definitely not a png") is None
    assert client.post("/ledger/history-screenshot",
                       files={"file": ("s.png", b"", "image/png")}).status_code == 415


# ---- the page the seller actually has to use -------------------------------

def test_the_dashboard_can_upload_a_transactions_screen():
    """The fallback is only a fallback if a cashier with no terminal can reach it."""
    from pathlib import Path
    from app.main import FRONTEND
    html = (Path(FRONTEND) / "index.html").read_text()
    assert "/ledger/history-screenshot" in html
    assert 'id="histFile"' in html
    assert "lowest trust" in html


def test_a_screen_of_only_money_out_says_so_and_says_why(client, monkeypatch, png):
    """Not "no payments on your screen" - the screen had figures; the parser refused
    them, and the seller needs the reason to know which to act on."""
    stub_reader(monkeypatch, "Sent via GCash PHP 500.00\nRef No. " + OTHER)
    res = upload(client, png)
    assert res.status_code == 400
    assert "money out" in res.json()["detail"]
    assert list_entries() == []
