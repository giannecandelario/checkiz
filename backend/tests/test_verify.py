from app.ledger import parse_sms
from app.parser import load_image, parse_fields

def test_parse_fields():
    f = parse_fields("Amount PHP 1,250.00\nRef No. 1002 849 130490")
    assert f["amount"] == 1250.00
    assert f["ref"] == "1002849130490"

def test_parse_sms():
    sms = "You have received PHP 1,250.00 of GCash from JUAN D. Ref. No. 1002 849 130490."
    e = parse_sms(sms)
    assert e and e["ref"] == "1002849130490" and e["amount"] == 1250.00

def test_parse_sms_rejects_garbage():
    assert parse_sms("hello world") is None

def test_no_bytes_is_not_a_picture():
    """cv2.imdecode *raises* on zero-length input instead of returning None like it
    does for any other unreadable body, so an empty upload reached the seller as a 500.
    "nothing arrived" is the same answer as "what arrived was not a picture"."""
    assert load_image(b"") is None
    assert load_image(b"\x00\x01\x02") is None
