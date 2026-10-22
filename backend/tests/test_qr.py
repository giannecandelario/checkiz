"""QR Ph tests use a synthetic payload (fake account IDs), not a real wallet QR."""
import base64

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, qrph, qrstore, verify
from app.main import app

def sample(name="MARIA S", account="09171234567"):
    merchant = qrph.tlv("00", "ph.ppmi.p2m") + qrph.tlv("01", "TESTBANK") + qrph.tlv("02", account)
    return qrph.build([("00", "01"), ("01", "11"), ("27", merchant), ("52", "0000"),
                       ("53", "608"), ("58", "PH"), ("59", name), ("60", "MANILA")])

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()

def test_crc_known_vector():
    assert qrph.crc16(b"123456789") == 0x29B1

def test_build_parse_roundtrip():
    p = sample()
    assert qrph.crc_ok(p) and qrph.analyze(p)["is_emv"]
    assert qrph.analyze(p)["point_of_initiation"] == "11"

def test_dynamic_build_keeps_account_and_adds_fields():
    p = sample()
    d = qrph.build_dynamic(p, 1250.37, "Order #104")
    info = qrph.analyze(d)
    assert qrph.crc_ok(d) and info["point_of_initiation"] == "12"
    assert info["amount"] == 1250.37 and info["reference_label"] == "Order104"
    assert qrph.account_signature(d) == qrph.account_signature(p)

def test_centavo_codes_are_unique_per_open_order():
    a = qrstore.next_free_amount(500); qrstore.save_order("A", a, True)
    b = qrstore.next_free_amount(500); qrstore.save_order("B", b, True)
    assert (a, b) == (500.01, 500.02)

def test_api_flow_register_generate_and_decode():
    mine = sample()
    with TestClient(app) as c:
        assert c.post("/qr/generate", json={"order_id": "1", "amount": 100}).status_code == 400
        assert c.post("/qr/register", json={"payload": mine}).json()["registered"]
        assert c.post("/qr/register", json={"payload": "hello"}).status_code == 400
        g = c.post("/qr/generate", json={"order_id": "104", "amount": 1250, "centavo_code": True}).json()
        assert g["amount"] == 1250.01
        png = base64.b64decode(g["png"].split(",")[1])
        r = c.post("/qr/decode", files={"file": ("qr.png", png, "image/png")}).json()
        assert r["payload"] == g["payload"]
        seller = c.get("/qr/seller").json()
        assert seller["registered"] and "account" not in str(seller["info"]).lower()
        blank = cv2.imencode(".png", np.full((200, 200, 3), 255, np.uint8))[1].tobytes()
        assert c.post("/qr/decode", files={"file": ("b.png", blank, "image/png")}).json()["payload"] is None

def test_receipt_amount_from_another_orders_qr_gets_warning(monkeypatch):
    from app.ledger import add_entry
    qrstore.save_order("A", 500.07, True)
    add_entry({"ref": "1002849130490", "amount": 500.07, "sender": None, "raw": "t"})
    nb = {"text": [], "left": [], "top": [], "width": [], "height": []}
    monkeypatch.setattr(verify, "run_ocr", lambda img: ("PHP 500.07 Ref No. 1002849130490", nb))
    ok, enc = cv2.imencode(".png", np.full((80, 200, 3), 255, np.uint8))
    r = verify.verify_receipt(enc.tobytes(), "B")
    assert r["status"] == "VERIFIED" and "Order #A" in r["warning"]
