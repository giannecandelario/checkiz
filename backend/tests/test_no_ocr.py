"""What happens when the server itself cannot read: say so, and say it about the server.

Found by running the app in a browser on 2026-10-23. On a machine without
Tesseract, `POST /verify` answered **500 text/plain "Internal Server Error"**
from a pytesseract traceback, and the dashboard translated that into "Something
else is listening on that port". Both were wrong: the server was Checkiz and it
was reachable - it was just blind, and had been since it started.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pytesseract import TesseractNotFoundError

from app import db, parser, verify
from app.ledger import add_entry
from app.main import FRONTEND, app
from app.verify import list_history

REF = "1002849130490"
NO_BOXES = {"text": [], "left": [], "top": [], "width": [], "height": []}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()


@pytest.fixture(autouse=True)
def unprobed_engine():
    """The probe answers once for the life of the process, so a test that wants a
    different machine must be allowed to ask again."""
    parser._ocr_engine = parser._UNPROBED
    yield
    parser._ocr_engine = parser._UNPROBED


@pytest.fixture
def png():
    ok, enc = cv2.imencode(".png", np.full((80, 200, 3), 255, np.uint8))
    return enc.tobytes()


@pytest.fixture
def client():
    return TestClient(app)


def no_engine(monkeypatch):
    monkeypatch.setattr(parser.pytesseract, "get_tesseract_version",
                        lambda: (_ for _ in ()).throw(TesseractNotFoundError()))


def reader_gives_up(monkeypatch):
    """Exactly what run_ocr does here when the binary is missing: it raises before
    looking at the image."""
    def boom(img):
        raise TesseractNotFoundError()
    monkeypatch.setattr(verify, "run_ocr", boom)


# ---- the probe itself -------------------------------------------------------

def test_a_working_engine_is_reported_as_its_version(monkeypatch):
    monkeypatch.setattr(parser.pytesseract, "get_tesseract_version", lambda: "5.5.0")
    assert parser.ocr_engine() == "5.5.0"


def test_a_missing_engine_is_none_not_an_exception(monkeypatch):
    no_engine(monkeypatch)
    assert parser.ocr_engine() is None


def test_the_probe_costs_one_subprocess_not_one_per_upload(monkeypatch):
    calls = []

    def count_then_fail():
        calls.append(1)
        raise TesseractNotFoundError()

    monkeypatch.setattr(parser.pytesseract, "get_tesseract_version", count_then_fail)
    for _ in range(5):
        assert parser.ocr_engine() is None
    assert len(calls) == 1


def test_a_blind_server_is_still_a_healthy_server(client):
    """/health must stay 200. "cannot read receipts" and "cannot be reached" are
    different problems and a page has to be able to tell them apart."""
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "checkiz"
    assert "ocr" in body


def test_health_names_the_engine_it_can_run(monkeypatch, client):
    monkeypatch.setattr(parser.pytesseract, "get_tesseract_version", lambda: "5.5.0")
    assert client.get("/health").json()["ocr"] == "5.5.0"


def test_health_admits_it_has_no_engine(monkeypatch, client):
    no_engine(monkeypatch)
    assert client.get("/health").json()["ocr"] is None


# ---- the upload -------------------------------------------------------------

def upload(client, order_id, png):
    return client.post("/verify", files={"file": ("r.png", png, "image/png")},
                       data={"order_id": order_id})


def test_an_unreadable_upload_answers_503_about_the_server(client, monkeypatch, png):
    reader_gives_up(monkeypatch)
    res = upload(client, "77", png)
    assert res.status_code == 503, res.text
    assert res.headers["content-type"].startswith("application/json")
    detail = res.json()["detail"]
    assert "Tesseract" in detail
    assert "Nothing about this photo was checked" in detail


def test_a_blind_upload_is_not_reported_as_a_verdict(client, monkeypatch, png):
    """A 500 used to reach the seller as a crash, and a real verdict body would be
    worse: it would put an unread photo in the history as if it had been judged."""
    reader_gives_up(monkeypatch)
    res = upload(client, "78", png)
    assert "status" not in res.json() and "label" not in res.json()
    assert list_history(20) == []


def test_the_engine_still_runs_its_checks_when_a_reader_is_stubbed(client, monkeypatch, png):
    """The guard sits where the engine actually fails, not at the door.

    A blanket "no Tesseract on this machine, refuse every upload" check would be
    wrong here: this repo's verdict tests stub the reader and run on a machine
    that has no OCR installed, which is the only reason they run at all."""
    no_engine(monkeypatch)
    monkeypatch.setattr(verify, "run_ocr",
                        lambda img: (f"PHP 1,250.00 Ref No. {REF}", NO_BOXES))
    monkeypatch.setattr(verify, "forensic_report",
                        lambda img, boxes: {"ela": 1.0, "sharpness": 1.0, "flagged": False})
    add_entry({"ref": REF, "amount": 1250.0, "sender": None, "raw": "t"})
    res = upload(client, "79", png)
    assert res.status_code == 200
    assert res.json()["status"] == "VERIFIED"


def test_a_receipt_needs_the_order_it_settles(monkeypatch, client, png):
    """Blank before the engine is asked anything: without an order there is nothing
    to reconcile against, and the row it writes would be unfindable."""
    res = upload(client, "   ", png)
    assert res.status_code == 422
    assert "order" in res.json()["detail"].lower()
    assert list_history(20) == []


# ---- the pages the server hands back ---------------------------------------

def page(name):
    return (Path(FRONTEND) / name).read_text()


def test_the_dashboard_reads_the_engine_field_before_the_first_upload():
    assert "h.ocr" in page("index.html")


def test_the_dashboard_does_not_read_a_missing_field_as_a_missing_engine():
    """`{"ok": true}` from a Checkiz one branch behind has no `ocr` key at all.
    Treating that as "no Tesseract here" would accuse a working machine of a fault
    it never reported - the same mistake one layer up as calling Checkiz's own 500
    another program's fault."""
    assert '!("ocr" in h)' in page("index.html")


def test_the_helper_no_longer_blames_the_port_it_was_only_asked_about():
    """`checkizProblem` cannot know who answered from a status code; only the
    /health probe in `checkizWho` can. Accusing another program from the first
    response is what sent the seller looking for a port conflict that did not
    exist while their own server was missing a binary."""
    js = page("api.js")
    assert "Something else is listening" not in js
    assert "is not Checkiz" in js
    assert "no OCR engine" in js
